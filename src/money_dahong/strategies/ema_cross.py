from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from money_dahong.exchange.binance_spot import Kline
from money_dahong.math_utils import ema_series
from money_dahong.strategies.base import Strategy, StrategyContext
from money_dahong.types import Signal


@dataclass(frozen=True)
class EmaCrossParams:
    fast_period: int = 12
    slow_period: int = 26


class EmaCrossStrategy(Strategy):
    strategy_id = "ema_cross"

    def __init__(self, params: EmaCrossParams) -> None:
        if params.fast_period >= params.slow_period:
            raise ValueError("fast_period must be < slow_period")
        self._params = params

    def generate_signal(self, *, klines: list[Kline], ctx: StrategyContext) -> Optional[Signal]:
        if len(klines) < self._params.slow_period + 2:
            return None

        closes = [k.close for k in klines]
        fast = ema_series(closes, self._params.fast_period)
        slow = ema_series(closes, self._params.slow_period)

        fast_prev, fast_now = fast[-2], fast[-1]
        slow_prev, slow_now = slow[-2], slow[-1]

        crossed_up = fast_prev <= slow_prev and fast_now > slow_now
        crossed_down = fast_prev >= slow_prev and fast_now < slow_now

        if not ctx.in_position and crossed_up:
            return Signal(side="BUY", reason="ema_cross_up")
        if ctx.in_position and crossed_down:
            return Signal(side="SELL", reason="ema_cross_down")
        return None
