"""Read-only SDK helpers needed by the voice satellite.

Robot control is intentionally delegated to the official Reachy Mini Home
Assistant integration. The voice app only reads Direction of Arrival so a
wake word can receive an immediate, local turn-to-speaker response.
"""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class ReachyController:
    """Minimal read-only controller for local voice feedback."""

    def __init__(self, reachy_mini: Any) -> None:
        self._reachy_mini = reachy_mini

    def get_doa_angle(self) -> tuple[float, bool] | None:
        """Return the current mic-array direction and speech activity."""
        try:
            get_doa = getattr(getattr(self._reachy_mini, "media", None), "get_DoA", None)
            if not callable(get_doa):
                return None
            doa = get_doa()
            if doa is None:
                return None
            angle, speech_detected = doa
            return float(angle), bool(speech_detected)
        except Exception as exc:
            _LOGGER.debug("Unable to read microphone DOA: %s", exc)
            return None
