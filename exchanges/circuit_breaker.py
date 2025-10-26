"""Simple circuit breaker utility for exchange calls.

This is a small, safe implementation to start work on a circuit-breaker feature.
It tracks consecutive failures, opens the circuit after a threshold, stays open
for a recovery timeout, then allows a single trial (half-open).
"""
from __future__ import annotations
import time
from enum import Enum
from typing import Optional


class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 60.0):
        self.failure_threshold = int(failure_threshold)
        self.recovery_timeout = float(recovery_timeout)
        self._fail_count = 0
        self._state = State.CLOSED
        self._opened_at: Optional[float] = None

    @property
    def state(self) -> State:
        # If open and timeout expired, move to HALF_OPEN
        if self._state == State.OPEN and self._opened_at is not None:
            if (time.time() - self._opened_at) >= self.recovery_timeout:
                self._state = State.HALF_OPEN
        return self._state

    def allow_request(self) -> bool:
        s = self.state
        if s == State.OPEN:
            return False
        # CLOSED or HALF_OPEN allow a request
        return True

    def record_success(self) -> None:
        # On success, reset and close the circuit
        self._fail_count = 0
        self._state = State.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        # Increment failure count; if threshold reached, open the circuit
        self._fail_count += 1
        if self._fail_count >= self.failure_threshold:
            self._state = State.OPEN
            self._opened_at = time.time()

    def reset(self) -> None:
        self._fail_count = 0
        self._state = State.CLOSED
        self._opened_at = None


__all__ = ["CircuitBreaker", "State"]
