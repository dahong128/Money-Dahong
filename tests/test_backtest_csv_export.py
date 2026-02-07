from decimal import Decimal
from pathlib import Path

from money_dahong.backtest.engine import Trade
from money_dahong.cli import _write_trades_csv


def test_write_trades_csv(tmp_path: Path) -> None:
    path = tmp_path / "out" / "trades.csv"
    trades = [
        Trade(
            entry_time_ms=1_700_000_000_000,
            exit_time_ms=1_700_000_060_000,
            side="LONG",
            exit_reason="cross_down",
            entry_price=Decimal("100"),
            exit_price=Decimal("101"),
            quantity=Decimal("0.5"),
            pnl_usdt=Decimal("0.5"),
            max_runup_pct=Decimal("3.2"),
        )
    ]

    _write_trades_csv(path=path, trades=trades)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("entry_time_ms,entry_time_utc,exit_time_ms,exit_time_utc")
    assert "cross_down" in lines[1]
    assert "0.5" in lines[1]
