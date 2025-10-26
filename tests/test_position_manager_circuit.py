import time

from exchanges.position_manager import PositionManager
from exchanges.circuit_breaker import CircuitBreaker, State


def test_per_symbol_circuit_breaker_blocks_trades():
    pm = PositionManager()
    sym = 'BTC-USD'
    # default breaker allows trades
    assert pm.allow_trade_for_symbol(sym) is True

    # install a strict breaker for the symbol (threshold=1)
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.2)
    pm.set_circuit_breaker_for_symbol(sym, cb)

    # record a failure -> breaker opens
    pm.record_failure_for_symbol(sym)
    assert cb.state == State.OPEN
    assert pm.allow_trade_for_symbol(sym) is False

    # wait for timeout -> half-open
    time.sleep(0.25)
    assert cb.state == State.HALF_OPEN
    assert pm.allow_trade_for_symbol(sym) is True

    # a recorded success should close the breaker
    pm.record_success_for_symbol(sym)
    assert cb.state == State.CLOSED
    assert pm.allow_trade_for_symbol(sym) is True
