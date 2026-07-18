"""Idle runtime helpers for `MovementManager`."""

from __future__ import annotations

import logging
import math
import random
from typing import TYPE_CHECKING

from .state_machine import (
    IDLE_BREATHING_FREQUENCY_HZ,
    OFFICIAL_NEUTRAL_ANTENNA_LOCAL_LEFT_RAD,
    OFFICIAL_NEUTRAL_ANTENNA_LOCAL_RIGHT_RAD,
    PendingAction,
    RobotState,
    build_generated_idle_action_sequence,
)

if TYPE_CHECKING:
    from .movement_manager import MovementManager

logger = logging.getLogger(__name__)


def apply_idle_behavior_enabled(manager: MovementManager, enabled: bool) -> None:
    manager._idle_motion_enabled = enabled
    manager._idle_antenna_enabled = enabled
    manager._idle_generated_motion_enabled = enabled

    if not enabled:
        fold_animation_offsets_into_targets(manager)
        clear_idle_activity(manager)
        clear_idle_animation(manager)
        manager.state.anim_antenna_left = 0.0
        manager.state.anim_antenna_right = 0.0
        if manager.state.robot_state == RobotState.IDLE:
            transition_or_apply_idle_rest_pose(manager, duration=2.4)
    elif manager.state.robot_state == RobotState.IDLE:
        clear_idle_activity(manager)
        manager._animation_player.set_animation("idle")
        manager._idle_action_animation_suppression = 1.0
        manager._start_action(
            PendingAction(
                name="idle_enable_neutral",
                target_pitch=0.0,
                target_yaw=0.0,
                target_roll=0.0,
                target_x=0.0,
                target_y=0.0,
                target_z=0.0,
                target_antenna_left=OFFICIAL_NEUTRAL_ANTENNA_LOCAL_LEFT_RAD,
                target_antenna_right=OFFICIAL_NEUTRAL_ANTENNA_LOCAL_RIGHT_RAD,
                duration=1.8,
            )
        )

    logger.info("Idle behavior %s", "enabled" if enabled else "disabled")


def fold_animation_offsets_into_targets(manager: MovementManager) -> None:
    """Preserve the visible pose before disabling additive idle animation."""
    manager.state.target_pitch += manager.state.anim_pitch
    manager.state.target_yaw += manager.state.anim_yaw
    manager.state.target_roll += manager.state.anim_roll
    manager.state.target_x += manager.state.anim_x
    manager.state.target_y += manager.state.anim_y
    manager.state.target_z += manager.state.anim_z
    manager.state.target_antenna_left += manager.state.anim_antenna_left
    manager.state.target_antenna_right += manager.state.anim_antenna_right


def apply_idle_rest_pose(manager: MovementManager) -> None:
    manager.state.target_pitch = manager._idle_rest_head_pitch_rad
    manager.state.target_yaw = 0.0
    manager.state.target_roll = 0.0
    manager.state.target_x = 0.0
    manager.state.target_y = 0.0
    manager.state.target_z = 0.0
    manager.state.target_antenna_left = manager._idle_rest_antenna_left_rad
    manager.state.target_antenna_right = manager._idle_rest_antenna_right_rad
    manager.state.anim_antenna_left = 0.0
    manager.state.anim_antenna_right = 0.0
    manager._antenna_controller.reset()


def transition_or_apply_idle_rest_pose(manager: MovementManager, duration: float = 2.0) -> None:
    if manager.state.robot_state == RobotState.IDLE:
        manager.transition_to_idle_rest(duration=duration)
    else:
        apply_idle_rest_pose(manager)


def clear_idle_activity(manager: MovementManager) -> None:
    manager.state.next_look_around_time = 0.0
    manager.state.look_around_in_progress = False
    manager._idle_action_queue.clear()
    manager._last_idle_generated_yaw = 0.0
    manager._last_idle_generated_signature = None
    if manager._pending_action and manager._pending_action.name.startswith(("idle_action", "idle_generated")):
        manager._pending_action = None


def clear_idle_animation(manager: MovementManager) -> None:
    manager._animation_player.stop()
    manager.state.anim_pitch = 0.0
    manager.state.anim_yaw = 0.0
    manager.state.anim_roll = 0.0
    manager.state.anim_x = 0.0
    manager.state.anim_y = 0.0
    manager.state.anim_z = 0.0
    manager.state.anim_antenna_left = 0.0
    manager.state.anim_antenna_right = 0.0


def schedule_next_idle_action_time(manager: MovementManager, now: float) -> None:
    interval = random.uniform(manager._idle_generated_min_interval, manager._idle_generated_max_interval)
    manager.state.next_look_around_time = now + interval


def _random_duration(duration_range: tuple[float, float], fallback: float) -> float:
    try:
        duration_min, duration_max = duration_range
        duration_min = max(0.05, float(duration_min))
        duration_max = max(duration_min, float(duration_max))
    except (TypeError, ValueError):
        return fallback
    return random.uniform(duration_min, duration_max)


def _random_breathing_window_after_idle_action(manager: MovementManager) -> float:
    """Return a post-action pure breathing window in whole official breath cycles."""
    cycle_min, cycle_max = manager._idle_generation_config.breath_cycle_range
    cycle_min = max(1, int(cycle_min))
    cycle_max = max(cycle_min, int(cycle_max))
    breath_period_s = 1.0 / max(0.01, IDLE_BREATHING_FREQUENCY_HZ)
    return random.randint(cycle_min, cycle_max) * breath_period_s


