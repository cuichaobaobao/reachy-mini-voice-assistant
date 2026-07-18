"""
Voice Assistant Service for Reachy Mini.

This module provides the main voice assistant service that integrates
with Home Assistant via ESPHome protocol.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field, fields
from pathlib import Path
from queue import Queue
from typing import TYPE_CHECKING

import numpy as np
from reachy_mini import ReachyMini

from .audio.audio_player import AudioPlayer
from .core import Config
from .core.util import get_mac
from .models import AvailableWakeWord, Preferences, ServerState, WakeWordType
from .motion.reachy_motion import ReachyMiniMotion
from .protocol.satellite import VoiceSatelliteProtocol
from .protocol.zeroconf import HomeAssistantZeroconf, get_default_friendly_name
from .vision import CameraFrameSource

if TYPE_CHECKING:
    from pymicro_wakeword import MicroWakeWord

_LOGGER = logging.getLogger(__name__)

_MODULE_DIR = Path(__file__).parent
_WAKEWORDS_DIR = _MODULE_DIR / "wakewords"
_SOUNDS_DIR = _MODULE_DIR / "sounds"
_LOCAL_DIR = _MODULE_DIR.parent / "local"
_BUNDLED_WAKE_WORD_IDS = ("okay_nabu", "hey_mycroft", "hey_jarvis")


@dataclass
class AudioProcessingContext:
    """Context for audio processing, holding mutable state."""

    wake_words: list = field(default_factory=list)
    micro_features: object | None = None
    micro_inputs: list = field(default_factory=list)
    last_active: float | None = None


# Audio chunk size for consistent streaming.
# 512 samples lowers idle audio-loop CPU pressure while keeping wake latency reasonable.
# ESPHome typical range: 256-512 samples
AUDIO_BLOCK_SIZE = 512  # samples at 16kHz = 32ms
MAX_AUDIO_BUFFER_SIZE = AUDIO_BLOCK_SIZE * 40  # Max 40 chunks (~640ms) to prevent memory leak


class VoiceAssistantService:
    """Voice assistant service that runs ESPHome protocol server."""

    def __init__(
        self,
        reachy_mini: ReachyMini,
        name: str | None = None,
        host: str = "0.0.0.0",
        port: int = 6053,
        wake_model: str = "okay_nabu",
    ):
        Config.initialize()
        self.reachy_mini = reachy_mini
        self.name = name or get_default_friendly_name()
        self.host = host
        self.port = port
        self.wake_model = wake_model

        self._server = None
        self._discovery = None
        self._audio_thread = None
        self._running = False
        self._state: ServerState | None = None
        self._motion = ReachyMiniMotion(reachy_mini)
        self._camera_frames = CameraFrameSource(
            reachy_mini,
            Config.vision.jpeg_refresh_hz,
            enabled=Config.vision.jpeg_enabled,
        )

        # Audio buffer for fixed-size chunk output
        # Use deque with maxlen to avoid creating new arrays on every operation
        # This prevents memory leak from repeated array creation (2-3 arrays per chunk)
        self._audio_buffer: deque[float] = deque(maxlen=MAX_AUDIO_BUFFER_SIZE)
        self._audio_buffer_2: deque[float] = deque(maxlen=MAX_AUDIO_BUFFER_SIZE)

        # Audio overflow log throttling
        self._last_audio_overflow_log = 0.0
        self._suppressed_audio_overflows = 0

        # Robot services pause/resume tracking (without RobotStateMonitor)
        self._robot_services_paused = threading.Event()  # Set when services should pause
        self._robot_services_resumed = threading.Event()  # Event-driven resume signaling
        self._robot_services_resumed.set()  # Start in resumed state

        # GStreamer access lock - prevents concurrent access to media pipeline
        # This prevents crashes when multiple threads access get_audio_sample() and push_audio_sample().
        self._gstreamer_lock = threading.Lock()

        self._event_loop: asyncio.AbstractEventLoop | None = None

        # Home Assistant connection state
        self._ha_connected = False  # Track whether HA is connected
        self._ha_connection_established = False  # Track if HA connection was ever established
        self._ha_disconnect_handle: asyncio.TimerHandle | None = None
        self._ha_disconnect_debounce_s = 3.0

    async def start(self) -> None:
        """Start the voice assistant service."""
        _LOGGER.info("Initializing voice assistant service...")

        # Ensure directories exist
        _WAKEWORDS_DIR.mkdir(parents=True, exist_ok=True)
        _SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
        _LOCAL_DIR.mkdir(parents=True, exist_ok=True)

        # Verify required files (bundled with package)
        await self._verify_required_files()

        # Load wake words
        available_wake_words = self._load_available_wake_words()
        _LOGGER.debug("Available wake words: %s", list(available_wake_words.keys()))

        # Load preferences
        preferences_path = _LOCAL_DIR / "preferences.json"
        preferences = self._load_preferences(preferences_path)

        # Load wake word models
        wake_models, active_wake_words = self._load_wake_models(available_wake_words, preferences)

        # Load stop model
        stop_model = self._load_stop_model()

        # Create audio players with Reachy Mini reference and GStreamer lock
        music_player = AudioPlayer(self.reachy_mini, gstreamer_lock=self._gstreamer_lock)
        tts_player = AudioPlayer(self.reachy_mini, gstreamer_lock=self._gstreamer_lock)

        # Create server state
        self._state = ServerState(
            name=self.name,
            mac_address=get_mac(),
            audio_queue=Queue(),
            entities=[],
            available_wake_words=available_wake_words,
            wake_words=wake_models,
            active_wake_words=active_wake_words,
            stop_word=stop_model,
            music_player=music_player,
            tts_player=tts_player,
            wakeup_sound=str(_SOUNDS_DIR / "wake_word_triggered.flac"),
            timer_finished_sound=str(_SOUNDS_DIR / "timer_finished.flac"),
            preferences=preferences,
            preferences_path=preferences_path,
            refractory_seconds=2.0,
            reachy_mini=self.reachy_mini,
            motion_enabled=True,
        )
        self._restore_wake_word_thresholds(self._state)

        # Log stop word status
        if self._state.stop_word:
            _LOGGER.info("Stop word initialized with ID: %s", self._state.stop_word.id)
        else:
            _LOGGER.error("Stop word is None! Stop command will not work")

        # Set motion controller reference in state
        self._state.motion = self._motion
        if self._motion and self._motion.movement_manager:
            idle_enabled = preferences.idle_behavior_enabled
            self._motion.movement_manager.set_idle_behavior_enabled(idle_enabled)
            self._motion.movement_manager.set_face_tracking_enabled(Config.vision.face_tracking_enabled)
            _LOGGER.info("Idle behavior restored from preferences: %s", idle_enabled)

        # Start Reachy Mini media system
        try:
            # Check if media system is already running to avoid conflicts
            media = self.reachy_mini.media
            if media.audio is not None:
                # Clean stale media state from previous app sessions (daemon is persistent)
                try:
                    media.stop_recording()
                except Exception:
                    pass
                try:
                    media.stop_playing()
                except Exception:
                    pass
                time.sleep(0.2)

                media.start_recording()
                _LOGGER.info("Started Reachy Mini recording")
                media.start_playing()
                _LOGGER.info("Started Reachy Mini playback")

                # Deterministic startup validation: fail fast instead of repeated
                # fallback/recovery loops that hide root causes.
                if not self._probe_audio_capture_ready(media, timeout_s=1.5):
                    raise RuntimeError("Audio capture probe failed after media startup")

                _LOGGER.info("Reachy Mini media system initialized")

                # Body yaw now follows head yaw in movement_manager.py

        except Exception as e:
            _LOGGER.warning("Failed to initialize Reachy Mini media: %s", e)

        if Config.vision.jpeg_enabled:
            frame = self._camera_frames.capture(force=True)
            if frame is None:
                _LOGGER.warning("JPEG frames requested, but no SDK JPEG frame is available")
            else:
                _LOGGER.info("SDK JPEG frame source ready for private voice vision")

        # Start motion controller (official-aligned 60Hz control loop)
        self._motion.start()

        # Match the official conversation app: speech-driven head wobbling is
        # handled by the Reachy Mini SDK/media pipeline, not by an app-local
        # TTS analysis callback.
        try:
            self.reachy_mini.enable_wobbling()
            _LOGGER.info("SDK speech wobbling enabled")
        except Exception as e:
            _LOGGER.warning("Failed to enable SDK speech wobbling: %s", e)

        # Start audio processing thread (non-daemon for proper cleanup)
        self._running = True
        self._audio_thread = threading.Thread(
            target=self._process_audio,
            daemon=False,
        )
        self._audio_thread.start()

        # Create ESPHome server
        loop = asyncio.get_running_loop()

        def protocol_factory():
            try:
                protocol = VoiceSatelliteProtocol(self._state, voice_assistant_service=self)
                protocol.set_ha_connection_callbacks(
                    on_connected=self._on_ha_connected, on_disconnected=self._on_ha_disconnected
                )
                return protocol
            except Exception:
                _LOGGER.exception("Failed to initialize ESPHome protocol connection")
                raise

        self._server = await loop.create_server(
            protocol_factory,
            host=self.host,
            port=self.port,
        )

        # Start mDNS discovery
        self._discovery = HomeAssistantZeroconf(port=self.port, name=self.name)
        await self._discovery.register_server()

        # Store service event loop for cross-thread async toggles
        self._event_loop = asyncio.get_running_loop()

        _LOGGER.info("Voice assistant service started on %s:%s", self.host, self.port)

    def capture_camera_frame(self) -> bytes | None:
        """Return a private JPEG snapshot for local voice behaviors only."""
        return self._camera_frames.capture()

    def _probe_audio_capture_ready(self, media, timeout_s: float = 1.5) -> bool:
        """Check whether microphone samples become available shortly after startup."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                sample = media.get_audio_sample()
                if sample is not None and isinstance(sample, np.ndarray) and sample.size > 0:
                    return True
            except Exception:
                pass
            time.sleep(0.05)
        return False

    def _suspend_voice_services(self, reason: str) -> None:
        """Suspend only voice-related services."""
        _LOGGER.warning("Suspending voice services (%s)", reason)
        self._robot_services_paused.set()
        self._robot_services_resumed.clear()
        self._set_service_state(suspended=True)
        self._audio_buffer.clear()
        self._audio_buffer_2.clear()
        self._suspend_satellite()
        self._set_audio_players_suspended(True)
        self._stop_media_system()

        _LOGGER.info("Voice services suspended - motion remains active")

    def _resume_voice_services(self, reason: str) -> None:
        """Resume only voice-related services."""
        _LOGGER.info("Resuming voice services (%s)", reason)
        self._robot_services_paused.clear()
        self._set_service_state(suspended=False)
        self._start_media_system()
        self._resume_satellite()
        self._set_audio_players_suspended(False)
        self._robot_services_resumed.set()

        _LOGGER.info("Voice services resumed - motion remained active")

    def _suspend_non_esphome_services(self, reason: str) -> None:
        """Suspend all non-ESPHome services."""
        _LOGGER.warning("Suspending non-ESPHome services (%s)", reason)
        self._robot_services_paused.set()
        self._robot_services_resumed.clear()
        self._set_service_state(suspended=True)
        self._audio_buffer.clear()
        self._audio_buffer_2.clear()

        if self._motion is not None and self._motion._movement_manager is not None:
            try:
                self._motion._movement_manager.suspend()
                _LOGGER.debug("Motion controller suspended")
            except Exception as e:
                _LOGGER.warning("Error suspending motion: %s", e)

        self._suspend_satellite()
        self._set_audio_players_suspended(True)
        self._stop_media_system()

        _LOGGER.info("Services suspended - ESPHome only")

    def _resume_non_esphome_services(self, reason: str) -> None:
        """Resume all non-ESPHome services after runtime suspension."""
        _LOGGER.info("Resuming non-ESPHome services (%s)", reason)
        self._robot_services_paused.clear()
        self._set_service_state(suspended=False)
        self._start_media_system()

        if self._motion is not None and self._motion._movement_manager is not None:
            try:
                self._motion._movement_manager.resume_from_suspend()
                _LOGGER.debug("Motion controller resumed from suspend")
            except Exception as e:
                _LOGGER.warning("Error resuming motion: %s", e)

        self._resume_satellite()
        self._set_audio_players_suspended(False)
        self._robot_services_resumed.set()

        _LOGGER.info("All services resumed - system fully operational")

    def _set_service_state(self, *, suspended: bool) -> None:
        if self._state is None:
            return
        self._state.services_suspended = suspended

    def _suspend_satellite(self) -> None:
        if self._state is None or self._state.satellite is None:
            return
        try:
            self._state.satellite.suspend()
            _LOGGER.debug("Satellite suspended")
        except Exception as e:
            _LOGGER.warning("Error suspending satellite: %s", e)

    def _resume_satellite(self) -> None:
        if self._state is None or self._state.satellite is None:
            return
        try:
            self._state.satellite.resume()
            _LOGGER.debug("Satellite resumed")
        except Exception as e:
            _LOGGER.warning("Error resuming satellite: %s", e)

    def _set_audio_players_suspended(self, suspended: bool) -> None:
        if self._state is None:
            return
        action = "suspend" if suspended else "resume"
        verb = "suspending" if suspended else "resuming"
        for player_name, label in (("tts_player", "TTS player"), ("music_player", "music player")):
            player = getattr(self._state, player_name)
            if player is None:
                continue
            try:
                getattr(player, action)()
            except Exception as e:
                _LOGGER.warning("Error %s %s: %s", verb, label, e)

    def _stop_media_system(self) -> None:
        media = self.reachy_mini.media
        try:
            media.stop_recording()
        except Exception as e:
            _LOGGER.warning("Error stopping recording: %s", e)
        try:
            media.stop_playing()
        except Exception as e:
            _LOGGER.warning("Error stopping playback: %s", e)
        _LOGGER.debug("Media system stopped")

    def _start_media_system(self) -> None:
        try:
            media = self.reachy_mini.media
            if media.audio is not None:
                try:
                    media.stop_recording()
                except Exception:
                    pass
                try:
                    media.stop_playing()
                except Exception:
                    pass
                time.sleep(0.2)
                media.start_recording()
                media.start_playing()
                if not self._probe_audio_capture_ready(media, timeout_s=1.5):
                    raise RuntimeError("Audio capture probe failed after media restart")
                _LOGGER.info("Media system restarted")
        except Exception as e:
            _LOGGER.warning("Failed to restart media: %s", e)

    def _on_robot_disconnected(self) -> None:
        """Called when robot connection is lost."""
        self._suspend_non_esphome_services(reason="robot_disconnected")

    def _on_robot_connected(self) -> None:
        """Called when robot connection is restored."""
        self._resume_non_esphome_services(reason="robot_connected")

    async def _on_ha_connected(self) -> None:
        """Called when Home Assistant connects."""
        _LOGGER.info("Home Assistant connected - initializing voice services")
        self._cancel_ha_disconnect_timer()
        self._ha_connected = True
        self._ha_connection_established = True

        # Resume services if they were suspended due to HA disconnection
        if self._state.services_suspended:
            self._resume_non_esphome_services(reason="ha_connected")

    def _cancel_ha_disconnect_timer(self) -> None:
        if self._ha_disconnect_handle is not None:
            self._ha_disconnect_handle.cancel()
            self._ha_disconnect_handle = None

    def _apply_ha_disconnect_suspend(self) -> None:
        self._ha_disconnect_handle = None
        if self._ha_connected:
            return
        _LOGGER.warning("Home Assistant still disconnected after debounce - suspending voice services")
        self._suspend_non_esphome_services(reason="ha_disconnected")

    def _on_ha_disconnected(self) -> None:
        """Called when Home Assistant disconnects."""
        _LOGGER.warning(
            "Home Assistant disconnected - waiting %.1fs before suspending voice services",
            self._ha_disconnect_debounce_s,
        )
        self._ha_connected = False

        self._cancel_ha_disconnect_timer()
        loop = self._event_loop
        if loop is not None and loop.is_running():
            self._ha_disconnect_handle = loop.call_later(
                self._ha_disconnect_debounce_s, self._apply_ha_disconnect_suspend
            )
        else:
            self._apply_ha_disconnect_suspend()

    async def stop(self) -> None:
        """Stop the voice assistant service."""
        _LOGGER.info("Stopping voice assistant service...")
        self._cancel_ha_disconnect_timer()

        # 1. First stop audio recording to prevent new data from coming in
        try:
            self.reachy_mini.media.stop_recording()
            _LOGGER.debug("Reachy Mini recording stopped")
        except Exception as e:
            _LOGGER.warning("Error stopping Reachy Mini recording: %s", e)

        # 2. Set stop flag
        self._running = False
        # Wake any threads blocked on resume signal
        self._robot_services_resumed.set()

        # 3. Wait for audio thread to finish
        if self._audio_thread:
            self._audio_thread.join(timeout=Config.shutdown.audio_thread_join_timeout)
            if self._audio_thread.is_alive():
                _LOGGER.warning("Audio thread did not stop in time")

        # 4. Stop playback
        try:
            try:
                self.reachy_mini.disable_wobbling()
                _LOGGER.debug("SDK speech wobbling disabled")
            except Exception as e:
                _LOGGER.debug("Error disabling SDK speech wobbling: %s", e)
            self.reachy_mini.media.stop_playing()
            _LOGGER.debug("Reachy Mini playback stopped")
        except Exception as e:
            _LOGGER.warning("Error stopping Reachy Mini playback: %s", e)

        # 5. Stop ESPHome server
        if self._server:
            self._server.close()
            try:
                await asyncio.wait_for(
                    self._server.wait_closed(),
                    timeout=Config.shutdown.server_close_timeout,
                )
            except TimeoutError:
                _LOGGER.warning("ESPHome server did not close in time")

        # 6. Unregister mDNS
        if self._discovery:
            try:
                await asyncio.wait_for(
                    self._discovery.unregister_server(),
                    timeout=Config.shutdown.server_close_timeout,
                )
            except TimeoutError:
                _LOGGER.warning("mDNS unregister did not finish in time")

        # 7. Close SDK media resources to prevent memory leaks
        try:
            self.reachy_mini.media.close()
            _LOGGER.info("SDK media resources closed")
        except Exception as e:
            _LOGGER.debug("Failed to close SDK media: %s", e)

        # 8. Shutdown motion executor
        if self._motion:
            self._motion.shutdown()

        _LOGGER.info("Voice assistant service stopped.")

    async def _verify_required_files(self) -> None:
        """Verify required model and sound files exist (bundled with package)."""
        required_wakewords = [
            *(f"{wake_word_id}.tflite" for wake_word_id in _BUNDLED_WAKE_WORD_IDS),
            *(f"{wake_word_id}.json" for wake_word_id in _BUNDLED_WAKE_WORD_IDS),
            "stop.tflite",
            "stop.json",
        ]

        # Required sound files (bundled in sounds/ directory)
        required_sounds = [
            "wake_word_triggered.flac",
            "timer_finished.flac",
        ]

        missing_wakewords = self._find_missing_files(_WAKEWORDS_DIR, required_wakewords)

        if missing_wakewords:
            _LOGGER.warning("Missing wake word files: %s. These should be bundled with the package.", missing_wakewords)

        missing_sounds = self._find_missing_files(_SOUNDS_DIR, required_sounds)

        if missing_sounds:
            _LOGGER.warning("Missing sound files: %s. These should be bundled with the package.", missing_sounds)

        if not missing_wakewords and not missing_sounds:
            _LOGGER.info("All required files verified successfully.")

    @staticmethod
    def _find_missing_files(base_dir: Path, filenames: list[str]) -> list[str]:
        return [filename for filename in filenames if not (base_dir / filename).exists()]

    @staticmethod
    def _get_probability_cutoff(config: dict, model_type: WakeWordType, default: float) -> float:
        """Read a wake word probability cutoff the same way OHF does."""
        type_config = config.get(model_type.value, {})
        try:
            return float(type_config.get("probability_cutoff", default))
        except (TypeError, ValueError):
            return default

    def _load_available_wake_words(self) -> dict[str, AvailableWakeWord]:
        """Load available wake word configurations."""
        available_wake_words: dict[str, AvailableWakeWord] = {}

        for model_id in _BUNDLED_WAKE_WORD_IDS:
            config_path = _WAKEWORDS_DIR / f"{model_id}.json"
            try:
                with open(config_path, encoding="utf-8") as f:
                    config = json.load(f)

                model_type = WakeWordType(config.get("type", "micro"))
                if model_type != WakeWordType.MICRO_WAKE_WORD:
                    _LOGGER.warning("Skipping non-MicroWakeWord model: %s", config_path)
                    continue

                available_wake_words[model_id] = AvailableWakeWord(
                    id=model_id,
                    type=model_type,
                    wake_word=config.get("wake_word", model_id),
                    trained_languages=config.get("trained_languages", []),
                    wake_word_path=config_path,
                    probability_cutoff=self._get_probability_cutoff(config, model_type, 0.7),
                )
            except Exception as e:
                _LOGGER.warning("Failed to load wake word %s: %s", config_path, e)

        return available_wake_words

    def _load_preferences(self, preferences_path: Path) -> Preferences:
        """Load user preferences."""
        if preferences_path.exists():
            try:
                with open(preferences_path, encoding="utf-8") as f:
                    data = json.load(f)

                valid_fields = {field.name for field in fields(Preferences)}
                filtered = {key: value for key, value in data.items() if key in valid_fields}
                return Preferences(**filtered)
            except Exception as e:
                _LOGGER.warning("Failed to load preferences: %s", e)

        return Preferences()

    def _load_wake_models(
        self,
        available_wake_words: dict[str, AvailableWakeWord],
        preferences: Preferences,
    ) -> tuple[dict[str, MicroWakeWord], set[str]]:
        """Load wake word models."""

        wake_models: dict[str, MicroWakeWord] = {}
        active_wake_words: set[str] = set()

        if preferences.active_wake_words:
            for wake_word_id in preferences.active_wake_words:
                self._try_add_wake_model(wake_models, active_wake_words, available_wake_words, wake_word_id)

        # Load default model if none loaded
        if not wake_models:
            self._try_add_wake_model(
                wake_models,
                active_wake_words,
                available_wake_words,
                self.wake_model,
                unknown_level="error",
                failure_level="error",
                log_default=True,
            )

        return wake_models, active_wake_words

    def _try_add_wake_model(
        self,
        wake_models: dict[str, MicroWakeWord],
        active_wake_words: set[str],
        available_wake_words: dict[str, AvailableWakeWord],
        wake_word_id: str,
        *,
        unknown_level: str = "warning",
        failure_level: str = "warning",
        log_default: bool = False,
    ) -> None:
        wake_word = available_wake_words.get(wake_word_id)
        if wake_word is None:
            getattr(_LOGGER, unknown_level)("Unknown wake word: %s", wake_word_id)
            return

        try:
            if log_default:
                _LOGGER.debug("Loading default wake model: %s", wake_word_id)
            else:
                _LOGGER.debug("Loading wake model: %s", wake_word_id)
            # pymicro_wakeword writes its parsed config to stdout. Keep the
            # daemon protocol/log stream clean while retaining our own logs.
            with contextlib.redirect_stdout(io.StringIO()):
                loaded_model = wake_word.load()
            loaded_model.id = wake_word_id
            wake_models[wake_word_id] = loaded_model
            active_wake_words.add(wake_word_id)
        except Exception as e:
            message = "Failed to load default wake model: %s" if log_default else "Failed to load wake model %s: %s"
            if log_default:
                getattr(_LOGGER, failure_level)(message, e)
            else:
                getattr(_LOGGER, failure_level)(message, wake_word_id, e)

    def _load_stop_model(self):
        """Load the stop word model."""
        from pymicro_wakeword import MicroWakeWord

        stop_config = _WAKEWORDS_DIR / "stop.json"
        if stop_config.exists():
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    model = MicroWakeWord.from_config(stop_config)
                # Don't override the model ID - use the one from config
                _LOGGER.info("Loaded stop model with ID: %s, config: %s", model.id, stop_config)
                return model
            except Exception as e:
                _LOGGER.error("Failed to load stop model from %s: %s", stop_config, e)
                import traceback

                traceback.print_exc()

        # Stop model not available - disable stop functionality
        _LOGGER.error("Stop model not available at %s - stop functionality will be disabled", stop_config)
        return None

    def _get_stop_word_default_threshold(self) -> float:
        """Read the bundled stop word default cutoff."""
        stop_config = _WAKEWORDS_DIR / "stop.json"
        try:
            with open(stop_config, encoding="utf-8") as f:
                config = json.load(f)
            return self._get_probability_cutoff(config, WakeWordType.MICRO_WAKE_WORD, 0.5)
        except Exception:
            return 0.5

    def _active_wake_word_ids_in_slot_order(self, state: ServerState) -> list[str]:
        """Return active wake word IDs in the same slot order Home Assistant uses."""
        ordered_ids: list[str] = []
        for wake_word_id in state.preferences.active_wake_words:
            if wake_word_id in state.active_wake_words and wake_word_id in state.wake_words:
                ordered_ids.append(wake_word_id)

        for wake_word_id in state.wake_words:
            if wake_word_id in state.active_wake_words and wake_word_id not in ordered_ids:
                ordered_ids.append(wake_word_id)

        return ordered_ids[:2]

    def _restore_wake_word_thresholds(self, state: ServerState) -> None:
        """Restore OHF-style sensitivity thresholds from preferences/model defaults."""
        active_ids = self._active_wake_word_ids_in_slot_order(state)

        wake_word_1_default = (
            state.available_wake_words[active_ids[0]].probability_cutoff
            if len(active_ids) >= 1 and active_ids[0] in state.available_wake_words
            else 0.7
        )
        wake_word_2_default = (
            state.available_wake_words[active_ids[1]].probability_cutoff
            if len(active_ids) >= 2 and active_ids[1] in state.available_wake_words
            else 0.7
        )

        state.wake_word_1_threshold = (
            float(state.preferences.wake_word_1_sensitivity)
            if state.preferences.wake_word_1_sensitivity is not None
            else wake_word_1_default
        )
        state.wake_word_2_threshold = (
            float(state.preferences.wake_word_2_sensitivity)
            if state.preferences.wake_word_2_sensitivity is not None
            else wake_word_2_default
        )
        state.stop_word_threshold = (
            float(state.preferences.stop_word_sensitivity)
            if state.preferences.stop_word_sensitivity is not None
            else self._get_stop_word_default_threshold()
        )

    def _process_audio(self) -> None:
        """Process audio from Reachy Mini's microphone."""
        from pymicro_wakeword import MicroWakeWordFeatures

        ctx = AudioProcessingContext()
        ctx.micro_features = MicroWakeWordFeatures()

        try:
            _LOGGER.info("Starting audio processing using Reachy Mini's microphone...")
            self._audio_loop_reachy(ctx)

        except Exception:
            _LOGGER.exception("Error processing audio")

    def _audio_loop_reachy(self, ctx: AudioProcessingContext) -> None:
        """Audio loop using Reachy Mini's microphone.

        This loop checks the robot connection state before attempting to
        read audio. When the robot is disconnected (e.g., sleep mode),
        the loop waits for reconnection without generating errors.
        """
        consecutive_audio_errors = 0
        max_consecutive_errors = 3  # Pause after 3 consecutive errors

        while self._running:
            try:
                # Check if robot services are paused (sleep mode / disconnected / muted)
                if self._robot_services_paused.is_set():
                    # Wait for resume signal (event-driven, wakes immediately on resume)
                    consecutive_audio_errors = 0  # Reset on pause
                    self._robot_services_resumed.wait(timeout=1.0)
                    continue

                if not self._wait_for_satellite():
                    continue

                # Update wake words list
                self._update_wake_words_list(ctx)

                # Get audio from Reachy Mini
                audio_chunks = self._get_reachy_audio_chunk()
                if audio_chunks is None:
                    idle_sleep = (
                        Config.audio.idle_sleep_sleeping
                        if self._robot_services_paused.is_set()
                        else Config.audio.idle_sleep_active
                    )
                    time.sleep(idle_sleep)
                    continue
                audio_chunk, audio_chunk_2 = audio_chunks

                # Audio successfully obtained, reset error counter
                consecutive_audio_errors = 0
                self._process_audio_chunk(ctx, audio_chunk, audio_chunk_2)

            except Exception as e:
                error_msg = str(e)

                # Check for audio processing errors that indicate sleep mode
                if "can only convert" in error_msg or "scalar" in error_msg:
                    consecutive_audio_errors += 1
                    if consecutive_audio_errors >= max_consecutive_errors:
                        if not self._robot_services_paused.is_set():
                            _LOGGER.warning("Audio errors indicate robot may be asleep - pausing audio processing")
                            self._robot_services_paused.set()
                            self._robot_services_resumed.clear()
                            # Clear audio buffer
                            self._audio_buffer.clear()
                            self._audio_buffer_2.clear()
                    # Wait for resume signal instead of polling
                    self._robot_services_resumed.wait(timeout=0.5)
                    continue

                # Check if this is a connection error
                if "Lost connection" in error_msg:
                    # Don't log - the state monitor will handle this
                    if not self._robot_services_paused.is_set():
                        _LOGGER.debug("Connection error detected, waiting for state monitor")
                    # Wait for resume signal instead of polling
                    self._robot_services_resumed.wait(timeout=1.0)
                else:
                    # Log unexpected errors (but limit frequency)
                    consecutive_audio_errors += 1
                    if consecutive_audio_errors <= 3:
                        _LOGGER.error("Error in Reachy audio processing: %s", e)
                    time.sleep(Config.audio.idle_sleep_sleeping)

    def _wait_for_satellite(self) -> bool:
        """Wait for satellite connection. Returns True if connected."""
        if self._state is None or self._state.satellite is None:
            time.sleep(0.1)
            return False
        return True

    def _update_wake_words_list(self, ctx: AudioProcessingContext) -> None:
        """Update wake words list if changed."""
        from pymicro_wakeword import MicroWakeWordFeatures

        if (not ctx.wake_words) or (self._state.wake_words_changed and self._state.wake_words):
            self._state.wake_words_changed = False
            ctx.wake_words.clear()
            self._restore_wake_word_thresholds(self._state)

            # Reset feature extractors to clear any residual audio data
            # This prevents false triggers when switching wake words
            ctx.micro_features = MicroWakeWordFeatures()
            ctx.micro_inputs.clear()

            # Also reset the refractory period to prevent immediate trigger
            ctx.last_active = time.monotonic()

            for ww_id in self._active_wake_word_ids_in_slot_order(self._state):
                ww_model = self._state.wake_words[ww_id]
                if not hasattr(ww_model, "id"):
                    ww_model.id = ww_id
                ctx.wake_words.append(ww_model)

            _LOGGER.info("Active wake words updated: %s (features reset)", list(self._state.active_wake_words))

    def _set_audio_input_channels(self, channels: int) -> None:
        if self._state is None or self._state.audio_input_channels == channels:
            return
        self._state.audio_input_channels = channels
        _LOGGER.info("Audio input channels detected: %d", channels)

    def _get_reachy_audio_chunk(self) -> tuple[bytes, bytes | None] | None:
        """Get fixed-size audio chunk from Reachy Mini's microphone.

        Returns exactly AUDIO_BLOCK_SIZE samples each time, buffering
        internally to ensure consistent chunk sizes for streaming.

        Returns:
            PCM audio bytes for channel 1 and optional channel 2, or None if not enough data.
        """
        # Check if services are paused (e.g., during sleep/disconnect)
        if self._robot_services_paused.is_set():
            return None

        # Pull enough SDK chunks in one pass to keep up with the live microphone.
        # A single SDK chunk can be smaller than AUDIO_BLOCK_SIZE.
        audio_samples = []
        buffered_samples = len(self._audio_buffer)
        for _ in range(20):
            if buffered_samples >= AUDIO_BLOCK_SIZE:
                break

            sample = self.reachy_mini.media.get_audio_sample()
            if (
                sample is None
                or not isinstance(sample, np.ndarray)
                or sample.ndim == 0
                or sample.size == 0
            ):
                break

            audio_samples.append(sample)
            buffered_samples += sample.shape[0]

        if not audio_samples:
            audio_data = None
        elif len(audio_samples) == 1:
            audio_data = audio_samples[0]
        else:
            audio_data = np.concatenate(audio_samples, axis=0)

        # Debug: Log SDK audio data statistics and sample rate (once at startup)
        if audio_data is not None and isinstance(audio_data, np.ndarray) and audio_data.size > 0:
            if not hasattr(self, "_audio_sample_rate_logged"):
                self._audio_sample_rate_logged = True
                try:
                    input_rate = self.reachy_mini.media.get_input_audio_samplerate()
                    _LOGGER.info(
                        "Audio input: sample_rate=%d Hz, shape=%s, dtype=%s (expected 16000 Hz)",
                        input_rate,
                        audio_data.shape,
                        audio_data.dtype,
                    )
                    if input_rate != 16000:
                        _LOGGER.warning(
                            "Audio sample rate mismatch! Got %d Hz, expected 16000 Hz. "
                            "STT may be slow or inaccurate. Consider resampling.",
                            input_rate,
                        )
                except Exception as e:
                    _LOGGER.warning("Could not get audio sample rate: %s", e)

        # Append new data to buffer if valid
        if audio_data is not None and isinstance(audio_data, np.ndarray) and audio_data.size > 0:
            try:
                if audio_data.dtype.kind not in ("S", "U", "O", "V", "b"):
                    # Convert to float32 only if needed (SDK already returns float32)
                    if audio_data.dtype != np.float32:
                        audio_data = audio_data.astype(np.float32, copy=False)

                    # Clean NaN/Inf values early to prevent downstream errors
                    audio_data = np.nan_to_num(audio_data, nan=0.0, posinf=1.0, neginf=-1.0)

                    audio_channel_2 = None
                    if audio_data.ndim == 2 and audio_data.shape[1] >= 2:
                        audio_channel_2 = audio_data[:, 1]
                        audio_data = audio_data[:, 0]
                        self._set_audio_input_channels(2)
                    elif audio_data.ndim == 2:
                        audio_data = audio_data[:, 0]
                        self._audio_buffer_2.clear()
                        self._set_audio_input_channels(1)
                    elif audio_data.ndim == 1:
                        self._audio_buffer_2.clear()
                        self._set_audio_input_channels(1)

                    # Resample if needed (SDK may return non-16kHz audio)
                    if audio_data.ndim == 1:
                        # Initialize sample rate once (not every chunk)
                        if not hasattr(self, "_input_sample_rate_fixed"):
                            try:
                                self._input_sample_rate = self.reachy_mini.media.get_input_audio_samplerate()
                                if self._input_sample_rate != 16000:
                                    _LOGGER.warning(
                                        f"Sample rate {self._input_sample_rate} != 16000 Hz. "
                                        "Performance may be degraded. "
                                        "Consider forcing 16kHz in hardware config."
                                    )
                            except Exception:
                                self._input_sample_rate = 16000

                            self._input_sample_rate_fixed = True  # Mark as fixed

                        # Resample to 16kHz if needed
                        if self._input_sample_rate != 16000 and self._input_sample_rate > 0:
                            from scipy.signal import resample

                            new_length = int(len(audio_data) * 16000 / self._input_sample_rate)
                            if new_length > 0:
                                audio_data = resample(audio_data, new_length)
                                audio_data = np.nan_to_num(
                                    audio_data,
                                    nan=0.0,
                                    posinf=1.0,
                                    neginf=-1.0,
                                ).astype(np.float32, copy=False)
                                if audio_channel_2 is not None:
                                    audio_channel_2 = resample(audio_channel_2, new_length)
                                    audio_channel_2 = np.nan_to_num(
                                        audio_channel_2,
                                        nan=0.0,
                                        posinf=1.0,
                                        neginf=-1.0,
                                    ).astype(np.float32, copy=False)

                        # Extend deque (deque automatically handles overflow with maxlen)
                        # This avoids creating new arrays like np.concatenate does
                        self._audio_buffer.extend(audio_data)
                        if audio_channel_2 is not None:
                            self._audio_buffer_2.extend(audio_channel_2)

            except (TypeError, ValueError):
                pass

        # Return fixed-size chunk if we have enough data
        if len(self._audio_buffer) >= AUDIO_BLOCK_SIZE:
            # Extract chunk and remove from buffer
            chunk = [self._audio_buffer.popleft() for _ in range(AUDIO_BLOCK_SIZE)]

            # Convert to PCM bytes (16-bit signed, little-endian)
            chunk_array = np.array(chunk, dtype=np.float32)
            pcm_bytes = (np.clip(chunk_array, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
            pcm_bytes_2 = None
            if len(self._audio_buffer_2) >= AUDIO_BLOCK_SIZE:
                chunk_2 = [self._audio_buffer_2.popleft() for _ in range(AUDIO_BLOCK_SIZE)]
                pcm_bytes_2 = self._convert_to_pcm(np.array(chunk_2, dtype=np.float32))
            return pcm_bytes, pcm_bytes_2

        return None

    def _convert_to_pcm(self, audio_chunk_array: np.ndarray) -> bytes:
        """Convert float32 audio array to 16-bit PCM bytes."""
        # Replace NaN/Inf with 0 to avoid casting errors
        audio_clean = np.nan_to_num(audio_chunk_array, nan=0.0, posinf=1.0, neginf=-1.0)
        return (np.clip(audio_clean, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()

    def _process_audio_chunk(
        self,
        ctx: AudioProcessingContext,
        audio_chunk: bytes,
        audio_chunk_2: bytes | None = None,
    ) -> None:
        """Process an audio chunk for wake word detection.

        Following reference project pattern: always process wake words.
        Refractory period prevents duplicate triggers.

        Args:
            ctx: Audio processing context
            audio_chunk: PCM audio bytes
        """
        # Stream audio to Home Assistant only after wake (privacy: no pre-wake upload)
        if self._state.satellite.is_streaming_audio:
            self._state.satellite.handle_audio(audio_chunk, audio_chunk_2)

        # Process wake word features
        self._process_features(ctx, audio_chunk)

        # Detect wake words
        self._detect_wake_words(ctx)

        # Detect stop word
        self._detect_stop_word(ctx)

    def _process_features(self, ctx: AudioProcessingContext, audio_chunk: bytes) -> None:
        """Process audio features for wake word detection."""
        ctx.micro_inputs.clear()
        ctx.micro_inputs.extend(ctx.micro_features.process_streaming(audio_chunk))

    def _detect_wake_words(self, ctx: AudioProcessingContext) -> None:
        """Detect wake words in the processed audio features.

        Uses refractory period to prevent duplicate triggers.
        Following reference project pattern.
        """
        from pymicro_wakeword import MicroWakeWord

        for wake_word_index, wake_word in enumerate(ctx.wake_words):
            activated = False

            if isinstance(wake_word, MicroWakeWord):
                wake_word.probability_cutoff = (
                    self._state.wake_word_1_threshold if wake_word_index == 0 else self._state.wake_word_2_threshold
                )
                for micro_input in ctx.micro_inputs:
                    if wake_word.process_streaming(micro_input):
                        activated = True

            if activated:
                # Check refractory period to prevent duplicate triggers
                now = time.monotonic()
                if (ctx.last_active is None) or ((now - ctx.last_active) > self._state.refractory_seconds):
                    _LOGGER.info("Wake word detected: %s", wake_word.id)
                    self._state.satellite.wakeup(wake_word)
                    self._motion.on_wakeup()
                    ctx.last_active = now

    def _detect_stop_word(self, ctx: AudioProcessingContext) -> None:
        """Detect stop word in the processed audio features."""
        if not self._state.stop_word:
            _LOGGER.warning("Stop word model not loaded")
            return

        # Keep stop-word arming aligned with actual playback, not only protocol
        # bookkeeping. This makes spoken "stop" robust even if the HA event
        # sequence or callback timing briefly desynchronizes the armed state.
        if self._state.tts_player.is_playing and self._state.stop_word.id not in self._state.active_wake_words:
            self._state.active_wake_words.add(self._state.stop_word.id)
            try:
                self._state.stop_word.is_active = True
            except Exception:
                pass

        stopped = False
        self._state.stop_word.probability_cutoff = self._state.stop_word_threshold
        for micro_input in ctx.micro_inputs:
            if self._state.stop_word.process_streaming(micro_input):
                stopped = True
                break  # Stop at first detection

        stop_armed = self._state.stop_word.id in self._state.active_wake_words
        if stopped and stop_armed and (not self._state.is_muted):
            _LOGGER.info("Stop word detected - stopping playback")
            self._state.satellite.stop()
