"""Motion bridge helpers for `VoiceSatelliteProtocol`."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .satellite import VoiceSatelliteProtocol

_LOGGER = logging.getLogger(__name__)

DOA_WAKE_MIN_YAW_DEG = 6.0
DOA_WAKE_TURN_SCALE = 1.0
DOA_WAKE_MIN_TURN_DURATION_S = 0.65
DOA_WAKE_MAX_TURN_DURATION_S = 1.25
DOA_WAKE_TURN_RATE_DEG_S = 75.0


def _wake_turn_duration_s(target_yaw_deg: float) -> float:
    if not math.isfinite(target_yaw_deg):
        return DOA_WAKE_MIN_TURN_DURATION_S
    turn_duration = abs(target_yaw_deg) / DOA_WAKE_TURN_RATE_DEG_S
    return max(DOA_WAKE_MIN_TURN_DURATION_S, min(DOA_WAKE_MAX_TURN_DURATION_S, turn_duration))


def turn_to_sound_source(protocol: VoiceSatelliteProtocol) -> None:
    if not protocol.state.motion_enabled:
        _LOGGER.info("DOA turn-to-sound: motion disabled")
        return
    try:
        doa = protocol.reachy_controller.get_doa_angle()
        if doa is None:
            _LOGGER.info("DOA not available, skipping turn-to-sound")
            return
        angle_rad, speech_detected = doa
        _LOGGER.debug("DOA raw: angle=%.3f rad (%.1f°), speech=%s", angle_rad, math.degrees(angle_rad), speech_detected)
        dir_x = math.sin(angle_rad)
        dir_y = math.cos(angle_rad)
        yaw_rad = -(angle_rad - math.pi / 2)
        yaw_deg = math.degrees(yaw_rad)
        _LOGGER.debug("DOA direction: x=%.2f, y=%.2f, yaw=%.1f°", dir_x, dir_y, yaw_deg)
        if abs(yaw_deg) < DOA_WAKE_MIN_YAW_DEG:
            _LOGGER.debug(
                "DOA angle %.1f° below threshold (%.1f°), skipping turn",
                yaw_deg,
                DOA_WAKE_MIN_YAW_DEG,
            )
            return
        target_yaw_deg = yaw_deg * DOA_WAKE_TURN_SCALE
        turn_duration = _wake_turn_duration_s(target_yaw_deg)
        _LOGGER.info(
            "Turning toward sound source: DOA=%.1f°, target=%.1f°, duration=%.2fs",
            yaw_deg,
            target_yaw_deg,
            turn_duration,
        )
        if protocol.state.motion and protocol.state.motion.movement_manager:
            protocol.state.motion.movement_manager.turn_to_angle(target_yaw_deg, duration=turn_duration)
    except Exception as e:
        _LOGGER.error("Error in turn-to-sound: %s", e)


def reachy_on_listening(protocol: VoiceSatelliteProtocol) -> None:
    enter_motion_state(protocol, "listening", "on_listening")


def reachy_on_thinking(protocol: VoiceSatelliteProtocol) -> None:
    enter_motion_state(protocol, "thinking", "on_thinking")


def reachy_on_speaking(protocol: VoiceSatelliteProtocol) -> None:
    enter_motion_state(protocol, "speaking", "on_speaking_start")


def reachy_on_idle(protocol: VoiceSatelliteProtocol) -> None:
    run_motion_state(protocol, "idle", "on_idle")


def reachy_on_timer_finished(protocol: VoiceSatelliteProtocol) -> None:
    run_motion_state(protocol, "timer_finished", "on_timer_finished")


def play_emotion(protocol: VoiceSatelliteProtocol, emotion_name: str) -> None:
    queue_emotion_move(protocol, emotion_name)


def queue_emotion_move(protocol: VoiceSatelliteProtocol, emotion_name: str) -> None:
    try:
        if protocol.state.motion and protocol.state.motion.movement_manager:
            movement_manager = protocol.state.motion.movement_manager
            if movement_manager.queue_emotion_move(emotion_name):
                _LOGGER.info("Queued emotion move: %s", emotion_name)
            else:
                _LOGGER.warning("Failed to queue emotion: %s", emotion_name)
        else:
            _LOGGER.warning("Cannot play emotion: no movement manager available")
    except Exception as e:
        _LOGGER.error("Error playing emotion %s: %s", emotion_name, e)


def enter_motion_state(protocol: VoiceSatelliteProtocol, context: str, callback_name: str) -> None:
    protocol._cancel_delayed_idle_return()
    run_motion_state(protocol, context, callback_name)


def run_motion_state(protocol: VoiceSatelliteProtocol, context: str, callback_name: str) -> None:
    if not protocol.state.motion_enabled:
        if context == "speaking":
            _LOGGER.warning("Motion disabled, skipping speaking animation")
        return
    if context in {"thinking", "idle"} and not protocol.state.reachy_mini:
        return
    motion = protocol.state.motion
    if motion is None:
        if context == "speaking":
            _LOGGER.warning("No motion controller, skipping speaking animation")
        return
    try:
        _LOGGER.debug("Reachy Mini: %s animation", context.capitalize())
        getattr(motion, callback_name)()
    except Exception as e:
        _LOGGER.error("Reachy Mini motion error: %s", e)
