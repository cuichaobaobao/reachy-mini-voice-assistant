"""Entity key definitions for ESPHome entities.

This module provides consistent entity key mappings for all HA entities.
Keys are fixed to ensure consistency across restarts.
"""

import logging

logger = logging.getLogger(__name__)


# Fixed entity key mapping - ensures consistent keys across restarts
# Keys are based on phase/category organization
ENTITY_KEYS: dict[str, int] = {
    # Media player (key 0 reserved)
    "reachy_mini_media_player": 0,
    # Voice satellite settings (100-199)
    "mute": 102,
    "wake_word_1_sensitivity": 105,
    "wake_word_2_sensitivity": 106,
    "stop_word_sensitivity": 107,
    # Conversation settings (1500-1599)
    "continuous_conversation": 1500,
}


def get_entity_key(object_id: str) -> int:
    """Get a consistent entity key for the given object_id.

    Args:
        object_id: The entity's object ID

    Returns:
        Integer key for the entity
    """
    if object_id in ENTITY_KEYS:
        return ENTITY_KEYS[object_id]

    # Fallback: generate key from hash (should not happen if all entities are registered)
    logger.warning("Entity key not found for %s, generating from hash", object_id)
    return abs(hash(object_id)) % 10000 + 2000


def register_entity_key(object_id: str, key: int) -> None:
    """Register a new entity key.

    Args:
        object_id: The entity's object ID
        key: The key to assign
    """
    if object_id in ENTITY_KEYS:
        logger.warning("Overwriting existing key for %s", object_id)
    ENTITY_KEYS[object_id] = key


def get_next_available_key(phase: int = 2000) -> int:
    """Get the next available key in a phase range.

    Args:
        phase: The phase base (e.g., 2000 for phase 26+)

    Returns:
        Next available key in the range
    """
    phase_keys = [k for k in ENTITY_KEYS.values() if phase <= k < phase + 100]
    if not phase_keys:
        return phase
    return max(phase_keys) + 1
