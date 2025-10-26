"""Simple position manager to track simulated positions and enforce safety limits.

This is intentionally small: it keeps a running position in base units, enforces
maximum position exposure in USD, and provides helper checks before placing
orders. It works in paper/dry-run mode and can be extended later to persist
positions or sync with exchange state.
"""
from dataclasses import dataclass
from typing import Optional, Dict
from exchanges.circuit_breaker import CircuitBreaker


@dataclass
class PositionLimits:
    max_notional_usd: float = 1000.0  # maximum USD exposure
    max_base_amount: Optional[float] = None  # optional cap on base currency
    min_order_usd: float = 1.0
    cooldown_seconds: float = 5.0  # minimal seconds between simulated trades
    stop_loss_pct: Optional[float] = None  # e.g. 0.05 for 5% stop loss
    take_profit_pct: Optional[float] = None  # e.g. 0.1 for 10% take profit


class PositionManager:
    def __init__(self, limits: Optional[PositionLimits] = None):
        self.limits = limits or PositionLimits()
        # Track position as signed base amount (positive = long/buy, negative = short/sell)
        self.position_base = 0.0
        self.avg_entry_price = None
        self._last_trade_ts = 0.0
        self.audit_path = None
        # per-symbol circuit breakers (lazy-created)
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}

    def set_circuit_breaker_for_symbol(self, symbol: str, cb: CircuitBreaker) -> None:
        """Explicitly set a CircuitBreaker instance for a symbol."""
        self._circuit_breakers[symbol] = cb

    def _get_cb(self, symbol: str) -> CircuitBreaker:
        cb = self._circuit_breakers.get(symbol)
        if cb is None:
            cb = CircuitBreaker()
            self._circuit_breakers[symbol] = cb
        return cb

    def allow_trade_for_symbol(self, symbol: str, now_ts: Optional[float] = None) -> bool:
        """Return True if trading is allowed for this symbol (cooldown + circuit breaker)."""
        if not self.can_trade(now_ts=now_ts):
            return False
        cb = self._get_cb(symbol)
        return cb.allow_request()

    def record_failure_for_symbol(self, symbol: str) -> None:
        """Record a failed attempt that should count towards the circuit breaker for the symbol."""
        cb = self._get_cb(symbol)
        cb.record_failure()

    def record_success_for_symbol(self, symbol: str) -> None:
        """Record a successful execution for the symbol (resets the breaker)."""
        cb = self._get_cb(symbol)
        cb.record_success()

    def current_position(self):
        return {"base": self.position_base, "avg_entry_price": self.avg_entry_price}

    def would_exceed_limits(self, side: str, amount_base: float, price: float) -> bool:
        """Return True if executing this order would exceed configured limits."""
        usd_notional = abs(amount_base) * price
        if usd_notional < self.limits.min_order_usd:
            return True

        # compute prospective position
        prospective_base = self.position_base + (amount_base if side == "buy" else -amount_base)
        prospective_notional = abs(prospective_base) * price

        if self.limits.max_notional_usd is not None and prospective_notional > self.limits.max_notional_usd:
            return True

        if self.limits.max_base_amount is not None and abs(prospective_base) > self.limits.max_base_amount:
            return True

        return False

    def can_trade(self, now_ts: Optional[float] = None) -> bool:
        """Return False if trade cooldown is in effect."""
        now = now_ts or __import__('time').time()
        if self.limits.cooldown_seconds and (now - self._last_trade_ts) < float(self.limits.cooldown_seconds):
            return False
        return True

    def should_close_for_sl_tp(self, current_price: float):
        """
        Check whether the current position should be closed because of stop-loss or take-profit.
        Returns a tuple (should_close: bool, side_to_close: str, amount_base: float) or (False, None, 0.0).
        """
        if self.position_base == 0 or self.avg_entry_price is None:
            return False, None, 0.0
        # long position
        if self.position_base > 0:
            if self.limits.stop_loss_pct is not None:
                if current_price <= self.avg_entry_price * (1.0 - float(self.limits.stop_loss_pct)):
                    return True, 'sell', abs(self.position_base)
            if self.limits.take_profit_pct is not None:
                if current_price >= self.avg_entry_price * (1.0 + float(self.limits.take_profit_pct)):
                    return True, 'sell', abs(self.position_base)
        else:
            # short position
            if self.limits.stop_loss_pct is not None:
                if current_price >= self.avg_entry_price * (1.0 + float(self.limits.stop_loss_pct)):
                    return True, 'buy', abs(self.position_base)
            if self.limits.take_profit_pct is not None:
                if current_price <= self.avg_entry_price * (1.0 - float(self.limits.take_profit_pct)):
                    return True, 'buy', abs(self.position_base)
        return False, None, 0.0

    def record_trade(self, side: str, amount_base: float, price: float) -> None:
        """Record an executed trade (updates position) and stamp the trade time; also audit to file if configured."""
        # stamp trade time
        import time as _time
        self._last_trade_ts = _time.time()
        # persist audit if requested
        try:
            if self.audit_path:
                import json
                with open(self.audit_path, 'a') as fh:
                    fh.write(json.dumps({'ts': self._last_trade_ts, 'side': side, 'amount': amount_base, 'price': price}) + "\n")
        except Exception:
            pass
        # delegate to existing logic to update position
        # update avg entry price via simple weighted average for the position
        signed_amount = amount_base if side == "buy" else -amount_base
        if self.position_base == 0 or (self.position_base > 0 and signed_amount > 0) or (self.position_base < 0 and signed_amount < 0):
            # extending position in same direction or opening new
            total_base = self.position_base + signed_amount
            if total_base == 0:
                # flat
                self.avg_entry_price = None
                self.position_base = 0.0
                return
            if self.avg_entry_price is None:
                self.avg_entry_price = price
            else:
                # weighted average price
                prev_notional = abs(self.position_base) * (self.avg_entry_price or price)
                add_notional = abs(signed_amount) * price
                self.avg_entry_price = (prev_notional + add_notional) / (abs(self.position_base) + abs(signed_amount))
            self.position_base = total_base
        else:
            # reducing or flipping position
            self.position_base += signed_amount
            if abs(self.position_base) < 1e-12:
                self.position_base = 0.0
                self.avg_entry_price = None


    
