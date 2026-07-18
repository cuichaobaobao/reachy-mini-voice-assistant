"""Message dispatch helpers for `VoiceSatelliteProtocol`."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aioesphomeapi.api_pb2 import (  # type: ignore[attr-defined]
    ButtonCommandRequest,
    DeviceInfoRequest,
    DeviceInfoResponse,
    HomeAssistantStateResponse,
    ListEntitiesDoneResponse,
    ListEntitiesRequest,
    MediaPlayerCommandRequest,
    NumberCommandRequest,
    SelectCommandRequest,
    SubscribeHomeAssistantStatesRequest,
    SubscribeStatesRequest,
    SwitchCommandRequest,
    VoiceAssistantAnnounceRequest,
    VoiceAssistantConfigurationRequest,
    VoiceAssistantConfigurationResponse,
    VoiceAssistantEventResponse,
    VoiceAssistantSetConfiguration,
    VoiceAssistantTimerEventResponse,
    VoiceAssistantWakeWord,
)
from aioesphomeapi.model import VoiceAssistantEventType, VoiceAssistantFeature, VoiceAssistantTimerEventType
from google.protobuf import message

from .. import __version__
from .entity_bridge import handle_ha_state_change, schedule_ha_connected_callback
from .voice_pipeline import handle_timer_event, handle_voice_event

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .satellite import VoiceSatelliteProtocol

_LOGGER = logging.getLogger(__name__)

_MULTI_CHANNEL_AUDIO_FEATURE = getattr(VoiceAssistantFeature, "MULTI_CHANNEL_AUDIO", 0)


def _voice_assistant_feature_flags(protocol: VoiceSatelliteProtocol) -> int:
    flags = (
        VoiceAssistantFeature.VOICE_ASSISTANT
        | VoiceAssistantFeature.API_AUDIO
        | VoiceAssistantFeature.ANNOUNCE
        | VoiceAssistantFeature.START_CONVERSATION
        | VoiceAssistantFeature.TIMERS
    )
    if (
        _MULTI_CHANNEL_AUDIO_FEATURE
        and getattr(protocol, "supports_audio_data2", False)
        and protocol.state.audio_input_channels >= 2
    ):
        flags |= _MULTI_CHANNEL_AUDIO_FEATURE
    return flags


def handle_message(protocol: VoiceSatelliteProtocol, msg: message.Message) -> Iterable[message.Message]:
    if isinstance(msg, VoiceAssistantEventResponse):
        data: dict[str, str] = {}
        for arg in msg.data:
            data[arg.name] = arg.value
        handle_voice_event(protocol, VoiceAssistantEventType(msg.event_type), data)
        return []

    if isinstance(msg, VoiceAssistantAnnounceRequest):
        _LOGGER.debug("Announcing: %s", msg.text)
        assert protocol.state.media_player_entity is not None
        urls = []
        if msg.preannounce_media_id:
            urls.append(msg.preannounce_media_id)
        urls.append(msg.media_id)
        protocol.state.active_wake_words.add(protocol.state.stop_word.id)
        protocol._set_stop_word_active(True)
        protocol._continue_conversation = msg.start_conversation
        protocol.duck()
        return list(
            protocol.state.media_player_entity.play(urls, announcement=True, done_callback=protocol._tts_finished)
        )

    if isinstance(msg, VoiceAssistantTimerEventResponse):
        handle_timer_event(protocol, VoiceAssistantTimerEventType(msg.event_type), msg)
        return []

    if isinstance(msg, HomeAssistantStateResponse):
        handle_ha_state_change(protocol, msg)
        return []

    if isinstance(msg, DeviceInfoRequest):
        return [
            DeviceInfoResponse(
                uses_password=False,
                name=protocol.state.name,
                friendly_name=protocol.state.name,
                project_name="ReachyMini.VoiceAssistant",
                project_version=__version__,
                esphome_version=protocol._aioesphomeapi_version,
                mac_address=protocol.state.mac_address,
                manufacturer="Reachy Mini Voice Assistant",
                model="Reachy Mini Voice Assistant",
                voice_assistant_feature_flags=_voice_assistant_feature_flags(protocol),
            )
        ]

    if isinstance(
        msg,
        (
            ListEntitiesRequest,
            SubscribeHomeAssistantStatesRequest,
            SubscribeStatesRequest,
            MediaPlayerCommandRequest,
            NumberCommandRequest,
            SwitchCommandRequest,
            SelectCommandRequest,
            ButtonCommandRequest,
        ),
    ):
        responses: list[message.Message] = []
        for entity in protocol.state.entities:
            responses.extend(entity.handle_message(msg))
        if isinstance(msg, ListEntitiesRequest):
            responses.append(ListEntitiesDoneResponse())
        return responses

    if isinstance(msg, VoiceAssistantConfigurationRequest):
        available_wake_words = [
            VoiceAssistantWakeWord(
                id=ww.id,
                wake_word=ww.wake_word,
                trained_languages=ww.trained_languages,
            )
            for ww in protocol.state.available_wake_words.values()
        ]
        _LOGGER.info("Connected to Home Assistant")
        schedule_ha_connected_callback(protocol)
        return [
            VoiceAssistantConfigurationResponse(
                available_wake_words=available_wake_words,
                active_wake_words=[
                    wake_word_id
                    for wake_word_id in protocol.state.preferences.active_wake_words
                    if wake_word_id in protocol.state.active_wake_words
                ]
                or [ww.id for ww in protocol.state.wake_words.values() if ww.id in protocol.state.active_wake_words],
                max_active_wake_words=2,
            )
        ]

    if isinstance(msg, VoiceAssistantSetConfiguration):
        active_wake_words: set[str] = set()
        active_wake_word_ids: list[str] = []
        for wake_word_id in msg.active_wake_words:
            if wake_word_id in protocol.state.wake_words:
                active_wake_words.add(wake_word_id)
                active_wake_word_ids.append(wake_word_id)
                continue
            model_info = protocol.state.available_wake_words.get(wake_word_id)
            if not model_info:
                _LOGGER.warning("Wake word not found: %s", wake_word_id)
                continue
            _LOGGER.debug("Loading wake word: %s", model_info.wake_word_path)
            loaded_model = model_info.load()
            loaded_model.id = wake_word_id
            protocol.state.wake_words[wake_word_id] = loaded_model
            _LOGGER.info("Wake word loaded: %s", wake_word_id)
            active_wake_words.add(wake_word_id)
            active_wake_word_ids.append(wake_word_id)
        protocol.state.active_wake_words = active_wake_words
        _LOGGER.debug("Active wake words: %s", active_wake_words)
        protocol.state.preferences.active_wake_words = active_wake_word_ids
        protocol.state.save_preferences()
        protocol.state.wake_words_changed = True
        return []

    return []
