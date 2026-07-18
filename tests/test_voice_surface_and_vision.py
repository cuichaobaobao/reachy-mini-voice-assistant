import importlib.util
import io
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class VoiceSurfaceTests(unittest.TestCase):
    def test_esphome_surface_only_contains_voice_settings(self):
        registry = read_source("reachy_mini_ha_voice/entities/entity_registry.py")
        runtime = read_source("reachy_mini_ha_voice/entities/runtime_entity_setup.py")

        self.assertIn("setup_runtime_entities(self, entities)", registry)
        self.assertIn("setup_conversation_entities(self, entities)", registry)
        self.assertNotIn("setup_motion_entities", registry)
        self.assertNotIn("setup_audio_direction_entities", registry)
        self.assertNotIn("setup_robot_info_entities", registry)
        self.assertNotIn("Speaker Volume", runtime)
        self.assertNotIn("Idle Behavior", runtime)
        self.assertNotIn('name="Emotion"', runtime)

    def test_robot_controls_are_delegated_to_official_integration(self):
        controller = read_source("reachy_mini_ha_voice/reachy_controller.py")
        bridge = read_source("reachy_mini_ha_voice/protocol/entity_bridge.py")

        self.assertIn("Minimal read-only controller", controller)
        self.assertIn("get_DoA", controller)
        self.assertNotIn("set_motor_mode", controller)
        self.assertNotIn("set_head_yaw", controller)
        self.assertIn("not used for robot control", bridge)


class VisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        module_path = ROOT / "reachy_mini_ha_voice/vision.py"
        spec = importlib.util.spec_from_file_location("voice_vision", module_path)
        assert spec and spec.loader
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_jpeg_source_caches_sdk_frames(self):
        calls = []
        media = types.SimpleNamespace(get_frame_jpeg=lambda: calls.append(True) or b"jpeg")
        source = self.module.CameraFrameSource(types.SimpleNamespace(media=media), refresh_hz=5.0)

        self.assertTrue(source.available)
        self.assertEqual(source.capture(force=True), b"jpeg")
        self.assertEqual(source.capture(), b"jpeg")
        self.assertEqual(len(calls), 1)

    def test_jpeg_source_does_not_access_sdk_when_disabled(self):
        calls = []
        media = types.SimpleNamespace(get_frame_jpeg=lambda: calls.append(True) or b"jpeg")
        source = self.module.CameraFrameSource(types.SimpleNamespace(media=media), enabled=False)

        self.assertFalse(source.available)
        self.assertIsNone(source.capture(force=True))
        self.assertEqual(calls, [])

    def test_face_tracking_is_private_and_voice_phase_limited(self):
        movement = read_source("reachy_mini_ha_voice/motion/movement_manager.py")
        commands = read_source("reachy_mini_ha_voice/motion/command_runtime.py")

        self.assertIn("self._face_tracking_enabled", movement)
        self.assertIn("RobotState.LISTENING", movement)
        self.assertIn("RobotState.THINKING", movement)
        self.assertIn("start_head_tracking(weight=1.0)", movement)
        self.assertIn("stop_head_tracking()", movement)
        self.assertIn('cmd == "set_face_tracking_enabled"', commands)

    def test_face_tracking_starts_and_stops_with_voice_states(self):
        from reachy_mini_ha_voice.motion.movement_manager import MovementManager
        from reachy_mini_ha_voice.motion.state_machine import RobotState

        class Robot:
            def __init__(self):
                self.calls = []

            def start_head_tracking(self, *, weight: float) -> None:
                self.calls.append(("start", weight))

            def stop_head_tracking(self) -> None:
                self.calls.append(("stop", None))

        robot = Robot()
        manager = MovementManager(robot)
        manager._face_tracking_enabled = True

        manager.state.robot_state = RobotState.LISTENING
        manager._sync_face_tracking()
        manager.state.robot_state = RobotState.THINKING
        manager._sync_face_tracking()
        manager.state.robot_state = RobotState.SPEAKING
        manager._sync_face_tracking()

        self.assertEqual(robot.calls, [("start", 1.0), ("stop", None)])

    def test_doa_helper_is_read_only(self):
        module_path = ROOT / "reachy_mini_ha_voice/reachy_controller.py"
        spec = importlib.util.spec_from_file_location("voice_controller", module_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        media = types.SimpleNamespace(get_DoA=lambda: (1.25, True))
        controller = module.ReachyController(types.SimpleNamespace(media=media))
        self.assertEqual(controller.get_doa_angle(), (1.25, True))

    def test_runtime_wake_word_loading_is_limited_and_quiet(self):
        from reachy_mini_ha_voice.voice_assistant import VoiceAssistantService

        service = VoiceAssistantService(types.SimpleNamespace())
        output = io.StringIO()
        with redirect_stdout(output):
            available = service._load_available_wake_words()
            stop_model = service._load_stop_model()

        self.assertEqual(set(available), {"okay_nabu", "hey_mycroft", "hey_jarvis"})
        self.assertEqual(stop_model.id, "stop")
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
