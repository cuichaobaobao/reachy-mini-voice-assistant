"""Entity registry for ESPHome entities.

This module handles the registration and management of all ESPHome entities
for the Reachy Mini voice assistant.
"""

import logging

from ..models import Preferences
from .runtime_entity_setup import (
    setup_conversation_entities,
    setup_runtime_entities,
)

_LOGGER = logging.getLogger(__name__)


class EntityRegistry:
    """Registry for managing ESPHome entities."""

    def __init__(
        self,
        server,
    ):
        """Initialize the voice-satellite entity registry."""
        self.server = server

    def _get_preferences(self) -> Preferences | None:
        return self.server.state.preferences

    def _get_server_state(self):
        return self.server.state

    def _save_preferences(self) -> None:
        self.server.state.save_preferences()

    def _set_preference_and_save(self, key: str, value) -> None:
        prefs = self._get_preferences()
        if prefs is not None:
            setattr(prefs, key, value)
            self._save_preferences()

    def _get_pref_bool(self, key: str, default: bool = False) -> bool:
        prefs = self._get_preferences()
        return bool(getattr(prefs, key, default)) if prefs is not None else default

    def _set_pref_bool(self, key: str, enabled: bool) -> None:
        prefs = self._get_preferences()
        if prefs is not None:
            setattr(prefs, key, bool(enabled))
            self._save_preferences()

    def setup_all_entities(self, entities: list) -> None:
        """Register voice-satellite settings only.

        Robot controls, state diagnostics, camera, and recorded moves belong
        to the official Reachy Mini Home Assistant integration.
        """
        setup_runtime_entities(self, entities)
        setup_conversation_entities(self, entities)

        _LOGGER.info("All entities registered: %d total", len(entities))
