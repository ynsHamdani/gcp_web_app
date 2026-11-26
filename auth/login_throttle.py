from __future__ import annotations

"""Process-local login throttling for the single-process development server.

Production deployments with multiple workers must replace this in-memory
limiter with a shared store (for example Redis or a database-backed limiter).
"""

from collections import deque
from hashlib import sha256
from math import ceil
from threading import RLock
from time import monotonic
from typing import Callable


class LoginThrottle:
    """Sliding-window limiter keyed by a normalized identifier and IP address."""

    def __init__(
        self,
        *,
        window_seconds: int = 15 * 60,
        identifier_limit: int = 5,
        address_limit: int = 30,
        clock: Callable[[], float] = monotonic,
        max_buckets: int = 10_000,
    ) -> None:
        if window_seconds < 1 or identifier_limit < 1 or address_limit < 1:
            raise ValueError("Login throttle limits must be positive.")
        self.window_seconds = int(window_seconds)
        self.identifier_limit = int(identifier_limit)
        self.address_limit = int(address_limit)
        self.max_buckets = max(100, int(max_buckets))
        self._clock = clock
        self._failures: dict[tuple[str, str], deque[float]] = {}
        self._lock = RLock()

    @staticmethod
    def _digest(value: str) -> str:
        return sha256(value.encode("utf-8", errors="replace")).hexdigest()

    def _keys(self, identifier: str, remote_addr: str | None) -> tuple[tuple[str, str], tuple[str, str]]:
        normalized_identifier = str(identifier or "").strip().casefold()[:320]
        normalized_address = str(remote_addr or "unknown")[:100]
        return (
            ("identifier", self._digest(normalized_identifier)),
            ("address", self._digest(normalized_address)),
        )

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        expired = []
        for key, events in self._failures.items():
            while events and events[0] <= cutoff:
                events.popleft()
            if not events:
                expired.append(key)
        for key in expired:
            self._failures.pop(key, None)

    def _retry_after_locked(self, keys: tuple[tuple[str, str], tuple[str, str]], now: float) -> int:
        retry = 0
        for key, limit in zip(keys, (self.identifier_limit, self.address_limit)):
            events = self._failures.get(key)
            if events and len(events) >= limit:
                retry = max(retry, ceil(self.window_seconds - (now - events[0])))
        return max(0, retry)

    def retry_after(self, identifier: str, remote_addr: str | None) -> int:
        now = self._clock()
        keys = self._keys(identifier, remote_addr)
        with self._lock:
            self._prune(now)
            return self._retry_after_locked(keys, now)

    def record_failure(self, identifier: str, remote_addr: str | None) -> int:
        now = self._clock()
        keys = self._keys(identifier, remote_addr)
        with self._lock:
            self._prune(now)
            for key in keys:
                self._failures.setdefault(key, deque()).append(now)
            while len(self._failures) > self.max_buckets:
                self._failures.pop(next(iter(self._failures)))
            return self._retry_after_locked(keys, now)

    def clear_identifier(self, identifier: str) -> None:
        key = self._keys(identifier, "unknown")[0]
        with self._lock:
            self._failures.pop(key, None)

    def reset(self) -> None:
        """Clear all buckets; intended for isolated tests and controlled resets."""
        with self._lock:
            self._failures.clear()
