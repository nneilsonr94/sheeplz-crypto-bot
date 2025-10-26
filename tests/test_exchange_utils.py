import pytest

from exchanges.exchange_utils import execute_with_cb
from exchanges.circuit_breaker import State
from exchanges.position_manager import PositionManager
from exchanges.circuit_breaker import CircuitBreaker


class DummyPosman:
    def __init__(self):
        self.success_calls = 0
        self.fail_calls = 0

    def record_success_for_symbol(self, symbol: str):
        self.success_calls += 1

    def record_failure_for_symbol(self, symbol: str):
        self.fail_calls += 1


def test_execute_with_cb_success():
    pm = DummyPosman()

    def _ok(symbol, side, amt):
        return {'id': 'ok', 'symbol': symbol, 'side': side, 'amount': amt}

    res = execute_with_cb(pm, 'BTC-USD', _ok, 'BTC-USD', 'buy', 0.001)
    assert res['id'] == 'ok'
    assert pm.success_calls == 1
    assert pm.fail_calls == 0


def test_execute_with_cb_failure():
    pm = DummyPosman()

    def _fail(symbol, side, amt):
        raise RuntimeError('boom')

    with pytest.raises(RuntimeError):
        execute_with_cb(pm, 'BTC-USD', _fail, 'BTC-USD', 'sell', 0.002)

    assert pm.fail_calls == 1
    assert pm.success_calls == 0


def test_execute_with_cb_triggers_circuit_breaker():
    # Use a real PositionManager and attach a low-threshold CircuitBreaker
    pm = PositionManager()
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.5)
    pm.set_circuit_breaker_for_symbol('BTC-USD', cb)

    def _fail(symbol, side, amt):
        raise RuntimeError('boom')

    # two failures should open the circuit
    for _ in range(2):
        with pytest.raises(RuntimeError):
            execute_with_cb(pm, 'BTC-USD', _fail, 'BTC-USD', 'sell', 0.001)

    assert pm._get_cb('BTC-USD').state == State.OPEN
