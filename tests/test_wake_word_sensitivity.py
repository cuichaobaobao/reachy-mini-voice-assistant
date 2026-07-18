import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class WakeWordSensitivitySourceTests(unittest.TestCase):
    def test_ohf_style_sensitivity_entities_are_registered(self):
        content = read_source("reachy_mini_ha_voice/entities/runtime_entity_setup.py")

        self.assertIn('name="Wake Word 1 Sensitivity"', content)
        self.assertIn('object_id="wake_word_1_sensitivity"', content)
        self.assertIn('name="Wake Word 2 Sensitivity"', content)
        self.assertIn('object_id="wake_word_2_sensitivity"', content)
        self.assertIn('name="Stop Word Sensitivity"', content)
        self.assertIn('object_id="stop_word_sensitivity"', content)
        self.assertIn("min_value=0.0", content)
        self.assertIn("max_value=1.0", content)
        self.assertIn("step=0.001", content)
        self.assertIn("entity_category=1", content)

    def test_wake_word_defaults_and_preferences_match_ohf_pattern(self):
        models = read_source("reachy_mini_ha_voice/models.py")
        voice_assistant = read_source("reachy_mini_ha_voice/voice_assistant.py")

        self.assertIn("probability_cutoff: float = 0.7", models)
        self.assertIn("wake_word_1_sensitivity: float | None = None", models)
        self.assertIn("wake_word_2_sensitivity: float | None = None", models)
        self.assertIn("stop_word_sensitivity: float | None = None", models)
        self.assertIn("wake_word_1_threshold: float = 0.7", models)
        self.assertIn("wake_word_2_threshold: float = 0.7", models)
        self.assertIn("stop_word_threshold: float = 0.5", models)

        self.assertIn("config.get(model_type.value, {})", voice_assistant)
        self.assertIn('type_config.get("probability_cutoff", default)', voice_assistant)
        self.assertIn("self._restore_wake_word_thresholds(self._state)", voice_assistant)

    def test_detection_applies_runtime_probability_cutoffs(self):
        content = read_source("reachy_mini_ha_voice/voice_assistant.py")

        self.assertIn("for wake_word_index, wake_word in enumerate(ctx.wake_words):", content)
        self.assertIn("wake_word.probability_cutoff = (", content)
        self.assertIn("self._state.wake_word_1_threshold", content)
        self.assertIn("self._state.wake_word_2_threshold", content)
        self.assertIn("self._state.stop_word.probability_cutoff = self._state.stop_word_threshold", content)

    def test_active_wake_word_slot_order_is_preserved(self):
        voice_assistant = read_source("reachy_mini_ha_voice/voice_assistant.py")
        message_dispatch = read_source("reachy_mini_ha_voice/protocol/message_dispatch.py")

        self.assertIn("def _active_wake_word_ids_in_slot_order", voice_assistant)
        self.assertIn("for wake_word_id in state.preferences.active_wake_words", voice_assistant)
        self.assertIn("ordered_ids[:2]", voice_assistant)
        self.assertIn("active_wake_word_ids: list[str] = []", message_dispatch)
        self.assertIn("protocol.state.preferences.active_wake_words = active_wake_word_ids", message_dispatch)
