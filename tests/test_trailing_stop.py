from decimal import Decimal

from money_dahong.backtest.engine import Backtester
from money_dahong.exchange.binance_spot import Kline
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


def test_trailing_stop_exits_before_cross_down() -> None:
    # Use a simple SMA cross to enter, then price spikes and drops.
    strategy = MaCrossStrategy(MaCrossParams(fast_period=2, slow_period=3, ma_type="sma"))
    bt = Backtester(
        symbol="ETHUSDT",
        interval="1m",
        strategy=strategy,
        initial_cash_usdt=Decimal("1000"),
        position_sizing="fixed_notional",
        cash_fraction=Decimal("0.8"),
        order_notional_usdt=Decimal("100"),
        fee_rate=Decimal("0"),
        slippage_bps=Decimal("0"),
        lookback_bars=strategy.lookback_bars,
        trailing_stop_enabled=True,
        trailing_start_profit_pct=Decimal("30"),
        trailing_drawdown_pct=Decimal("10"),
    )

    # Sequence:
    # - enter on cross up around 3
    # - peak reaches 4 (+33%)
    # - then drop to 3.5 (12.5% from peak) triggers trailing stop exit
    klines = [
        _k("1", 0),
        _k("1", 1000),
        _k("1", 2000),
        _k("1", 3000),
        _k("3", 4000),  # BUY should trigger
        _k("4", 5000),  # peak profit >= 30%
        _k("3.5", 6000),  # drawdown >= 10% from peak triggers trailing stop
        _k("3.5", 7000),
    ]
    bt.run(klines=klines)
    assert bt.trades
    assert bt.trades[-1].exit_reason == "trailing_stop"
