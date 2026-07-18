"""Official-style TTS audio to head motion worker."""

from __future__ import annotations

import queue
import threading
import time
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray

from ..motion.speech_sway import HOP_MS, SpeechSwayRT
from .audio_player_shared import MOVEMENT_LATENCY_S

if TYPE_CHECKING:
    from collections.abc import Callable

_ZERO_SWAY = {"pitch_rad": 0.0, "yaw_rad": 0.0, "roll_rad": 0.0, "x_m": 0.0, "y_m": 0.0, "z_m": 0.0}


class HeadWobbler:
    """Convert TTS PCM chunks into audio-reactive head offsets on a worker thread."""

    def __init__(self, apply_offsets: Callable[[dict[str, float]], None]) -> None:
        self._apply_offsets = apply_offsets
        self._base_ts: float | None = None
        self._hops_done = 0
        self._generation = 0

        self._audio_queue: queue.Queue[tuple[int, int, NDArray[Any]]] = queue.Queue()
        self._sway = SpeechSwayRT()
        self._state_lock = threading.Lock()
        self._sway_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._working_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self.reset(apply_zero=True)

    def finish(self, timeout_s: float = 0.7) -> None:
        deadline = time.monotonic() + max(0.0, timeout_s)
        while time.monotonic() < deadline:
            if self._audio_queue.unfinished_tasks <= 0:
                break
            time.sleep(0.01)
        self.stop()

    def reset(self, apply_zero: bool = False) -> None:
        with self._state_lock:
            self._generation += 1
            self._base_ts = None
            self._hops_done = 0

        while True:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break
            else:
                self._audio_queue.task_done()

        with self._sway_lock:
            self._sway.reset()

        if apply_zero:
            self._apply_offsets(_ZERO_SWAY)

    def feed(self, pcm: NDArray[Any], sample_rate: int) -> None:
        with self._state_lock:
            generation = self._generation
        self._audio_queue.put((generation, int(sample_rate), np.asarray(pcm).copy()))

    def _working_loop(self) -> None:
        hop_dt = HOP_MS / 1000.0
        while not self._stop_event.is_set():
            try:
                chunk_generation, sample_rate, chunk = self._audio_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            try:
                with self._state_lock:
                    current_generation = self._generation
                    if chunk_generation != current_generation:
                        continue
                    if self._base_ts is None:
                        self._base_ts = time.monotonic()
                    base_ts = self._base_ts

                with self._sway_lock:
                    results = self._sway.feed(chunk, sample_rate)

                for result in results:
                    with self._state_lock:
                        if self._generation != current_generation:
                            break
                        hops_done = self._hops_done

                    target = base_ts + MOVEMENT_LATENCY_S + hops_done * hop_dt
                    now = time.monotonic()
                    if now - target >= hop_dt:
                        lag_hops = int((now - target) / hop_dt)
                        with self._state_lock:
                            self._hops_done += lag_hops
                        continue
                    if target > now:
                        time.sleep(target - now)
                        with self._state_lock:
                            if self._generation != current_generation:
                                break

                    self._apply_offsets(result)
                    with self._state_lock:
                        self._hops_done += 1
            finally:
                self._audio_queue.task_done()
