"""
Worker Pool — adaptive concurrency engine with CPU-aware throttling.

Features:
  1. Queue-based task dispatch
  2. Up to MAX_WORKERS concurrent threads
  3. CPU usage monitoring — scales workers up/down
  4. Per-task result collection
  5. Deterministic ordering of results

Usage:
    pool = WorkerPool()
    futures = pool.submit_batch(tasks, worker_fn)
    results = pool.collect(futures)
    pool.shutdown()
"""

from __future__ import annotations

import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, TypeVar

from rich.console import Console

from jcode.config import (
    MAX_WORKERS,
    MIN_WORKERS,
    CPU_HIGH_THRESHOLD,
    CPU_LOW_THRESHOLD,
    WORKER_POLL_INTERVAL,
)

console = Console()

T = TypeVar("T")


@dataclass
class WorkerResult:
    """Result from a single worker task."""
    task_id: int
    success: bool
    result: Any = None
    error: str = ""
    duration_ms: int = 0


class WorkerPool:
    """
    Adaptive thread pool with CPU-aware concurrency.

    - Starts with MAX_WORKERS threads
    - Monitors CPU usage and adjusts concurrency
    - Provides submit_batch / collect API
    - Thread-safe via internal locks
    """

    def __init__(self, max_workers: int | None = None) -> None:
        self._max = max_workers or MAX_WORKERS
        self._current_workers = min(self._max, 4)  # Start moderate
        self._executor = ThreadPoolExecutor(max_workers=self._max)
        self._lock = threading.Lock()
        self._active_count = 0
        self._semaphore = threading.Semaphore(self._current_workers)
        self._monitor_thread: threading.Thread | None = None
        self._shutdown = False

        # Start CPU monitor
        self._start_monitor()

    def _start_monitor(self) -> None:
        """Start background CPU monitoring thread."""
        self._monitor_thread = threading.Thread(
            target=self._cpu_monitor_loop, daemon=True
        )
        self._monitor_thread.start()

    def _cpu_monitor_loop(self) -> None:
        """Periodically check CPU usage and adjust concurrency."""
        while not self._shutdown:
            try:
                cpu = self._get_cpu_usage()
                with self._lock:
                    old = self._current_workers
                    if cpu > CPU_HIGH_THRESHOLD and self._current_workers > MIN_WORKERS:
                        self._current_workers = max(MIN_WORKERS, self._current_workers - 1)
                    elif cpu < CPU_LOW_THRESHOLD and self._current_workers < self._max:
                        self._current_workers = min(self._max, self._current_workers + 1)

                    if self._current_workers != old:
                        # Adjust semaphore
                        diff = self._current_workers - old
                        if diff > 0:
                            for _ in range(diff):
                                self._semaphore.release()
                        # If shrinking, the semaphore will naturally block new acquisitions
            except Exception:
                pass
            time.sleep(WORKER_POLL_INTERVAL)

    @staticmethod
    def _get_cpu_usage() -> float:
        """Get current CPU usage percentage. Cross-platform."""
        try:
            import psutil
            return psutil.cpu_percent(interval=0.5)
        except ImportError:
            # Fallback: use os.getloadavg on Unix
            try:
                load1, _, _ = os.getloadavg()
                cpu_count = os.cpu_count() or 1
                return min(100.0, (load1 / cpu_count) * 100.0)
            except (OSError, AttributeError):
                return 50.0  # Assume moderate if we can't measure

    def submit(
        self,
        fn: Callable[..., T],
        *args: Any,
        task_id: int = 0,
        **kwargs: Any,
    ) -> Future[WorkerResult]:
        """Submit a single task to the pool with concurrency throttling."""

        def _wrapped() -> WorkerResult:
            # Acquire semaphore to respect concurrency limit
            self._semaphore.acquire()
            with self._lock:
                self._active_count += 1

            start = time.monotonic()
            try:
                result = fn(*args, **kwargs)
                elapsed = int((time.monotonic() - start) * 1000)
                return WorkerResult(
                    task_id=task_id,
                    success=True,
                    result=result,
                    duration_ms=elapsed,
                )
            except Exception as e:
                elapsed = int((time.monotonic() - start) * 1000)
                return WorkerResult(
                    task_id=task_id,
                    success=False,
                    error=str(e),
                    duration_ms=elapsed,
                )
            finally:
                with self._lock:
                    self._active_count -= 1
                self._semaphore.release()

        return self._executor.submit(_wrapped)

    def submit_batch(
        self,
        tasks: list[dict],
        fn: Callable[..., Any],
    ) -> list[Future[WorkerResult]]:
        """
        Submit a batch of tasks. Each task dict must have an 'id' key.
        The function `fn` receives the task dict as its only argument.
        """
        futures = []
        for task in tasks:
            future = self.submit(fn, task, task_id=task.get("id", 0))
            futures.append(future)
        return futures

    def collect(
        self,
        futures: list[Future[WorkerResult]],
        timeout: float | None = None,
    ) -> list[WorkerResult]:
        """
        Wait for all futures and return results in submission order.
        """
        results = []
        for f in futures:
            try:
                result = f.result(timeout=timeout)
                results.append(result)
            except Exception as e:
                results.append(WorkerResult(
                    task_id=-1, success=False, error=str(e),
                ))
        return results

    @property
    def active_count(self) -> int:
        """Number of currently active workers."""
        with self._lock:
            return self._active_count

    @property
    def current_concurrency(self) -> int:
        """Current concurrency limit (may be adjusted by CPU monitor)."""
        with self._lock:
            return self._current_workers

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the pool."""
        self._shutdown = True
        self._executor.shutdown(wait=wait)

    def __enter__(self) -> "WorkerPool":
        return self

    def __exit__(self, *args) -> None:
        self.shutdown()
