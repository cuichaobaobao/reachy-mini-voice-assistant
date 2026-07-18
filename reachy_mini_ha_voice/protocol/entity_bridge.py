"""Entity and Home Assistant bridge helpers for `VoiceSatelliteProtocol`."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..entities.entity import MediaPlayerEntity
from ..entities.entity_keys import get_entity_key
from ..entities.entity_registry import EntityRegistry

if TYPE_CHECKING:
    from aioesphomeapi.api_pb2 import HomeAssistantStateResponse  # type: ignore[attr-defined]

    from .satellite import VoiceSatelliteProtocol

_LOGGER = logging.getLogger(__name__)


def create_entity_registry(protocol: VoiceSatelliteProtocol) -> EntityRegistry:
    return EntityRegistry(
        server=protocol,
    )


def initialize_entities(protocol: VoiceSatelliteProtocol) -> None:
    try:
        _LOGGER.info("Checking entity initialization state...")
        if not protocol.state._entities_initialized:
            _LOGGER.info("Setting up entities for first time...")
            if protocol.state.media_player_entity is None:
                _LOGGER.info("Creating MediaPlayerEntity...")
                protocol.state.media_player_entity = MediaPlayerEntity(
                    server=protocol,
                    key=get_entity_key("reachy_mini_media_player"),
                    name="Media Player",
                    object_id="reachy_mini_media_player",
                    music_player=protocol.state.music_player,
                    announce_player=protocol.state.tts_player,
                )
                protocol.state.entities.append(protocol.state.media_player_entity)
                _LOGGER.info("MediaPlayerEntity created")

            _LOGGER.info("Setting up all entities via registry...")
            protocol._entity_registry.setup_all_entities(protocol.state.entities)
            protocol.state._entities_initialized = True
            _LOGGER.info("Entities initialized: %d total", len(protocol.state.entities))
        else:
            _LOGGER.info("Entities already initialized, updating server references")
            for entity in protocol.state.entities:
                entity.server = protocol
            _LOGGER.info("Server references updated for %d entities", len(protocol.state.entities))
    except Exception as e:
        _LOGGER.error("Error during entity setup: %s", e, exc_info=True)
        raise


def on_authenticated(protocol: VoiceSatelliteProtocol) -> None:
    for entity in protocol.state.entities:
        try:
            entity.update_state()
        except Exception as e:
            _LOGGER.debug("Failed to replay state for %s: %s", getattr(entity, "object_id", entity), e)


def handle_ha_state_change(protocol: VoiceSatelliteProtocol, msg: HomeAssistantStateResponse) -> None:
    # State subscriptions are not used for robot control. Home Assistant
    # automations should target the official Reachy Mini integration instead.
    _LOGGER.debug("Ignoring external HA state update: %s", msg.entity_id)


def schedule_ha_connected_callback(protocol: VoiceSatelliteProtocol) -> None:
    if protocol._on_ha_connected_callback:
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(protocol._on_ha_connected_callback())
            _ = task
        except Exception as e:
            _LOGGER.error("Error in HA connected callback: %s", e)


def run_ha_disconnected_callback(protocol: VoiceSatelliteProtocol) -> None:
    if protocol._on_ha_disconnected_callback:
        try:
            protocol._on_ha_disconnected_callback()
        except Exception as e:
            _LOGGER.error("Error in HA disconnected callback: %s", e)
