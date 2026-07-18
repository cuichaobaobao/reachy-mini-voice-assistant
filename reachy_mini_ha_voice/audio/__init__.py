"""Audio module for Reachy Mini.

This module handles all audio-related functionality:
- AudioPlayer: Audio playback through the Reachy Mini media system
- DOATracker: Direction of Arrival sound localization
"""

from .audio_player import AudioPlayer
from .doa_tracker import DOAConfig, DOATracker

__all__ = [
    "AudioPlayer",
    "DOAConfig",
    "DOATracker",
]
