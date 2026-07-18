"""Entity setup helpers for runtime/control related entities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .entity import NumberEntity
from .entity_extensions import SwitchEntity
from .entity_keys import get_entity_key

if TYPE_CHECKING:
    from .entity_registry import EntityRegistry

_LOGGER = logging.getLogger(__name__)


def setup_runtime_entities(registry: EntityRegistry, entities: list) -> None:
    def get_wake_word_1_sensitivity() -> float:
        return float(registry._get_server_state().wake_word_1_threshold)

    def set_wake_word_1_sensitivity(value: float) -> None:
        state = registry._get_server_state()
        state.wake_word_1_threshold = float(value)
        state.preferences.wake_word_1_sensitivity = float(value)
        state.save_preferences()

    def get_wake_word_2_sensitivity() -> float:
        return float(registry._get_server_state().wake_word_2_threshold)

    def set_wake_word_2_sensitivity(value: float) -> None:
        state = registry._get_server_state()
        state.wake_word_2_threshold = float(value)
        state.preferences.wake_word_2_sensitivity = float(value)
        state.save_preferences()

    def get_stop_word_sensitivity() -> float:
        return float(registry._get_server_state().stop_word_threshold)

    def set_stop_word_sensitivity(value: float) -> None:
        state = registry._get_server_state()
        state.stop_word_threshold = float(value)
        state.preferences.stop_word_sensitivity = float(value)
        state.save_preferences()

    entities.append(
        NumberEntity(
            server=registry.server,
            key=get_entity_key("wake_word_1_sensitivity"),
            name="Wake Word 1 Sensitivity",
            object_id="wake_word_1_sensitivity",
            min_value=0.0,
            max_value=1.0,
            step=0.001,
            icon="mdi:microphone-question",
            mode=1,
            entity_category=1,
            value_getter=get_wake_word_1_sensitivity,
            value_setter=set_wake_word_1_sensitivity,
        )
    )
    entities.append(
        NumberEntity(
            server=registry.server,
            key=get_entity_key("wake_word_2_sensitivity"),
            name="Wake Word 2 Sensitivity",
            object_id="wake_word_2_sensitivity",
            min_value=0.0,
            max_value=1.0,
            step=0.001,
            icon="mdi:microphone-question",
            mode=1,
            entity_category=1,
            value_getter=get_wake_word_2_sensitivity,
            value_setter=set_wake_word_2_sensitivity,
        )
    )
    entities.append(
        NumberEntity(
            server=registry.server,
            key=get_entity_key("stop_word_sensitivity"),
            name="Stop Word Sensitivity",
            object_id="stop_word_sensitivity",
            min_value=0.0,
            max_value=1.0,
            step=0.001,
            icon="mdi:microphone-off",
            mode=1,
            entity_category=1,
            value_getter=get_stop_word_sensitivity,
            value_setter=set_stop_word_sensitivity,
        )
    )

    def get_muted() -> bool:
        state = registry._get_server_state()
        return bool(state.is_muted)

    def set_muted(muted: bool) -> None:
        state = registry._get_server_state()
        state.is_muted = muted
        voice_assistant = registry.server._voice_assistant_service
        if muted:
            voice_assistant._suspend_voice_services(reason="mute")
        else:
            voice_assistant._resume_voice_services(reason="mute")

    entities.append(
        SwitchEntity(
            server=registry.server,
            key=get_entity_key("mute"),
            name="Mute",
            object_id="mute",
            icon="mdi:microphone-off",
            entity_category=1,
            value_getter=get_muted,
            value_setter=set_muted,
        )
    )

    _LOGGER.debug("Phase 1 entities registered")


def setup_conversation_entities(registry: EntityRegistry, entities: list) -> None:
    entities.append(
        SwitchEntity(
            server=registry.server,
            key=get_entity_key("continuous_conversation"),
            name="Continuous Conversation",
            object_id="continuous_conversation",
            icon="mdi:message-reply-text",
            device_class="switch",
            entity_category=1,
            value_getter=lambda: registry._get_pref_bool("continuous_conversation"),
            value_setter=lambda enabled: registry._set_pref_bool("continuous_conversation", enabled),
        )
    )
    _LOGGER.debug("Behavior entities registered")
