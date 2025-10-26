import time

from exchanges.circuit_breaker import CircuitBreaker, State


def test_circuit_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.5)
    assert cb.allow_request() is True
    cb.record_failure()
    # still closed until threshold
    assert cb.state == State.CLOSED
    cb.record_failure()
    assert cb.state == State.OPEN
    assert cb.allow_request() is False


def test_circuit_half_open_after_timeout():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.2)
    cb.record_failure()
    assert cb.state == State.OPEN
    assert cb.allow_request() is False
    # wait for timeout
    time.sleep(0.25)
    assert cb.state == State.HALF_OPEN
    assert cb.allow_request() is True


def test_success_resets_circuit():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=1.0)
    cb.record_failure()
    assert cb.state == State.OPEN
    time.sleep(1.1)
    # half-open now
    assert cb.state == State.HALF_OPEN
    # success should close and reset failures
    cb.record_success()
    assert cb.state == State.CLOSED
    assert cb.allow_request() is True
