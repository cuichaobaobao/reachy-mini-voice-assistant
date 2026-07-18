import types
import unittest
from unittest.mock import patch

from aioesphomeapi.api_pb2 import VoiceAssistantRequest
from aioesphomeapi.model import VoiceAssistantEventType

from reachy_mini_ha_voice.protocol import satellite, voice_pipeline
from reachy_mini_ha_voice.protocol.satellite import VoiceSatelliteProtocol


class FakeTimer:
    def __init__(self, delay, callback):
        self.delay = delay
        self.callback = callback
        self.cancelled = False
        self.daemon = False

    def start(self):
        return None

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.callback()


class ListeningWatchdogTests(unittest.TestCase):
    def _make_protocol(self):
        protocol = object.__new__(VoiceSatelliteProtocol)
        stop_word = types.SimpleNamespace(id="stop", is_active=True)
        protocol.state = types.SimpleNamespace(
            active_wake_words={"stop"},
            stop_word=stop_word,
            tts_player=types.SimpleNamespace(stop=lambda: None),
        )
        protocol._is_streaming_audio = True
        protocol._pipeline_active = True
        protocol._pending_voice_request = ("wake", "conv")
        protocol._tts_url = "http://example.test/tts"
        protocol._tts_played = False
        protocol._continue_conversation = True
        protocol._timer_finished = False
        protocol._timer_ring_start = None
        protocol._idle_return_timer = None
        protocol._listening_watchdog_timer = None
        protocol._listening_watchdog_generation = 0
        protocol._writelines = object()
        protocol._buffer = None
        protocol._buffer_len = 0
        protocol._pos = 0

        protocol.sent_messages = []
        protocol.idle_calls = []
        protocol.unduck_calls = []

        def send_messages(messages):
            protocol.sent_messages.extend(messages)

        protocol.send_messages = send_messages
        protocol._reachy_on_idle = lambda: protocol.idle_calls.append(True)
        protocol.unduck = lambda: protocol.unduck_calls.append(True)
        return protocol

    def test_listening_watchdog_aborts_pipeline_and_returns_motion_to_idle(self):
        protocol = self._make_protocol()

        with patch.object(satellite.threading, "Timer", FakeTimer):
            protocol._start_listening_watchdog()
            timer = protocol._listening_watchdog_timer
            self.assertIsNotNone(timer)
            timer.fire()

        self.assertFalse(protocol._pipeline_active)
        self.assertFalse(protocol._is_streaming_audio)
        self.assertIsNone(protocol._pending_voice_request)
        self.assertIsNone(protocol._tts_url)
        self.assertFalse(protocol._continue_conversation)
        self.assertNotIn(protocol.state.stop_word.id, protocol.state.active_wake_words)
        self.assertFalse(protocol.state.stop_word.is_active)
        self.assertEqual(len(protocol.idle_calls), 1)
        self.assertEqual(len(protocol.unduck_calls), 1)
        self.assertEqual(len(protocol.sent_messages), 1)
        self.assertIsInstance(protocol.sent_messages[0], VoiceAssistantRequest)
        self.assertFalse(protocol.sent_messages[0].start)

    def test_stt_end_cancels_listening_watchdog(self):
        protocol = self._make_protocol()
        protocol._reachy_on_thinking_calls = []
        protocol._reachy_on_thinking = lambda: protocol._reachy_on_thinking_calls.append(True)

        with patch.object(satellite.threading, "Timer", FakeTimer):
            protocol._start_listening_watchdog()
            timer = protocol._listening_watchdog_timer
            voice_pipeline.handle_voice_event(
                protocol,
                VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
                {},
            )

        self.assertTrue(timer.cancelled)
        self.assertIsNone(protocol._listening_watchdog_timer)
        self.assertFalse(protocol._is_streaming_audio)
        self.assertEqual(protocol._reachy_on_thinking_calls, [True])

    def test_ha_disconnect_forces_idle_when_voice_was_active(self):
        protocol = self._make_protocol()
        disconnected_calls = []
        protocol._on_ha_disconnected_callback = lambda: disconnected_calls.append(True)

        protocol.connection_lost(None)

        self.assertFalse(protocol._pipeline_active)
        self.assertFalse(protocol._is_streaming_audio)
        self.assertIsNone(protocol._pending_voice_request)
        self.assertEqual(protocol.idle_calls, [True])
        self.assertEqual(disconnected_calls, [True])


if __name__ == "__main__":
    unittest.main()
