"""Lightweight adapter to 'wire' the vendored Tradingview scripts into the bot.

This adapter does NOT execute Pine scripts. Instead it exposes a tiny API that
loads available Tradingview script filenames (from vendor/Tradingview) and
provides a deterministic, explainable "signal" based on recent price history.

You can later replace the heuristic here with a proper translator or an RPC
call to a TradingView execution environment.
"""
from collections import deque
from typing import Deque, List, Optional
import os
import statistics

VENDOR_TV_PATH = os.path.join(os.path.dirname(__file__), '..', 'vendor', 'Tradingview')


def available_scripts() -> List[str]:
    path = os.path.abspath(VENDOR_TV_PATH)
    try:
        files = [f for f in os.listdir(path) if f.lower().endswith('.pine') or f.lower().endswith('.txt') or f.lower().endswith('')]
        return files
    except Exception:
        return []


def get_signal_from_prices(prices: List[float]) -> Optional[str]:
    """Simple heuristic:

    - if last price > mean(prices) by a threshold => 'buy'
    - if last price < mean(prices) by a threshold => 'sell'
    - otherwise => None
    """
    if not prices or len(prices) < 3:
        return None
    mean = statistics.mean(prices)
    last = prices[-1]
    # dynamic threshold: 0.5% of mean
    thresh = 0.005 * mean
    if last - mean > thresh:
        return 'buy'
    if mean - last > thresh:
        return 'sell'
    return None


def signal_to_action(signal: Optional[str]) -> float:
    """Map a signal to a normalized action in [-1, 1].

    buy -> +0.6, sell -> -0.6, None -> 0.0
    """
    if signal == 'buy':
        return 0.6
    if signal == 'sell':
        return -0.6
    return 0.0


class PriceBuffer:
    def __init__(self, size: int = 20):
        self.size = size
        self.buf: Deque[float] = deque(maxlen=size)

    def add(self, price: float) -> None:
        self.buf.append(float(price))

    def to_list(self) -> List[float]:
        return list(self.buf)
