"""Helpers for executing exchange calls with circuit-breaker bookkeeping.

Provides a small wrapper to execute an exchange function and record
success/failure in a provided PositionManager for a given symbol.
"""
from __future__ import annotations
from typing import Any, Callable
import logging

logger = logging.getLogger(__name__)


def execute_with_cb(posman, symbol: str, fn: Callable[..., Any], *args, **kwargs) -> Any:
    """Execute fn(*args, **kwargs). On success call posman.record_success_for_symbol(symbol).
    On exception call posman.record_failure_for_symbol(symbol) and re-raise the exception.
    """
    try:
        res = fn(*args, **kwargs)
        try:
            posman.record_success_for_symbol(symbol)
        except Exception:
            logger.exception("Failed to record success for symbol %s", symbol)
        return res
    except Exception:
        try:
            posman.record_failure_for_symbol(symbol)
        except Exception:
            logger.exception("Failed to record failure for symbol %s", symbol)
        raise


__all__ = ["execute_with_cb"]
