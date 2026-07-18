"""Movement state machine and related motion data structures.

This module now also contains idle-behavior data helpers so the control-loop
implementation can stay focused on runtime orchestration.
"""

import logging
import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ..animations.animation_config import load_animation_config

logger = logging.getLogger(__name__)

OFFICIAL_NEUTRAL_ANTENNA_SDK_LEFT_RAD = -0.1745
OFFICIAL_NEUTRAL_ANTENNA_SDK_RIGHT_RAD = 0.1745
OFFICIAL_NEUTRAL_ANTENNA_LOCAL_LEFT_RAD = 0.1745
OFFICIAL_NEUTRAL_ANTENNA_LOCAL_RIGHT_RAD = -0.1745
OFFICIAL_BREATHING_INTERPOLATION_DURATION_S = 1.0
OFFICIAL_BREATHING_Z_AMPLITUDE_M = 0.005
OFFICIAL_BREATHING_FREQUENCY_HZ = 0.1
OFFICIAL_BREATHING_ANTENNA_AMPLITUDE_RAD = math.radians(15.0)
OFFICIAL_BREATHING_ANTENNA_FREQUENCY_HZ = 0.5
IDLE_BREATHING_FREQUENCY_HZ = OFFICIAL_BREATHING_FREQUENCY_HZ


