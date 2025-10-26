import logging
import os

import pytest

import run_live


def test_run_live_fake_exchange_forced_failures(monkeypatch, caplog):
    """Run a short live loop using the FakeExchange in deterministic fail mode and assert the circuit opens."""
    # Configure environment for deterministic failures
    monkeypatch.setenv('USE_FAKE_EXCHANGE', '1')
    monkeypatch.setenv('FORCE_FAIL_MODE', 'always')
    monkeypatch.setenv('DRY_RUN', '1')
    # increase steps to ensure enough failing attempts to trip the circuit
    monkeypatch.setenv('RUN_STEPS', '12')
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