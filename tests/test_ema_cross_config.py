from pathlib import Path

import pytest

from money_dahong.config.ema_cross import load_ema_cross_run_config


def test_load_ema_cross_config(tmp_path: Path) -> None:
    p = tmp_path / "ema_cross.toml"
    p.write_text(
        """
[market]
symbol = "BTCUSDT"
interval = "15m"

[strategy]
fast_period = 9
slow_period = 21
""",
        encoding="utf-8",
    )
    cfg = load_ema_cross_run_config(p)
    assert cfg.market.symbol == "BTCUSDT"
    assert cfg.market.interval == "15m"
    assert cfg.strategy.fast_period == 9
    assert cfg.strategy.slow_period == 21


def test_load_ema_cross_config_rejects_invalid_periods(tmp_path: Path) -> None:
    p = tmp_path / "bad.toml"
    p.write_text(
        """
[strategy]
fast_period = 30
slow_period = 20
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_ema_cross_run_config(p)