def _current_target_action(manager: MovementManager, *, name: str, duration: float) -> PendingAction:
    return PendingAction(
        name=name,
        target_pitch=manager.state.target_pitch,
        target_yaw=manager.state.target_yaw,
        target_roll=manager.state.target_roll,
        target_x=manager.state.target_x,
        target_y=manager.state.target_y,
        target_z=manager.state.target_z,
        target_antenna_left=manager.state.target_antenna_left,
        target_antenna_right=manager.state.target_antenna_right,
        duration=duration,
    )


def _hold_generated_action(action: PendingAction, *, duration: float) -> PendingAction:
    return PendingAction(
        name="idle_generated_hold",
        target_pitch=action.target_pitch,
        target_yaw=action.target_yaw,
        target_roll=action.target_roll,
        target_x=action.target_x,
        target_y=action.target_y,
        target_z=action.target_z,
        target_antenna_left=action.target_antenna_left,
        target_antenna_right=action.target_antenna_right,
        duration=duration,
    )


def _return_to_breathing_neutral(duration: float) -> PendingAction:
    return PendingAction(
        name="idle_generated_return",
        target_pitch=0.0,
        target_yaw=0.0,
        target_roll=0.0,
        target_x=0.0,
        target_y=0.0,
        target_z=0.0,
        target_antenna_left=OFFICIAL_NEUTRAL_ANTENNA_LOCAL_LEFT_RAD,
        target_antenna_right=OFFICIAL_NEUTRAL_ANTENNA_LOCAL_RIGHT_RAD,
        duration=duration,
    )


def enqueue_generated_idle_cycle(manager: MovementManager, idle_actions: list[PendingAction]) -> float:
    """Queue one generated idle cycle with breathing crossfade and return."""
    config = manager._idle_generation_config
    fade_out = _random_duration(config.fade_out_duration_range_s, 0.7)
    hold = _random_duration(config.hold_range_s, 0.6)
    return_duration = _random_duration(config.return_duration_range_s, 1.4)
    final_action = idle_actions[-1]

    manager._idle_action_queue.append(
        _current_target_action(manager, name="idle_generated_fade_out", duration=fade_out)
    )
    manager._idle_action_queue.extend(idle_actions)
    manager._idle_action_queue.append(_hold_generated_action(final_action, duration=hold))
    manager._idle_action_queue.append(_return_to_breathing_neutral(return_duration))
    action_duration = sum(max(0.0, float(action.duration)) for action in idle_actions)
    return fade_out + action_duration + hold + return_duration


def update_idle_look_around(
    manager: MovementManager,
    *,
    inactivity_threshold_s: float,
    legacy_probability: float,
    yaw_range_deg: float,
    pitch_range_deg: float,
    duration_s: float,
) -> None:
    if not manager._idle_motion_enabled and not manager._idle_generated_motion_enabled:
        manager.state.next_look_around_time = 0.0
        manager.state.look_around_in_progress = False
        return

    if manager.state.robot_state != RobotState.IDLE:
        manager.state.next_look_around_time = 0.0
        manager.state.look_around_in_progress = False
        return

    if manager._manual_head_yaw_hold:
        manager.state.next_look_around_time = 0.0
        manager.state.look_around_in_progress = False
        return

    if manager._pending_action is not None:
        return

    now = manager._now()
    idle_duration = now - manager.state.idle_start_time
    if idle_duration < inactivity_threshold_s:
        return

    if manager.state.next_look_around_time == 0.0:
        schedule_next_idle_action_time(manager, now)
        return

    if now < manager.state.next_look_around_time or manager.state.look_around_in_progress:
        return

    if manager._idle_generated_motion_enabled:
        if random.random() > manager._idle_generated_trigger_probability:
            schedule_next_idle_action_time(manager, now)
            return

        idle_actions, signature = build_generated_idle_action_sequence(
            manager._idle_generation_config,
            last_yaw_rad=manager._last_idle_generated_yaw,
            last_signature=manager._last_idle_generated_signature,
        )
        manager._last_idle_generated_yaw = idle_actions[0].target_yaw
        manager._last_idle_generated_signature = signature
        queued_duration = enqueue_generated_idle_cycle(manager, idle_actions)
        breathing_window = _random_breathing_window_after_idle_action(manager)
        manager.state.look_around_in_progress = True
        manager.state.next_look_around_time = now + queued_duration + breathing_window
        return

    if not manager._idle_motion_enabled:
        schedule_next_idle_action_time(manager, now)
        return

    if random.random() > legacy_probability:
        schedule_next_idle_action_time(manager, now)
        return

    target_yaw = random.uniform(-yaw_range_deg, yaw_range_deg)
    target_pitch = random.uniform(-pitch_range_deg, pitch_range_deg)
    action = PendingAction(
        name="look_around",
        target_yaw=math.radians(target_yaw),
        target_pitch=math.radians(target_pitch),
        duration=duration_s,
    )
    manager._idle_action_queue.append(action)
    manager.state.look_around_in_progress = True
    queued_duration = sum(max(0.0, float(item.duration)) for item in manager._idle_action_queue)
    manager.state.next_look_around_time = now + queued_duration
    schedule_next_idle_action_time(manager, manager.state.next_look_around_time)
    logger.debug("Starting look-around: yaw=%.1f°, pitch=%.1f°", target_yaw, target_pitch)