class RobotState(Enum):
    """Robot state machine states."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


# State to animation mapping
# SPEAKING uses a dedicated antenna-forward animation while speech_sway
# continues to drive the head motion on top.
STATE_ANIMATION_MAP = {
    "idle": "idle",
    "listening": "listening",
    "thinking": "thinking",
    "speaking": "speaking",
}


@dataclass
class MovementState:
    """Internal movement state (only modified by control loop)."""

    # Current robot state
    robot_state: RobotState = RobotState.IDLE

    # Animation offsets (from AnimationPlayer)
    anim_pitch: float = 0.0
    anim_yaw: float = 0.0
    anim_roll: float = 0.0
    anim_x: float = 0.0
    anim_y: float = 0.0
    anim_z: float = 0.0
    anim_antenna_left: float = 0.0
    anim_antenna_right: float = 0.0

    # Speech sway offsets (from audio analysis)
    sway_pitch: float = 0.0
    sway_yaw: float = 0.0
    sway_roll: float = 0.0
    sway_x: float = 0.0
    sway_y: float = 0.0
    sway_z: float = 0.0

    # Target pose (from actions)
    target_pitch: float = 0.0
    target_yaw: float = 0.0
    target_roll: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    target_z: float = 0.0
    target_antenna_left: float = 0.0
    target_antenna_right: float = 0.0

    # Timing
    last_activity_time: float = 0.0
    idle_start_time: float = 0.0

    # Note: Antenna freeze state is now managed by AntennaController (motion/antenna.py)

    # Idle look-around behavior
    next_look_around_time: float = 0.0
    look_around_in_progress: bool = False

    animation_blend: float = 1.0


@dataclass
class PendingAction:
    """A pending motion action."""

    name: str
    target_pitch: float = 0.0
    target_yaw: float = 0.0
    target_roll: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    target_z: float = 0.0
    target_antenna_left: float = 0.0
    target_antenna_right: float = 0.0
    duration: float = 0.5
    callback: Callable | None = None


@dataclass
class IdleRestPose:
    """Low-energy rest pose used when idle behavior is disabled."""

    pitch_rad: float
    antenna_left_rad: float
    antenna_right_rad: float


@dataclass
class IdleBehaviorConfig:
    """Parsed idle behavior configuration from the unified JSON file."""

    rest_pose: IdleRestPose
    min_interval_s: float
    max_interval_s: float
    trigger_probability: float
    generation: "IdleGenerationConfig"


@dataclass
class IdleGenerationConfig:
    """Realtime generated idle motion ranges."""

    yaw_range_deg: tuple[float, float]
    pitch_range_deg: tuple[float, float]
    roll_range_deg: tuple[float, float]
    x_range_m: tuple[float, float]
    y_range_m: tuple[float, float]
    z_range_m: tuple[float, float]
    antenna_variation_range_rad: tuple[float, float]
    duration_range_s: tuple[float, float]
    hold_range_s: tuple[float, float]
    return_duration_range_s: tuple[float, float]
    fade_out_duration_range_s: tuple[float, float]
    breath_cycle_range: tuple[int, int]
    opposite_direction_bias: float
    micro_motion_probability: float
    min_repeat_distance: float


def parse_numeric_range(value: Any, default_min: float, default_max: float) -> tuple[float, float]:
    """Parse a numeric range from config value."""
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            min_v = float(value[0])
            max_v = float(value[1])
            if min_v > max_v:
                min_v, max_v = max_v, min_v
            return min_v, max_v
        except (TypeError, ValueError):
            return default_min, default_max

    if value is None:
        return default_min, default_max

    try:
        span = abs(float(value))
        return -span, span
    except (TypeError, ValueError):
        return default_min, default_max


def parse_probability(value: Any, default: float) -> float:
    """Parse a probability-like value in the 0..1 range."""
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def parse_int_range(value: Any, default_min: int, default_max: int) -> tuple[int, int]:
    """Parse an integer range from config value."""
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            min_v = int(value[0])
            max_v = int(value[1])
            if min_v > max_v:
                min_v, max_v = max_v, min_v
            return max(1, min_v), max(1, max_v)
        except (TypeError, ValueError):
            return default_min, default_max

    if value is None:
        return default_min, default_max

    try:
        cycles = max(1, int(value))
        return cycles, cycles
    except (TypeError, ValueError):
        return default_min, default_max


def load_idle_behavior_config(
    *,
    config_path: Path,
    default_rest_pose: dict[str, float],
    default_min_interval_s: float,
    default_max_interval_s: float,
    default_probability: float,
    default_yaw_range_deg: float,
    default_pitch_range_deg: float,
    default_duration_s: float,
) -> IdleBehaviorConfig:
    """Load idle behavior configuration from the unified animation file."""
    rest_pose = IdleRestPose(
        pitch_rad=math.radians(float(default_rest_pose["pitch_deg"])),
        antenna_left_rad=float(default_rest_pose["antenna_left_rad"]),
        antenna_right_rad=float(default_rest_pose["antenna_right_rad"]),
    )
    min_interval_s = default_min_interval_s
    max_interval_s = default_max_interval_s
    trigger_probability = default_probability
    generation = IdleGenerationConfig(
        yaw_range_deg=(-default_yaw_range_deg, default_yaw_range_deg),
        pitch_range_deg=(-default_pitch_range_deg, default_pitch_range_deg),
        roll_range_deg=(-6.0, 6.0),
        x_range_m=(-0.002, 0.002),
        y_range_m=(-0.002, 0.002),
        z_range_m=(-0.006, 0.014),
        antenna_variation_range_rad=(-0.06, 0.06),
        duration_range_s=(7.5, 12.0),
        hold_range_s=(1.0, 2.0),
        return_duration_range_s=(2.2, 3.4),
        fade_out_duration_range_s=(0.35, 0.65),
        breath_cycle_range=(1, 3),
        opposite_direction_bias=0.68,
        micro_motion_probability=0.05,
        min_repeat_distance=0.35,
    )

    if not config_path.exists():
        logger.debug("Idle behavior config file not found: %s", config_path)
        return IdleBehaviorConfig(rest_pose, min_interval_s, max_interval_s, trigger_probability, generation)

    try:
        config = load_animation_config(config_path)
    except Exception as e:
        logger.warning("Failed to read idle behavior config: %s", e)
        return IdleBehaviorConfig(rest_pose, min_interval_s, max_interval_s, trigger_probability, generation)

    rest_pose_section = config.get("idle_rest_pose")
    if isinstance(rest_pose_section, dict):
        try:
            rest_pose.pitch_rad = math.radians(
                float(rest_pose_section.get("pitch_deg", default_rest_pose["pitch_deg"]))
            )
        except (TypeError, ValueError):
            pass
        try:
            rest_pose.antenna_left_rad = float(
                rest_pose_section.get("antenna_left_rad", default_rest_pose["antenna_left_rad"])
            )
        except (TypeError, ValueError):
            pass
        try:
            rest_pose.antenna_right_rad = float(
                rest_pose_section.get("antenna_right_rad", default_rest_pose["antenna_right_rad"])
            )
        except (TypeError, ValueError):
            pass

    section = config.get("idle_generated_motion")
    if not isinstance(section, dict):
        return IdleBehaviorConfig(rest_pose, min_interval_s, max_interval_s, trigger_probability, generation)

    try:
        min_interval = float(section.get("min_interval_s", default_min_interval_s))
        max_interval = float(section.get("max_interval_s", default_max_interval_s))
        if min_interval > max_interval:
            min_interval, max_interval = max_interval, min_interval
        min_interval_s = max(0.5, min_interval)
        max_interval_s = max(min_interval_s, max_interval)
    except (TypeError, ValueError):
        min_interval_s = default_min_interval_s
        max_interval_s = default_max_interval_s

    try:
        probability = float(section.get("trigger_probability", default_probability))
    except (TypeError, ValueError):
        probability = default_probability
    trigger_probability = max(0.0, min(1.0, probability))

    generation = IdleGenerationConfig(
        yaw_range_deg=parse_numeric_range(section.get("yaw_range_deg"), -default_yaw_range_deg, default_yaw_range_deg),
        pitch_range_deg=parse_numeric_range(
            section.get("pitch_range_deg"), -default_pitch_range_deg, default_pitch_range_deg
        ),
        roll_range_deg=parse_numeric_range(section.get("roll_range_deg"), -6.0, 6.0),
        x_range_m=parse_numeric_range(section.get("x_range_m"), -0.002, 0.002),
        y_range_m=parse_numeric_range(section.get("y_range_m"), -0.002, 0.002),
        z_range_m=parse_numeric_range(section.get("z_range_m"), -0.006, 0.014),
        antenna_variation_range_rad=parse_numeric_range(section.get("antenna_variation_range_rad"), -0.06, 0.06),
        duration_range_s=parse_numeric_range(section.get("duration_range_s"), 7.5, 12.0),
        hold_range_s=parse_numeric_range(section.get("hold_range_s"), 1.0, 2.0),
        return_duration_range_s=parse_numeric_range(section.get("return_duration_range_s"), 2.2, 3.4),
        fade_out_duration_range_s=parse_numeric_range(section.get("fade_out_duration_range_s"), 0.35, 0.65),
        breath_cycle_range=parse_int_range(section.get("breath_cycle_range"), 1, 3),
        opposite_direction_bias=parse_probability(section.get("opposite_direction_bias"), 0.68),
        micro_motion_probability=parse_probability(section.get("micro_motion_probability"), 0.05),
        min_repeat_distance=parse_probability(section.get("min_repeat_distance"), 0.35),
    )

    return IdleBehaviorConfig(rest_pose, min_interval_s, max_interval_s, trigger_probability, generation)


def _sample_biased_yaw(config: IdleGenerationConfig, last_yaw_rad: float) -> float:
    yaw_min, yaw_max = config.yaw_range_deg
    if abs(last_yaw_rad) > math.radians(2.0) and random.random() < config.opposite_direction_bias:
        if last_yaw_rad > 0.0 and yaw_min < 0.0:
            yaw_max = min(yaw_max, -2.0)
        elif last_yaw_rad < 0.0 and yaw_max > 0.0:
            yaw_min = max(yaw_min, 2.0)
    return math.radians(random.uniform(float(yaw_min), float(yaw_max)))


def _sample_generated_idle_values(
    config: IdleGenerationConfig,
    *,
    last_yaw_rad: float,
) -> tuple[float, float, float, float, float, float, float, float, float, float]:
    pitch_min, pitch_max = config.pitch_range_deg
    roll_min, roll_max = config.roll_range_deg
    x_min, x_max = config.x_range_m
    y_min, y_max = config.y_range_m
    z_min, z_max = config.z_range_m
    duration_min, duration_max = config.duration_range_s

    yaw = _sample_biased_yaw(config, last_yaw_rad)
    pitch = math.radians(random.uniform(float(pitch_min), float(pitch_max)))
    roll = math.radians(random.uniform(float(roll_min), float(roll_max)))
    x = random.uniform(float(x_min), float(x_max))
    y = random.uniform(float(y_min), float(y_max))
    z = random.uniform(float(z_min), float(z_max))
    antenna_left = OFFICIAL_NEUTRAL_ANTENNA_LOCAL_LEFT_RAD
    antenna_right = OFFICIAL_NEUTRAL_ANTENNA_LOCAL_RIGHT_RAD
    duration = max(1.5, random.uniform(float(duration_min), float(duration_max)))

    if random.random() < config.micro_motion_probability:
        yaw *= 0.35
        pitch *= 0.45
        roll *= 0.45
        x *= 0.4
        y *= 0.4
        z *= 0.4
        duration = max(duration, 2.4)

    if abs(yaw) < math.radians(1.5) and abs(pitch) < math.radians(1.0) and abs(roll) < math.radians(1.0):
        yaw = math.copysign(math.radians(random.uniform(2.5, 6.0)), yaw or random.choice((-1.0, 1.0)))

    return yaw, pitch, roll, x, y, z, antenna_left, antenna_right, duration, random.random()


def _split_sequence_duration(total_duration: float, step_count: int) -> list[float]:
    """Split a generated idle movement into several slow, visible segments."""
    weights = [random.uniform(0.85, 1.35) for _ in range(max(1, step_count))]
    total_weight = sum(weights)
    duration = max(6.5, total_duration)
    return [duration * weight / total_weight for weight in weights]


def _official_neutral_antenna_targets() -> dict[str, float]:
    return {
        "target_antenna_left": OFFICIAL_NEUTRAL_ANTENNA_LOCAL_LEFT_RAD,
        "target_antenna_right": OFFICIAL_NEUTRAL_ANTENNA_LOCAL_RIGHT_RAD,
    }


def _make_idle_step(
    *,
    name: str,
    yaw: float,
    pitch: float,
    roll: float,
    x: float,
    y: float,
    z: float,
    duration: float,
) -> PendingAction:
    return PendingAction(
        name=f"idle_generated_{name}",
        target_yaw=yaw,
        target_pitch=pitch,
        target_roll=roll,
        target_x=x,
        target_y=y,
        target_z=z,
        duration=duration,
        **_official_neutral_antenna_targets(),
    )


_IDLE_PRIMITIVE_CODES = {
    "look_left": 0.05,
    "look_right": 0.11,
    "look_up": 0.17,
    "look_down": 0.23,
    "look_up_side": 0.29,
    "look_down_side": 0.35,
    "stretch_neck": 0.41,
    "tuck_neck": 0.47,
    "tilt_head": 0.53,
    "opposite_glance": 0.59,
    "settle_glance": 0.65,
    "small_pause": 0.71,
}


def _sequence_signature(actions: list[PendingAction]) -> tuple[float, ...]:
    """Compact numeric signature used to avoid near-identical idle sequences."""
    if not actions:
        return ()
    total_duration = sum(action.duration for action in actions)
    mean_yaw = sum(action.target_yaw for action in actions) / len(actions)
    mean_pitch = sum(action.target_pitch for action in actions) / len(actions)
    mean_z = sum(action.target_z for action in actions) / len(actions)
    max_yaw = max(abs(action.target_yaw) for action in actions)
    max_pitch = max(abs(action.target_pitch) for action in actions)
    max_z = max(abs(action.target_z) for action in actions)
    order = tuple(
        _IDLE_PRIMITIVE_CODES.get(action.name.rsplit("_", 1)[0].removeprefix("idle_generated_"), 0.0)
        for action in actions[:8]
    )
    return (
        len(actions) / 8.0,
        total_duration / 12.0,
        mean_yaw / math.radians(28.0),
        mean_pitch / math.radians(14.0),
        mean_z / 0.014,
        max_yaw / math.radians(28.0),
        max_pitch / math.radians(14.0),
        max_z / 0.014,
        *order,
    )


def _signature_distance(candidate: tuple[float, ...], previous: tuple[float, ...] | None) -> float:
    if previous is None:
        return 1.0
    length = min(len(candidate), len(previous))
    if length == 0:
        return 1.0
    return sum(min(1.0, abs(candidate[i] - previous[i])) for i in range(length)) / length


def _generated_distance(candidate: tuple[float, ...], previous: tuple[float, ...] | None) -> float:
    if previous is None:
        return 1.0
    yaw, pitch, roll, x, y, z, _antenna_left, _antenna_right, duration, _ = candidate
    last_yaw, last_pitch, last_roll, last_x, last_y, last_z, _last_left, _last_right, last_duration, _ = previous
    parts = (
        min(1.0, abs(yaw - last_yaw) / math.radians(18.0)),
        min(1.0, abs(pitch - last_pitch) / math.radians(8.0)),
        min(1.0, abs(roll - last_roll) / math.radians(8.0)),
        min(1.0, abs(x - last_x) / 0.003),
        min(1.0, abs(y - last_y) / 0.003),
        min(1.0, abs(z - last_z) / 0.006),
        min(1.0, abs(duration - last_duration) / 2.0),
    )
    return sum(parts) / len(parts)


def build_generated_idle_pending_action(
    config: IdleGenerationConfig,
    *,
    last_yaw_rad: float = 0.0,
    last_signature: tuple[float, ...] | None = None,
) -> tuple[PendingAction, tuple[float, ...]]:
    """Generate one idle action from fresh sampled ranges at runtime."""
    best = None
    best_distance = -1.0
    for _ in range(10):
        candidate = _sample_generated_idle_values(config, last_yaw_rad=last_yaw_rad)
        distance = _generated_distance(candidate, last_signature)
        if distance >= config.min_repeat_distance:
            best = candidate
            break
        if distance > best_distance:
            best = candidate
            best_distance = distance

    assert best is not None
    yaw, pitch, roll, x, y, z, antenna_left, antenna_right, duration, _ = best
    return PendingAction(
        name="idle_generated",
        target_yaw=yaw,
        target_pitch=pitch,
        target_roll=roll,
        target_x=x,
        target_y=y,
        target_z=z,
        target_antenna_left=antenna_left,
        target_antenna_right=antenna_right,
        duration=duration,
    ), best


def build_generated_idle_action_sequence(
    config: IdleGenerationConfig,
    *,
    last_yaw_rad: float = 0.0,
    last_signature: tuple[float, ...] | None = None,
) -> tuple[list[PendingAction], tuple[float, ...]]:
    """Generate a multi-step idle action sequence from fresh runtime parameters."""
    best_actions = None
    best_signature = None
    best_distance = -1.0
    for _ in range(8):
        actions, signature = _build_generated_idle_action_sequence_once(
            config,
            last_yaw_rad=last_yaw_rad,
            last_signature=last_signature,
        )
        distance = _signature_distance(signature, last_signature)
        if distance >= config.min_repeat_distance:
            return actions, signature
        if distance > best_distance:
            best_actions = actions
            best_signature = signature
            best_distance = distance

    assert best_actions is not None and best_signature is not None
    return best_actions, best_signature


def _build_generated_idle_action_sequence_once(
    config: IdleGenerationConfig,
    *,
    last_yaw_rad: float = 0.0,
    last_signature: tuple[float, ...] | None = None,
) -> tuple[list[PendingAction], tuple[float, ...]]:
    """Generate one candidate idle sequence."""
    action, _signature = build_generated_idle_pending_action(
        config,
        last_yaw_rad=last_yaw_rad,
        last_signature=None,
    )
    step_count = random.randint(5, 8)
    durations = _split_sequence_duration(action.duration, step_count)
    yaw_sign = 1.0 if action.target_yaw >= 0.0 else -1.0
    side_name = "look_right" if yaw_sign > 0.0 else "look_left"
    opposite_name = "look_left" if yaw_sign > 0.0 else "look_right"
    side_yaw = math.copysign(
        max(abs(action.target_yaw), math.radians(random.uniform(9.0, 26.0))),
        yaw_sign,
    )
    opposite_yaw = -side_yaw * random.uniform(0.35, 0.8)
    up_pitch = -abs(random.uniform(math.radians(7.0), math.radians(13.0)))
    down_pitch = abs(random.uniform(math.radians(7.0), math.radians(14.0)))
    stretch_z = max(action.target_z, random.uniform(0.008, 0.014))
    tuck_z = random.uniform(-0.006, -0.002)
    side_roll = yaw_sign * abs(random.uniform(math.radians(1.5), math.radians(7.0)))

    primitives = [
        (
            side_name,
            side_yaw,
            action.target_pitch * random.uniform(0.35, 0.75),
            side_roll,
            action.target_x * random.uniform(0.35, 0.75),
            action.target_y,
            random.uniform(-0.001, 0.003),
        ),
        (
            "look_up",
            side_yaw * random.uniform(-0.25, 0.55),
            up_pitch,
            action.target_roll * random.uniform(0.35, 0.75),
            action.target_x * random.uniform(0.4, 1.0),
            action.target_y * random.uniform(0.35, 0.8),
            random.uniform(0.004, 0.01),
        ),
        (
            "stretch_neck",
            side_yaw * random.uniform(-0.15, 0.65) + math.radians(random.uniform(-4.0, 4.0)),
            random.uniform(math.radians(-4.0), math.radians(3.0)),
            action.target_roll * random.uniform(0.5, 1.0),
            action.target_x,
            action.target_y,
            stretch_z,
        ),
        (
            "look_down",
            side_yaw * random.uniform(-0.2, 0.45),
            down_pitch,
            -side_roll * random.uniform(0.3, 0.8),
            action.target_x * random.uniform(0.15, 0.55),
            -action.target_y * random.uniform(0.15, 0.45),
            random.uniform(-0.002, 0.002),
        ),
        (
            "tuck_neck",
            opposite_yaw * random.uniform(0.2, 0.65),
            down_pitch * random.uniform(0.45, 0.9),
            -side_roll * random.uniform(0.2, 0.65),
            -action.target_x * random.uniform(0.1, 0.4),
            -action.target_y * random.uniform(0.2, 0.6),
            tuck_z,
        ),
        (
            opposite_name,
            opposite_yaw,
            random.choice((up_pitch, down_pitch)) * random.uniform(0.25, 0.65),
            -side_roll * random.uniform(0.35, 0.8),
            -action.target_x * random.uniform(0.25, 0.75),
            -action.target_y,
            random.uniform(-0.001, 0.005),
        ),
        (
            "settle_glance",
            side_yaw * random.uniform(0.15, 0.4),
            action.target_pitch * random.uniform(0.15, 0.4),
            action.target_roll * random.uniform(0.1, 0.35),
            action.target_x * random.uniform(0.05, 0.25),
            action.target_y * random.uniform(0.05, 0.25),
            random.uniform(-0.001, 0.003),
        ),
        (
            "look_up_side",
            side_yaw * random.uniform(0.55, 1.0),
            up_pitch * random.uniform(0.45, 0.9),
            side_roll * random.uniform(0.25, 0.75),
            action.target_x * random.uniform(0.15, 0.7),
            action.target_y * random.uniform(0.15, 0.7),
            random.uniform(0.003, 0.01),
        ),
        (
            "look_down_side",
            opposite_yaw * random.uniform(0.35, 0.9),
            down_pitch * random.uniform(0.45, 0.95),
            -side_roll * random.uniform(0.25, 0.75),
            -action.target_x * random.uniform(0.15, 0.7),
            -action.target_y * random.uniform(0.15, 0.7),
            random.uniform(-0.004, 0.001),
        ),
        (
            "tilt_head",
            side_yaw * random.uniform(-0.2, 0.35),
            action.target_pitch * random.uniform(0.2, 0.5),
            side_roll * random.uniform(0.75, 1.2),
            action.target_x * random.uniform(0.05, 0.3),
            action.target_y * random.uniform(0.05, 0.3),
            random.uniform(-0.001, 0.003),
        ),
        (
            "small_pause",
            action.target_yaw * random.uniform(0.15, 0.35),
            action.target_pitch * random.uniform(0.1, 0.25),
            action.target_roll * random.uniform(0.1, 0.25),
            action.target_x * random.uniform(0.05, 0.18),
            action.target_y * random.uniform(0.05, 0.18),
            action.target_z * random.uniform(0.05, 0.18),
        ),
    ]

    by_name = {primitive[0]: primitive for primitive in primitives}
    selected = [
        by_name[side_name],
        by_name["look_up"],
        by_name["stretch_neck"],
        by_name["look_down"],
        by_name["tuck_neck"],
    ]
    optional_names = [
        "look_up",
        "look_down",
        "look_up_side",
        "look_down_side",
        opposite_name,
        "settle_glance",
        "tilt_head",
        "small_pause",
    ]
    optional = [by_name[name] for name in optional_names if by_name[name] not in selected]
    random.shuffle(optional)
    selected.extend(optional[: max(0, step_count - len(selected))])
    anchor = selected[0]
    middle = selected[1:]
    random.shuffle(middle)
    if random.random() < 0.65:
        selected = [anchor, *middle]
    else:
        insert_at = random.randint(0, min(2, len(middle)))
        selected = [*middle[:insert_at], anchor, *middle[insert_at:]]
    selected = selected[:step_count]

    actions = []
    for index, (name, yaw, pitch, roll, x, y, z) in enumerate(selected):
        actions.append(
            _make_idle_step(
                name=f"{name}_{index + 1}",
                yaw=yaw,
                pitch=pitch,
                roll=roll,
                x=x,
                y=y,
                z=z,
                duration=durations[index],
            )
        )
    return actions, _sequence_signature(actions)
