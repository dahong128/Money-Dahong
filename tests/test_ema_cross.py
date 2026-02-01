from decimal import Decimal

from money_dahong.exchange.binance_spot import Kline
from money_dahong.strategies.base import StrategyContext
from money_dahong.strategies.ema_cross import EmaCrossParams, EmaCrossStrategy


def _k(close: str, t: int) -> Kline:
    return Kline(
        open_time_ms=t,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("0"),
        close_time_ms=t + 1,
    )


def test_ema_cross_buy_then_sell() -> None:
    s = EmaCrossStrategy(EmaCrossParams(fast_period=2, slow_period=3))
    ctx_flat = StrategyContext(symbol="ETHUSDT", in_position=False, position_qty=Decimal("0"))

    # Find a BUY on an upswing.
    upswing = [_k(str(v), i * 1000) for i, v in enumerate([10, 10, 10, 10, 10, 30])]
    buy = None
    for i in range(4, len(upswing) + 1):
        buy = s.generate_signal(klines=upswing[:i], ctx=ctx_flat)
        if buy and buy.side == "BUY":
            break
    assert buy is not None and buy.side == "BUY"

    # Find a SELL on a downswing after being in position.
    ctx_in = StrategyContext(symbol="ETHUSDT", in_position=True, position_qty=Decimal("1"))
    downswing = [_k(str(v), i * 1000) for i, v in enumerate([30, 30, 30, 30, 30, 10])]
    sell = None
    for i in range(4, len(downswing) + 1):
        sell = s.generate_signal(klines=downswing[:i], ctx=ctx_in)
        if sell and sell.side == "SELL":
            break
    assert sell is not None and sell.side == "SELL"
