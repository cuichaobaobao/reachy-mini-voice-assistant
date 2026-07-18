"""Animation player for conversation state animations.

This module provides a JSON-driven animation system for Reachy Mini,
inspired by SimpleDances project and reachy_mini_conversation_app.

Animations are defined as periodic oscillations that can be layered
on top of other movements. The speaking animation uses multi-frequency
oscillators for more natural head sway.
"""

import logging
import math
import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from ..animations.animation_config import load_animation_config

_LOGGER = logging.getLogger(__name__)

_MODULE_DIR = Path(__file__).parent
_PACKAGE_DIR = _MODULE_DIR.parent  # reachy_mini_ha_voice/
_ANIMATIONS_FILE = _PACKAGE_DIR / "animations" / "conversation_animations.json"


@dataclass
class AnimationParams:
    """Parameters for a single animation with per-axis frequencies."""

    name: str
    description: str
    # Position amplitudes (meters)
    x_amplitude_m: float = 0.0
    y_amplitude_m: float = 0.0
    z_amplitude_m: float = 0.0
    # Position offsets (meters)
    x_offset_m: float = 0.0
    y_offset_m: float = 0.0
    z_offset_m: float = 0.0
    # Orientation amplitudes (radians)
    roll_amplitude_rad: float = 0.0
    pitch_amplitude_rad: float = 0.0
    yaw_amplitude_rad: float = 0.0
    # Orientation offsets (radians)
    roll_offset_rad: float = 0.0
    pitch_offset_rad: float = 0.0
    yaw_offset_rad: float = 0.0
    # Antenna
    antenna_amplitude_rad: float = 0.0
    antenna_move_name: str = "both"
    antenna_frequency_hz: float = 0.0  # If not specified, uses main frequency_hz
    # Per-axis frequencies (Hz) - if not specified, uses main frequency_hz
    frequency_hz: float = 0.5
    pitch_frequency_hz: float = 0.0
    yaw_frequency_hz: float = 0.0
    roll_frequency_hz: float = 0.0
    x_frequency_hz: float = 0.0
    y_frequency_hz: float = 0.0
    z_frequency_hz: float = 0.0
    # Phase offset for variation
    phase_offset: float = 0.0


