import math
import types
import unittest

from reachy_mini_ha_voice.protocol import motion_bridge


class MotionBridgeDOATests(unittest.TestCase):
    def _protocol_for_doa(self, angle_deg: float):
        calls = []
        controller = types.SimpleNamespace(get_doa_angle=lambda: (math.radians(angle_deg), True))
        movement_manager = types.SimpleNamespace(turn_to_angle=lambda yaw, duration: calls.append((yaw, duration)))
        protocol = types.SimpleNamespace(
            reachy_controller=controller,
            state=types.SimpleNamespace(
                motion_enabled=True,
                motion=types.SimpleNamespace(movement_manager=movement_manager),
            ),
        )
        return protocol, calls

    def test_wakeup_doa_uses_more_sensitive_turning(self):
        protocol, calls = self._protocol_for_doa(60.0)

        motion_bridge.turn_to_sound_source(protocol)

        self.assertEqual(len(calls), 1)
        yaw, duration = calls[0]
        self.assertAlmostEqual(yaw, 30.0)
        self.assertAlmostEqual(duration, 0.65)

    def test_wakeup_doa_uses_dynamic_duration_for_large_turns(self):
        protocol, calls = self._protocol_for_doa(0.0)

        motion_bridge.turn_to_sound_source(protocol)

        self.assertEqual(len(calls), 1)
        yaw, duration = calls[0]
        self.assertAlmostEqual(yaw, 90.0)
        self.assertAlmostEqual(duration, 1.2)

    def test_wakeup_doa_skips_only_under_six_degrees(self):
        protocol, calls = self._protocol_for_doa(85.0)

        motion_bridge.turn_to_sound_source(protocol)

        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
