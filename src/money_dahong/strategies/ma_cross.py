from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Optional

from money_dahong.exchange.binance_spot import Kline
from money_dahong.math_utils import ema_series, sma
from money_dahong.strategies.base import Strategy, StrategyContext
from money_dahong.types import Signal

MaType = Literal["sma", "ema"]


@dataclass(frozen=True)
class MaCrossParams:
    fast_period: int = 20
    slow_period: int = 60
    ma_type: MaType = "sma"


def _ma_prev_now(closes: list[Decimal], *, period: int, ma_type: MaType) -> tuple[Decimal, Decimal]:
    if len(closes) < period + 1:
        raise ValueError("not enough closes for prev/now")

    if ma_type == "sma":
        prev = sma(closes[:-1], period)
        now = sma(closes, period)
        return prev, now

    ema = ema_series(closes, period)
    return ema[-2], ema[-1]


class MaCrossStrategy(Strategy):
    strategy_id = "ma_cross"

    def __init__(self, params: MaCrossParams) -> None:
        if params.fast_period <= 0 or params.slow_period <= 0:
            raise ValueError("periods must be > 0")
        if params.fast_period >= params.slow_period:
            raise ValueError("fast_period must be < slow_period")
        self._params = params

    @property
    def lookback_bars(self) -> int:
        # Need two bars to detect cross, plus slow period lookback.
        return self._params.slow_period + 2

    def generate_signal(self, *, klines: list[Kline], ctx: StrategyContext) -> Optional[Signal]:
        if len(klines) < self.lookback_bars:
            return None

        closes = [k.close for k in klines]
        fast_prev, fast_now = _ma_prev_now(
            closes,
            period=self._params.fast_period,
            ma_type=self._params.ma_type,
        )
        slow_prev, slow_now = _ma_prev_now(
            closes,
            period=self._params.slow_period,
            ma_type=self._params.ma_type,
        )

        crossed_up = fast_prev <= slow_prev and fast_now > slow_now
        crossed_down = fast_prev >= slow_prev and fast_now < slow_now

        if not ctx.in_position and crossed_up:
            return Signal(side="BUY", reason=f"{self._params.ma_type}_cross_up")
        if ctx.in_position and crossed_down:
            return Signal(side="SELL", reason=f"{self._params.ma_type}_cross_down")
        return None

