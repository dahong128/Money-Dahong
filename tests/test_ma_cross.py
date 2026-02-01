from decimal import Decimal

from money_dahong.exchange.binance_spot import Kline
from money_dahong.strategies.base import StrategyContext
from money_dahong.strategies.ma_cross import MaCrossParams, MaCrossStrategy


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


def test_ma_cross_sma_buy_then_sell() -> None:
    s = MaCrossStrategy(MaCrossParams(fast_period=2, slow_period=3, ma_type="sma"))
    ctx_flat = StrategyContext(symbol="ETHUSDT", in_position=False, position_qty=Decimal("0"))

    up = [_k(str(v), i * 1000) for i, v in enumerate([1, 1, 1, 1, 3])]
    sig_buy = s.generate_signal(klines=up, ctx=ctx_flat)
    assert sig_buy is not None and sig_buy.side == "BUY"

    ctx_in = StrategyContext(symbol="ETHUSDT", in_position=True, position_qty=Decimal("1"))
    down = [_k(str(v), i * 1000) for i, v in enumerate([3, 3, 3, 3, 1])]
    sig_sell = s.generate_signal(klines=down, ctx=ctx_in)
    assert sig_sell is not None and sig_sell.side == "SELL"

