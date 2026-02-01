from decimal import Decimal
from pathlib import Path

from money_dahong.backtest.engine import EquityPoint, Trade
from money_dahong.backtest.reporting import write_backtest_report


def test_write_backtest_report_creates_files(tmp_path: Path) -> None:
    summary = {
        "symbol": "ETHUSDT",
        "interval": "1m",
        "strategy_id": "ma_cross",
        "ma_type": "sma",
        "fast": 20,
        "slow": 60,
        "bars": 100,
        "trades": 1,
        "start_equity_usdt": "1000",
        "end_equity_usdt": "1010",
        "return_pct": "1",
        "max_drawdown_pct": "0.5",
        "fee_rate": "0",
        "order_notional_usdt": "25",
    }
    trades = [
        Trade(
            entry_time_ms=1,
            exit_time_ms=2,
            side="LONG",
            entry_price=Decimal("100"),
            exit_price=Decimal("101"),
            quantity=Decimal("0.25"),
            pnl_usdt=Decimal("0.25"),
        )
    ]
    curve = [
        EquityPoint(
            time_ms=2,
            close=Decimal("101"),
            cash=Decimal("900"),
            qty=Decimal("1"),
            equity=Decimal("1001"),
        )
    ]

    report_dir = write_backtest_report(
        report_root=tmp_path,
        report_name="unit_test",
        summary=summary,
        trades=trades,
        equity_curve=curve,
    )

    assert (report_dir / "report.md").exists()
    assert (report_dir / "summary.json").exists()
    assert (report_dir / "trades.csv").exists()
    assert (report_dir / "equity.csv").exists()

