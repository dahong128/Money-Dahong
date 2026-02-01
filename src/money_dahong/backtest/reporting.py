from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from money_dahong.backtest.engine import EquityPoint, Trade


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    return str(obj)


def _now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _safe_name(value: str) -> str:
    keep = []
    for ch in value.strip():
        if ch.isalnum() or ch in ("-", "_", "."):
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep).strip("_") or "run"


def write_backtest_report(
    *,
    report_root: Path,
    report_name: str,
    summary: dict[str, Any],
    trades: list[Trade],
    equity_curve: list[EquityPoint],
) -> Path:
    """
    Writes:
      - report.md
      - summary.json
      - trades.csv
      - equity.csv
    Returns the report directory path.
    """
    report_dir = report_root / f"{_now_stamp()}_{_safe_name(report_name)}"
    report_dir.mkdir(parents=True, exist_ok=False)

    (report_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )

    with (report_dir / "trades.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "entry_time_ms",
                "exit_time_ms",
                "side",
                "entry_price",
                "exit_price",
                "quantity",
                "pnl_usdt",
            ],
        )
        writer.writeheader()
        for t in trades:
            row = asdict(t)
            row["entry_price"] = str(t.entry_price)
            row["exit_price"] = str(t.exit_price)
            row["quantity"] = str(t.quantity)
            row["pnl_usdt"] = str(t.pnl_usdt)
            writer.writerow(row)

    with (report_dir / "equity.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["time_ms", "close", "cash", "qty", "equity"],
        )
        writer.writeheader()
        for p in equity_curve:
            writer.writerow(
                {
                    "time_ms": p.time_ms,
                    "close": str(p.close),
                    "cash": str(p.cash),
                    "qty": str(p.qty),
                    "equity": str(p.equity),
                }
            )

    # Simple human-readable markdown report
    lines: list[str] = []
    lines.append(f"# Backtest Report: {summary.get('symbol')} {summary.get('interval')}")
    lines.append("")
    lines.append("## Summary")
    for key in (
        "strategy_id",
        "ma_type",
        "fast",
        "slow",
        "bars",
        "trades",
        "start_equity_usdt",
        "end_equity_usdt",
        "return_pct",
        "max_drawdown_pct",
        "fee_rate",
        "order_notional_usdt",
    ):
        if key in summary:
            lines.append(f"- {key}: `{summary[key]}`")
    lines.append("")

    if trades:
        wins = sum(1 for t in trades if t.pnl_usdt > 0)
        win_rate = (Decimal(wins) / Decimal(len(trades))) * Decimal("100")
        lines.append("## Trades")
        lines.append(f"- win_rate_pct: `{str(win_rate)}`")
        lines.append("")
        lines.append("See `trades.csv` for details.")
        lines.append("")

    lines.append("## Files")
    lines.append("- `summary.json`")
    lines.append("- `trades.csv`")
    lines.append("- `equity.csv`")
    lines.append("")

    (report_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return report_dir