class AnimationPlayer:
    """Plays JSON-defined animations for conversation states.

    Features:
    - Multi-frequency oscillators for natural motion
    - Random phase offsets per animation start for variation
    - Smooth transitions between animations
    - Crossfade from the current animation offsets into the next animation
      without forcing a neutral zero-offset step between voice states.
    """

    def __init__(self):
        self._animations: dict[str, AnimationParams] = {}
        self._amplitude_scale: float = 1.0
        self._transition_duration: float = 0.3
        self._interpolation_duration: float = 0.2
        self._current_animation: str | None = None
        self._target_animation: str | None = None
        self._transition_start: float = 0.0
        self._phase_start: float = 0.0
        self._lock = threading.Lock()
        # Random phase offsets for each axis (regenerated on animation change)
        self._phase_pitch: float = 0.0
        self._phase_yaw: float = 0.0
        self._phase_roll: float = 0.0
        self._phase_x: float = 0.0
        self._phase_y: float = 0.0
        self._phase_z: float = 0.0
        # Transition state (for smooth crossfade between animation offsets)
        self._in_interpolation: bool = False
        self._interpolation_start_time: float = 0.0
        self._interpolation_start_offsets: dict[str, float] = {
            "pitch": 0.0,
            "yaw": 0.0,
            "roll": 0.0,
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "antenna_left": 0.0,
            "antenna_right": 0.0,
        }
        self._transition_start_offsets: dict[str, float] = self._interpolation_start_offsets.copy()
        self._last_offsets: dict[str, float] = {
            "pitch": 0.0,
            "yaw": 0.0,
            "roll": 0.0,
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "antenna_left": 0.0,
            "antenna_right": 0.0,
        }
        self._load_config()

    def _load_config(self) -> None:
        """Load animations and actions from JSON file."""
        if not _ANIMATIONS_FILE.exists():
            _LOGGER.warning("Animations file not found: %s", _ANIMATIONS_FILE)
            return
        try:
            data = load_animation_config(_ANIMATIONS_FILE)

            settings = data.get("settings", {})
            self._amplitude_scale = settings.get("amplitude_scale", 1.0)
            self._transition_duration = settings.get("transition_duration_s", 0.3)

            # Load animations
            animations = data.get("animations", {})
            for name, params in animations.items():
                self._animations[name] = AnimationParams(
                    name=name,
                    description=params.get("description", ""),
                    x_amplitude_m=params.get("x_amplitude_m", 0.0),
                    y_amplitude_m=params.get("y_amplitude_m", 0.0),
                    z_amplitude_m=params.get("z_amplitude_m", 0.0),
                    x_offset_m=params.get("x_offset_m", 0.0),
                    y_offset_m=params.get("y_offset_m", 0.0),
                    z_offset_m=params.get("z_offset_m", 0.0),
                    roll_amplitude_rad=params.get("roll_amplitude_rad", 0.0),
                    pitch_amplitude_rad=params.get("pitch_amplitude_rad", 0.0),
                    yaw_amplitude_rad=params.get("yaw_amplitude_rad", 0.0),
                    roll_offset_rad=params.get("roll_offset_rad", 0.0),
                    pitch_offset_rad=params.get("pitch_offset_rad", 0.0),
                    yaw_offset_rad=params.get("yaw_offset_rad", 0.0),
                    antenna_amplitude_rad=params.get("antenna_amplitude_rad", 0.0),
                    antenna_move_name=params.get("antenna_move_name", "both"),
                    antenna_frequency_hz=params.get("antenna_frequency_hz", 0.0),
                    frequency_hz=params.get("frequency_hz", 0.5),
                    pitch_frequency_hz=params.get("pitch_frequency_hz", 0.0),
                    yaw_frequency_hz=params.get("yaw_frequency_hz", 0.0),
                    roll_frequency_hz=params.get("roll_frequency_hz", 0.0),
                    x_frequency_hz=params.get("x_frequency_hz", 0.0),
                    y_frequency_hz=params.get("y_frequency_hz", 0.0),
                    z_frequency_hz=params.get("z_frequency_hz", 0.0),
                    phase_offset=params.get("phase_offset", 0.0),
                )

            _LOGGER.info("Loaded %d animations", len(self._animations))
        except Exception as e:
            _LOGGER.error("Failed to load animations: %s", e)

    def _randomize_phases(self) -> None:
        """Generate random phase offsets for natural variation."""
        self._phase_pitch = random.random() * 2 * math.pi
        self._phase_yaw = random.random() * 2 * math.pi
        self._phase_roll = random.random() * 2 * math.pi
        self._phase_x = random.random() * 2 * math.pi
        self._phase_y = random.random() * 2 * math.pi
        self._phase_z = random.random() * 2 * math.pi

    def set_animation(self, name: str) -> bool:
        """Set the current animation with smooth transition.

        The previous implementation always eased the active offsets back to
        zero before starting the next animation. That made voice-state changes
        visibly pause or jump. We instead crossfade from the current offsets
        directly into the next animation's oscillator.
        """
        with self._lock:
            if name not in self._animations and name is not None:
                _LOGGER.warning("Unknown animation: %s", name)
                return False
            if name == self._target_animation:
                return True
            if name == self._current_animation and name == self._target_animation:
                return True

            # Capture current offsets for transition start
            self._interpolation_start_offsets = self._last_offsets.copy()
            self._transition_start_offsets = self._last_offsets.copy()
            self._interpolation_start_time = time.perf_counter()
            self._in_interpolation = False

            self._target_animation = name
            self._transition_start = time.perf_counter()
            self._phase_start = self._transition_start
            # Randomize phases for new animation
            self._randomize_phases()
            _LOGGER.debug("Crossfading to animation: %s", name)
            return True

    def stop(self) -> None:
        """Stop all animations."""
        with self._lock:
            self._current_animation = None
            self._target_animation = None

    def get_offsets(self, dt: float = 0.0) -> dict[str, float]:
        """Calculate current animation offsets.

        Voice-state changes crossfade directly from the last visible offsets
        into the next animation so listening/thinking/speaking transitions do
        not force a short neutral pose between states.

        Each axis can have its own frequency for more organic movement.

        Args:
            dt: Delta time (unused, kept for API compatibility)

        Returns:
            Dict with keys: pitch, yaw, roll, x, y, z, antenna_left, antenna_right
        """
        with self._lock:
            now = time.perf_counter()

            # Handle transition to a new animation with a direct offset crossfade.
            if self._target_animation != self._current_animation:
                transition_elapsed = max(0.0, now - self._transition_start)
                progress = min(transition_elapsed / max(1e-6, self._transition_duration), 1.0)
                smooth_t = progress * progress * (3.0 - 2.0 * progress)
                target_offsets = self._zero_offsets()
                if self._target_animation is not None:
                    target_params = self._animations.get(self._target_animation)
                    if target_params is not None:
                        target_offsets = self._sample_animation_offsets(target_params, transition_elapsed)

                result = {
                    key: self._transition_start_offsets.get(key, 0.0) * (1.0 - smooth_t)
                    + target_offsets.get(key, 0.0) * smooth_t
                    for key in self._last_offsets
                }

                if progress >= 1.0:
                    self._current_animation = self._target_animation
                    self._phase_start = now - transition_elapsed
                    result = target_offsets

                self._last_offsets = result.copy()
                return result

            # No animation
            if self._current_animation is None:
                result = self._zero_offsets()
                self._last_offsets = result.copy()
                return result

            params = self._animations.get(self._current_animation)
            if params is None:
                result = self._zero_offsets()
                self._last_offsets = result.copy()
                return result

            elapsed = now - self._phase_start
            result = self._sample_animation_offsets(params, elapsed)
            self._last_offsets = result.copy()
            return result

    def _zero_offsets(self) -> dict[str, float]:
        return {
            "pitch": 0.0,
            "yaw": 0.0,
            "roll": 0.0,
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "antenna_left": 0.0,
            "antenna_right": 0.0,
        }

    def _sample_animation_offsets(self, params: AnimationParams, elapsed: float) -> dict[str, float]:
        base_freq = params.frequency_hz

        # Per-axis frequencies (fall back to base frequency if not specified)
        pitch_freq = params.pitch_frequency_hz if params.pitch_frequency_hz > 0 else base_freq
        yaw_freq = params.yaw_frequency_hz if params.yaw_frequency_hz > 0 else base_freq
        roll_freq = params.roll_frequency_hz if params.roll_frequency_hz > 0 else base_freq
        x_freq = params.x_frequency_hz if params.x_frequency_hz > 0 else base_freq
        y_freq = params.y_frequency_hz if params.y_frequency_hz > 0 else base_freq
        z_freq = params.z_frequency_hz if params.z_frequency_hz > 0 else base_freq

        pitch = params.pitch_offset_rad + params.pitch_amplitude_rad * math.sin(
            2 * math.pi * pitch_freq * elapsed + self._phase_pitch
        )

        yaw = params.yaw_offset_rad + params.yaw_amplitude_rad * math.sin(
            2 * math.pi * yaw_freq * elapsed + self._phase_yaw
        )

        roll = params.roll_offset_rad + params.roll_amplitude_rad * math.sin(
            2 * math.pi * roll_freq * elapsed + self._phase_roll
        )

        x = params.x_offset_m + params.x_amplitude_m * math.sin(2 * math.pi * x_freq * elapsed + self._phase_x)

        y = params.y_offset_m + params.y_amplitude_m * math.sin(2 * math.pi * y_freq * elapsed + self._phase_y)

        z_phase = 0.0 if params.name == "idle" else self._phase_z
        z = params.z_offset_m + params.z_amplitude_m * math.sin(2 * math.pi * z_freq * elapsed + z_phase)

        # Antenna movement with its own frequency
        antenna_freq = params.antenna_frequency_hz if params.antenna_frequency_hz > 0 else base_freq
        antenna_phase = 2 * math.pi * antenna_freq * elapsed
        if params.antenna_move_name == "both":
            left = right = params.antenna_amplitude_rad * math.sin(antenna_phase)
        elif params.antenna_move_name == "wiggle":
            left = params.antenna_amplitude_rad * math.sin(antenna_phase)
            right = params.antenna_amplitude_rad * math.sin(antenna_phase + math.pi)
        else:
            left = params.antenna_amplitude_rad * math.sin(antenna_phase)
            right = params.antenna_amplitude_rad * math.sin(antenna_phase + math.pi / 2)

        scale = self._amplitude_scale
        return {
            "pitch": pitch * scale,
            "yaw": yaw * scale,
            "roll": roll * scale,
            "x": x * scale,
            "y": y * scale,
            "z": z * scale,
            "antenna_left": left * scale,
            "antenna_right": right * scale,
        }

    @property
    def current_animation(self) -> str | None:
        """Get the current animation name."""
        with self._lock:
            return self._current_animation

    @property
    def available_animations(self) -> list:
        """Get list of available animation names."""
        return list(self._animations.keys())
