"""Private camera helpers for voice feedback.

The official Reachy Mini Home Assistant integration owns camera entities and
streaming. This module only provides a rate-limited JPEG snapshot for local
voice behaviors such as face-tracking diagnostics.
"""

from __future__ import annotations

import logging
import time
from typing import Any

_LOGGER = logging.getLogger(__name__)


class CameraFrameSource:
    """Read and cache JPEG frames from the SDK without publishing a camera."""

    def __init__(self, reachy_mini: Any, refresh_hz: float = 5.0, *, enabled: bool = True) -> None:
        self._reachy_mini = reachy_mini
        self._enabled = enabled
        self._minimum_interval_s = 1.0 / max(0.1, refresh_hz)
        self._last_capture_time = 0.0
        self._latest_frame: bytes | None = None

    @property
    def available(self) -> bool:
        if not self._enabled:
            return False
        media = getattr(self._reachy_mini, "media", None)
        return callable(getattr(media, "get_frame_jpeg", None))

    def capture(self, *, force: bool = False) -> bytes | None:
        """Return the newest SDK JPEG frame without exceeding its rate."""
        if not self._enabled:
            return None

        now = time.monotonic()
        if not force and now - self._last_capture_time < self._minimum_interval_s:
            return self._latest_frame

        self._last_capture_time = now
        media = getattr(self._reachy_mini, "media", None)
        get_frame_jpeg = getattr(media, "get_frame_jpeg", None)
        if not callable(get_frame_jpeg):
            return self._latest_frame

        try:
            frame = get_frame_jpeg()
        except Exception as exc:
            _LOGGER.debug("JPEG frame capture failed: %s", exc)
            return self._latest_frame

        if isinstance(frame, bytes) and frame:
            self._latest_frame = frame
        return self._latest_frame
