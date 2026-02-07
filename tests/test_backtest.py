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


def test_backtest_runs_and_records_trade() -> None:
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
        trailing_stop_enabled=False,
        trailing_start_profit_pct=Decimal("30"),
        trailing_drawdown_pct=Decimal("10"),
    )

    # Add a dummy last "forming" bar; backtester ignores last bar like live runner.
    klines = [
        _k("1", 0),
        _k("1", 1000),
        _k("1", 2000),
        _k("1", 3000),
        _k("3", 4000),  # BUY should trigger here
        _k("3", 5000),
        _k("3", 6000),
        _k("3", 7000),
        _k("1", 8000),  # SELL should trigger here
        _k("1", 9000),
    ]
    result = bt.run(klines=klines)
    assert result.bars == len(klines) - 1
    assert result.trades == 1
    assert bt.trades[0].pnl_usdt != Decimal("0")
    assert bt.trades[0].exit_reason == "cross_down"


def test_backtest_slippage_reduces_pnl() -> None:
    strategy = MaCrossStrategy(MaCrossParams(fast_period=2, slow_period=3, ma_type="sma"))
    common_kwargs = dict(
        symbol="ETHUSDT",
        interval="1m",
        strategy=strategy,
        initial_cash_usdt=Decimal("1000"),
        position_sizing="fixed_notional",
        cash_fraction=Decimal("0.8"),
        order_notional_usdt=Decimal("100"),
        fee_rate=Decimal("0"),
        lookback_bars=strategy.lookback_bars,
        trailing_stop_enabled=False,
        trailing_start_profit_pct=Decimal("30"),
        trailing_drawdown_pct=Decimal("10"),
    )
    bt_no_slip = Backtester(slippage_bps=Decimal("0"), **common_kwargs)
    bt_slip = Backtester(slippage_bps=Decimal("50"), **common_kwargs)

    klines = [
        _k("1", 0),
        _k("1", 1000),
        _k("1", 2000),
        _k("1", 3000),
        _k("3", 4000),  # BUY
        _k("3", 5000),
        _k("3", 6000),
        _k("3", 7000),
        _k("1", 8000),  # SELL
        _k("1", 9000),
    ]
    bt_no_slip.run(klines=klines)
    bt_slip.run(klines=klines)

    assert bt_no_slip.trades
    assert bt_slip.trades
    assert bt_slip.trades[0].pnl_usdt < bt_no_slip.trades[0].pnl_usdt
