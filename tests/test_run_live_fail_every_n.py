import logging
import os

import pytest

import run_live


def test_run_live_fake_exchange_fail_every_n(monkeypatch, caplog):
    """Run a short live loop using the FakeExchange with FORCE_FAIL_EVERY_N and assert the circuit opens."""
    # Configure environment for deterministic every-N failures
    monkeypatch.setenv('USE_FAKE_EXCHANGE', '1')
    # Use 1 to deterministically fail every call for reliable opening of circuit in short run
    monkeypatch.setenv('FORCE_FAIL_EVERY_N', '1')
    monkeypatch.setenv('FORCE_FAIL_MODE', '')
    monkeypatch.setenv('DRY_RUN', '1')
    monkeypatch.setenv('RUN_STEPS', '8')
    monkeypatch.setenv('POLL_INTERVAL', '0.01')
    monkeypatch.setenv('FORCE_ACTION', '1.0')
    # relax limits so orders are attempted
    monkeypatch.setenv('MAX_ACCOUNT_NOTIONAL_USD', '1000000')
    monkeypatch.setenv('MIN_ORDER_USD', '0.0')
    monkeypatch.setenv('PM_COOLDOWN_SECONDS', '0.0')

    caplog.set_level(logging.WARNING)
    # Run main; it should exit after RUN_STEPS
    run_live.main()

    # Assert that the circuit breaker opened during the run (warning logged)
    logs = "\n".join([r.getMessage() for r in caplog.records])
    assert 'CircuitBreaker opened' in logs or 'CircuitBreaker moved to OPEN' in logs
