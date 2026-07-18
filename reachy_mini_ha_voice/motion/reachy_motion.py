"""Reachy Mini motion control integration.

This module provides a high-level motion API that delegates to the
MovementManager for unified control.
"""

import logging
import threading

from .movement_manager import MovementManager, RobotState

_LOGGER = logging.getLogger(__name__)
IDLE_RETURN_TO_NEUTRAL_DURATION_S = 1.0
IDLE_REST_HOLD_DELAY_S = 15.0


class ReachyMiniMotion:
    """Reachy Mini motion controller for voice assistant.

    All public motion methods (on_*) are non-blocking. They send commands
    to the MovementManager which handles them in its official-aligned 60Hz control loop.
    """

    def __init__(self, reachy_mini):
        self.reachy_mini = reachy_mini
        self._movement_manager: MovementManager | None = None
        self._is_speaking = False
        self._idle_rest_delay_timer: threading.Timer | None = None
        self._idle_rest_delay_generation = 0

        _LOGGER.debug("ReachyMiniMotion.__init__ called with reachy_mini=%s", reachy_mini)

        # Initialize movement manager
        try:
            self._movement_manager = MovementManager(reachy_mini)
            _LOGGER.debug("MovementManager created successfully")
        except Exception as e:
            _LOGGER.error("Failed to create MovementManager: %s", e, exc_info=True)
            self._movement_manager = None

    def set_reachy_mini(self, reachy_mini):
        """Set the Reachy Mini instance."""
        self.reachy_mini = reachy_mini
        if self._movement_manager is None:
            self._movement_manager = MovementManager(reachy_mini)
        else:
            self._movement_manager.robot = reachy_mini

    def start(self):
        """Start the movement manager control loop."""
        if self._movement_manager is not None:
            self._movement_manager.start()
            _LOGGER.info("Motion control started")
        else:
            _LOGGER.warning("Motion control not started: movement_manager is None")

    def shutdown(self):
        """Shutdown the motion controller."""
        self._cancel_delayed_idle_rest()
        if self._movement_manager is not None:
            self._movement_manager.stop()
            _LOGGER.info("Motion control stopped")

    @property
    def movement_manager(self) -> MovementManager | None:
        """Get the movement manager instance."""
        return self._movement_manager

    # -------------------------------------------------------------------------
    # Public non-blocking motion methods
    # -------------------------------------------------------------------------

    def _cancel_delayed_idle_rest(self, *, stop_temporary_breathing: bool = False) -> None:
        self._idle_rest_delay_generation += 1
        if self._idle_rest_delay_timer is not None:
            self._idle_rest_delay_timer.cancel()
            self._idle_rest_delay_timer = None
        if stop_temporary_breathing and self._movement_manager is not None:
            self._movement_manager.stop_temporary_idle_breathing()

    def _schedule_delayed_idle_rest(self) -> None:
        """Delay the low-energy rest pose after a conversation ends.

        When idle animation is disabled, the robot should not immediately drop
        into the historical low-energy rest pose after speaking. Keep the
        official breathing and antenna idle layer alive briefly so quick
        follow-up wake words feel natural, then settle into rest.
        """
        self._cancel_delayed_idle_rest()
        self._idle_rest_delay_generation += 1
        generation = self._idle_rest_delay_generation

        def _go_rest() -> None:
            self._idle_rest_delay_timer = None
            manager = self._movement_manager
            if manager is None:
                return
            if generation != self._idle_rest_delay_generation:
                return
            if manager.state.robot_state != RobotState.IDLE:
                return
            if manager.get_idle_behavior_enabled():
                return
            if manager._manual_head_yaw_hold:
                return
            manager.stop_temporary_idle_breathing()
            manager.transition_to_idle_rest(duration=2.6)

        delay_s = IDLE_RETURN_TO_NEUTRAL_DURATION_S + IDLE_REST_HOLD_DELAY_S
        self._idle_rest_delay_timer = threading.Timer(delay_s, _go_rest)
        self._idle_rest_delay_timer.daemon = True
        self._idle_rest_delay_timer.start()
        _LOGGER.debug("Scheduled idle rest transition in %.1fs", delay_s)

    def on_wakeup(self):
        """Called when wake word is detected.

        Non-blocking: command sent to MovementManager.
        """
        self._cancel_delayed_idle_rest(stop_temporary_breathing=True)
        _LOGGER.debug("on_wakeup called")
        if self._movement_manager is None:
            _LOGGER.warning("on_wakeup: movement_manager is None, skipping motion")
            return

        self._movement_manager.set_state(RobotState.LISTENING)
        _LOGGER.info("Wake word detected, entering listening state")

    def on_listening(self):
        """Called when listening for speech - attentive pose.

        Non-blocking: command sent to MovementManager.
        """
        self._cancel_delayed_idle_rest()
        if self._movement_manager is None:
            return

        self._movement_manager.set_state(RobotState.LISTENING)
        _LOGGER.debug("Reachy Mini: Listening pose")

    def on_continue_listening(self):
        """Called when continuing to listen in tap conversation mode.

        Non-blocking: command sent to MovementManager.
        """
        self._cancel_delayed_idle_rest()
        if self._movement_manager is None:
            return

        self._movement_manager.set_state(RobotState.LISTENING)
        _LOGGER.debug("Reachy Mini: Continue listening")

    def on_thinking(self):
        """Called when processing speech - thinking pose.

        Non-blocking: command sent to MovementManager.
        Animation offsets are defined in conversation_animations.json.
        """
        self._cancel_delayed_idle_rest()
        if self._movement_manager is None:
            return

        self._movement_manager.set_state(RobotState.THINKING)
        _LOGGER.debug("Reachy Mini: Thinking pose")

    def on_speaking_start(self):
        """Called when TTS starts - start speech-reactive motion.

        Non-blocking: command sent to MovementManager.
        The state is still exposed to the motion state machine, while the
        visible speaking motion is driven by SpeechSwayRT from TTS audio.
        """
        self._cancel_delayed_idle_rest()
        if self._movement_manager is None:
            _LOGGER.warning("MovementManager not initialized, skipping speaking animation")
            return

        self._is_speaking = True
        self._movement_manager.set_state(RobotState.SPEAKING)
        _LOGGER.info("Reachy Mini: Speaking animation started")

    def on_speaking_end(self):
        """Called when TTS ends - stop speech-reactive motion.

        Non-blocking: command sent to MovementManager.
        """
        if self._movement_manager is None:
            return

        self._is_speaking = False
        self._movement_manager.set_speech_sway(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        # Don't change state yet - let on_idle handle that
        _LOGGER.debug("Reachy Mini: Speaking ended")

    def on_conversation_finished(self):
        """Called when a non-continuous conversation ends before delayed idle return."""
        if self._movement_manager is None:
            return

        self._cancel_delayed_idle_rest()
        self._is_speaking = False
        if not self._movement_manager._manual_head_yaw_hold:
            self._movement_manager.reset_yaw_to_neutral(duration=1.2)
            _LOGGER.debug("Reachy Mini: Conversation finished, recentering yaw before idle")

    def on_idle(self):
        """Called when returning to idle state.

        Non-blocking: command sent to MovementManager.
        """
        if self._movement_manager is None:
            return

        self._is_speaking = False
        self._movement_manager.set_state(RobotState.IDLE)
        if not self._movement_manager._manual_head_yaw_hold:
            if self._movement_manager.get_idle_behavior_enabled():
                self._cancel_delayed_idle_rest(stop_temporary_breathing=True)
                self._movement_manager.reset_to_neutral(duration=IDLE_RETURN_TO_NEUTRAL_DURATION_S)
            else:
                self._movement_manager.reset_to_neutral(duration=IDLE_RETURN_TO_NEUTRAL_DURATION_S)
                self._schedule_delayed_idle_rest()
                self._movement_manager.start_temporary_idle_breathing()

        _LOGGER.debug("Reachy Mini: Idle pose")

    def on_pause_motion(self):
        """Called when motion should settle immediately.

        The robot smoothly returns to a neutral pose and then resumes its
        normal idle behavior.
        """
        if self._movement_manager is None:
            return

        self._cancel_delayed_idle_rest(stop_temporary_breathing=True)
        self._is_speaking = False
        self._movement_manager.reset_to_neutral(duration=0.6)
        self._movement_manager.set_state(RobotState.IDLE)
        _LOGGER.debug("Reachy Mini: Motion paused to neutral idle")

    def on_timer_finished(self):
        """Called when a timer finishes - alert animation.

        Non-blocking: command sent to MovementManager.
        """
        if self._movement_manager is None:
            return

        # Quick shake to alert
        self._movement_manager.shake(amplitude_deg=15, duration=0.4)
        _LOGGER.debug("Reachy Mini: Timer finished animation")

    def on_error(self):
        """Called on error - shake head.

        Non-blocking: command sent to MovementManager.
        """
        if self._movement_manager is None:
            return

        self._movement_manager.shake(amplitude_deg=10, duration=0.3)
        _LOGGER.debug("Reachy Mini: Error animation")

    def wiggle_antennas(self, happy: bool = True):
        """Wiggle antennas to show emotion.

        Non-blocking: antenna movement is handled by animation system.
        """
        if self._movement_manager is None:
            return

        # Antenna movement is handled by animation system
        # Set appropriate animation state
        if happy:
            self._movement_manager.set_state(RobotState.SPEAKING)
        _LOGGER.debug("Reachy Mini: Antenna wiggle (%s)", "happy" if happy else "sad")
