import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch

from reachy_mini_ha_voice.motion import animation_player as animation_player_module
from reachy_mini_ha_voice.motion.animation_player import AnimationPlayer
from reachy_mini_ha_voice.motion.state_machine import (
    IDLE_BREATHING_FREQUENCY_HZ,
    OFFICIAL_BREATHING_ANTENNA_FREQUENCY_HZ,
    OFFICIAL_BREATHING_Z_AMPLITUDE_M,
)


class _Clock:
    def __init__(self, value: float = 0.0):
        self.value = value

    def perf_counter(self) -> float:
        return self.value


class OfficialIdleBreathingTests(unittest.TestCase):
    def test_idle_animation_layer_matches_official_breathing_formula(self):
        clock = _Clock(100.0)
        with patch.object(animation_player_module.time, "perf_counter", clock.perf_counter):
            player = AnimationPlayer()
            self.assertTrue(player.set_animation("idle"))

            clock.value += player._transition_duration + player._interpolation_duration
            player.get_offsets()
            clock.value += 0.25
            offsets = player.get_offsets()

        elapsed = player._transition_duration + player._interpolation_duration + 0.25
        expected_z = OFFICIAL_BREATHING_Z_AMPLITUDE_M * math.sin(2.0 * math.pi * IDLE_BREATHING_FREQUENCY_HZ * elapsed)
        expected_sway = 0.262 * math.sin(2.0 * math.pi * OFFICIAL_BREATHING_ANTENNA_FREQUENCY_HZ * elapsed)

        self.assertAlmostEqual(offsets["z"], expected_z)
        self.assertAlmostEqual(offsets["antenna_left"], expected_sway)
        self.assertAlmostEqual(offsets["antenna_right"], -expected_sway)

    def test_voice_state_animation_crossfades_without_zero_interpolation(self):
        clock = _Clock(100.0)
        with (
            patch.object(animation_player_module.time, "perf_counter", clock.perf_counter),
            patch.object(animation_player_module.random, "random", return_value=0.0),
        ):
            player = AnimationPlayer()
            player._current_animation = "listening"
            player._target_animation = "listening"
            player._last_offsets = player._zero_offsets()
            player._last_offsets["pitch"] = 0.1

            self.assertTrue(player.set_animation("thinking"))
            self.assertFalse(player._in_interpolation)

            clock.value += player._transition_duration / 2.0
            offsets = player.get_offsets()

        self.assertGreater(offsets["pitch"], 0.03)

    def test_speaking_head_motion_is_audio_driven_only(self):
        config = json.loads(Path("reachy_mini_ha_voice/animations/conversation_animations.json").read_text())
        speaking = config["animations"]["speaking"]

        self.assertEqual(speaking["antenna_move_name"], "wiggle")
        self.assertAlmostEqual(speaking["pitch_amplitude_rad"], 0.0)
        self.assertAlmostEqual(speaking["yaw_amplitude_rad"], 0.0)
        self.assertAlmostEqual(speaking["roll_amplitude_rad"], 0.0)
        self.assertAlmostEqual(speaking["z_amplitude_m"], 0.0)
        self.assertAlmostEqual(speaking["antenna_amplitude_rad"], 0.35)
        self.assertAlmostEqual(speaking["antenna_frequency_hz"], 0.32)
        self.assertAlmostEqual(speaking["frequency_hz"], 0.32)

    def test_disabled_idle_rest_pose_uses_historical_sleep_posture(self):
        config = json.loads(Path("reachy_mini_ha_voice/animations/conversation_animations.json").read_text())
        rest = config["idle_rest_pose"]

        self.assertAlmostEqual(rest["pitch_deg"], 16.0)
        self.assertAlmostEqual(rest["antenna_left_rad"], 3.05)
        self.assertAlmostEqual(rest["antenna_right_rad"], -3.05)


if __name__ == "__main__":
    unittest.main()
