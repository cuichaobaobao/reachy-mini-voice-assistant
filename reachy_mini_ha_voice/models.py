"""Shared models for Reachy Mini Voice Assistant."""

import json
import logging
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import threading
    from queue import Queue

    from pymicro_wakeword import MicroWakeWord

    from .audio.audio_player import AudioPlayer
    from .entities.entity import ESPHomeEntity, MediaPlayerEntity
    from .protocol.satellite import VoiceSatelliteProtocol

_LOGGER = logging.getLogger(__name__)


class WakeWordType(StrEnum):
    MICRO_WAKE_WORD = "micro"


@dataclass
class AvailableWakeWord:
    id: str
    type: WakeWordType
    wake_word: str
    trained_languages: list[str]
    wake_word_path: Path
    probability_cutoff: float = 0.7

    def load(self) -> "MicroWakeWord":
        if self.type == WakeWordType.MICRO_WAKE_WORD:
            from pymicro_wakeword import MicroWakeWord

            return MicroWakeWord.from_config(config_path=self.wake_word_path)

        raise ValueError(f"Unexpected wake word type: {self.type}")


@dataclass
class Preferences:
    active_wake_words: list[str] = field(default_factory=list)
    wake_word_1_sensitivity: float | None = None
    wake_word_2_sensitivity: float | None = None
    stop_word_sensitivity: float | None = None
    # Continuous conversation mode (controlled from Home Assistant)
    continuous_conversation: bool = False
    # Unified idle behavior toggle (controlled from Home Assistant)
    idle_behavior_enabled: bool = False

    def set_idle_behavior_enabled(self, enabled: bool) -> None:
        """Update the unified idle behavior toggle."""
        self.idle_behavior_enabled = enabled


@dataclass
class ServerState:
    """Global server state."""

    name: str
    mac_address: str
    audio_queue: "Queue[bytes | None]"
    entities: "list[ESPHomeEntity]"
    available_wake_words: "dict[str, AvailableWakeWord]"
    wake_words: "dict[str, MicroWakeWord]"
    active_wake_words: set[str]
    stop_word: "MicroWakeWord"
    music_player: "AudioPlayer"
    tts_player: "AudioPlayer"
    wakeup_sound: str
    timer_finished_sound: str
    preferences: Preferences
    preferences_path: Path

    # Reachy Mini specific
    reachy_mini: object
    motion_enabled: bool = True
    motion: object | None = None  # ReachyMiniMotion instance

    media_player_entity: "MediaPlayerEntity | None" = None
    satellite: "VoiceSatelliteProtocol | None" = None
    wake_words_changed: bool = False
    wake_word_1_threshold: float = 0.7
    wake_word_2_threshold: float = 0.7
    stop_word_threshold: float = 0.5
    refractory_seconds: float = 2.0
    timer_max_ring_seconds: float = 900.0
    audio_input_channels: int = 1
    _entities_initialized: bool = False

    _services_suspended: bool = False

    # Mute state (controlled from Home Assistant) - thread-safe via properties
    _is_muted: bool = False

    # Thread safety
    _state_lock: "threading.Lock | None" = None

    def __post_init__(self):
        """Initialize state lock after dataclass creation."""
        import threading

        object.__setattr__(self, "_state_lock", threading.Lock())

    @property
    def services_suspended(self) -> bool:
        """Thread-safe getter for services_suspended."""
        if self._state_lock is None:
            return self._services_suspended
        with self._state_lock:
            return self._services_suspended

    @services_suspended.setter
    def services_suspended(self, value: bool) -> None:
        """Thread-safe setter for services_suspended."""
        if self._state_lock is None:
            object.__setattr__(self, "_services_suspended", value)
        else:
            with self._state_lock:
                object.__setattr__(self, "_services_suspended", value)

    @property
    def is_muted(self) -> bool:
        """Thread-safe getter for is_muted."""
        if self._state_lock is None:
            return self._is_muted
        with self._state_lock:
            return self._is_muted

    @is_muted.setter
    def is_muted(self, value: bool) -> None:
        """Thread-safe setter for is_muted."""
        if self._state_lock is None:
            object.__setattr__(self, "_is_muted", value)
        else:
            with self._state_lock:
                object.__setattr__(self, "_is_muted", value)

    def save_preferences(self) -> None:
        """Save preferences as JSON."""
        _LOGGER.debug("Saving preferences: %s", self.preferences_path)
        self.preferences_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.preferences_path, "w", encoding="utf-8") as preferences_file:
            json.dump(asdict(self.preferences), preferences_file, ensure_ascii=False, indent=4)
