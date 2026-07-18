"""Voice-satellite entities for Home Assistant."""

from .entity import BinarySensorEntity, ESPHomeEntity, MediaPlayerEntity, NumberEntity, TextSensorEntity
from .entity_extensions import ButtonEntity, SelectEntity, SensorEntity, SwitchEntity
from .entity_keys import ENTITY_KEYS, get_entity_key, get_next_available_key, register_entity_key
from .entity_registry import EntityRegistry

__all__ = [
    "ENTITY_KEYS",
    "BinarySensorEntity",
    "ButtonEntity",
    "ESPHomeEntity",
    "EntityRegistry",
    "MediaPlayerEntity",
    "NumberEntity",
    "SelectEntity",
    "SensorEntity",
    "SwitchEntity",
    "TextSensorEntity",
    "get_entity_key",
    "get_next_available_key",
    "register_entity_key",
]
