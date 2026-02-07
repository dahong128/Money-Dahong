from pathlib import Path

import pytest

from money_dahong.config.ma_cross import load_ma_cross_backtest_config


def test_load_ma_cross_config(tmp_path: Path) -> None:
    p = tmp_path / "ma_cross.toml"
    p.write_text(
        """
[market]
symbol = "ETHUSDT"
interval = "1h"
limit = 2000
start_utc = "2024-01-01T00:00:00Z"
end_utc = "2024-12-31T23:59:59Z"

[strategy]
ma_type = "ema"
fast_period = 10
slow_period = 30

[backtest]
initial_cash_usdt = 1000
position_sizing = "cash_fraction"
cash_fraction = 0.8
order_notional_usdt = 25
fee_rate = 0.001
slippage_bps = 5
trades_csv = "build/trades.csv"

[risk]
trailing_stop_enabled = true
trailing_start_profit_pct = 30
trailing_drawdown_pct = 10
""",
        encoding="utf-8",
    )
    cfg = load_ma_cross_backtest_config(p)
    assert cfg.market.symbol == "ETHUSDT"
    assert cfg.market.interval == "1h"
    assert cfg.market.limit == 2000
    assert cfg.market.start_utc == "2024-01-01T00:00:00Z"
    assert cfg.market.end_utc == "2024-12-31T23:59:59Z"
    assert cfg.strategy.ma_type == "ema"
    assert cfg.strategy.fast_period == 10
    assert cfg.strategy.slow_period == 30
    assert cfg.backtest.position_sizing == "cash_fraction"
    assert cfg.backtest.slippage_bps == 5
    assert cfg.backtest.trades_csv == "build/trades.csv"
    assert cfg.risk.trailing_stop_enabled is True


def test_load_ma_cross_config_rejects_invalid_periods(tmp_path: Path) -> None:
    p = tmp_path / "bad.toml"
    p.write_text(
        """
[strategy]
ma_type = "sma"
fast_period = 60
slow_period = 20
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_ma_cross_backtest_config(p)
