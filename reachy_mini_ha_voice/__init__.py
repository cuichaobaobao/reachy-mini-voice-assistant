"""
Reachy Mini Voice Assistant

A deep integration app combining Reachy Mini robot with Home Assistant,
enabling voice control, smart home automation, and expressive robot interactions.

Key features:
- Local wake word detection (MicroWakeWord)
- ESPHome protocol for seamless Home Assistant communication
- STT/TTS powered by Home Assistant voice pipeline
- Reachy Mini motion control with expressive animations
- Smart home entity control through natural voice commands
"""

try:
    from importlib.metadata import version

    __version__ = version("reachy-mini-ha-voice")
except Exception:
    __version__ = "0.0.0"  # Fallback for development
__author__ = "Reachy Mini Voice Assistant"

# Don't import main module here to avoid runpy warning
# The app is loaded via entry point: reachy_mini_ha_voice.main:ReachyMiniHaVoice

__all__ = [
    "__version__",
]
