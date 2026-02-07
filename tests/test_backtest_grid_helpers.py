from decimal import Decimal
from pathlib import Path

import pytest

from money_dahong.cli import (
    GridResultRow,
    _build_period_pairs,
    _parse_period_list,
    _rank_grid_rows,
    _write_grid_results_csv,
)


def test_parse_period_list_uses_fallback_when_empty() -> None:
    assert _parse_period_list(value=None, option_name="--fast-values", fallback=12) == [12]
    assert _parse_period_list(value=" ", option_name="--fast-values", fallback=12) == [12]


def test_parse_period_list_parses_and_dedupes() -> None:
    values = _parse_period_list(value="10, 20,10,30", option_name="--fast-values", fallback=12)
    assert values == [10, 20, 30]


def test_parse_period_list_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        _parse_period_list(value="10,a", option_name="--fast-values", fallback=12)


def test_build_period_pairs_filters_fast_lt_slow() -> None:
    pairs = _build_period_pairs(fast_values=[10, 20], slow_values=[15, 20, 30])
    assert pairs == [(10, 15), (10, 20), (10, 30), (20, 30)]


def test_rank_grid_rows_orders_by_return_then_drawdown() -> None:
    rows = [
        GridResultRow(
            fast=10,
            slow=30,
            trades=5,
            win_rate_pct=Decimal("40"),
            return_pct=Decimal("10"),
            max_drawdown_pct=Decimal("5"),
            end_equity_usdt=Decimal("1100"),
        ),
        GridResultRow(
            fast=12,
            slow=30,
            trades=3,
            win_rate_pct=Decimal("66.7"),
            return_pct=Decimal("10"),
            max_drawdown_pct=Decimal("4"),
            end_equity_usdt=Decimal("1100"),
        ),
        GridResultRow(
            fast=8,
            slow=25,
            trades=8,
            win_rate_pct=Decimal("50"),
            return_pct=Decimal("8"),
            max_drawdown_pct=Decimal("3"),
            end_equity_usdt=Decimal("1080"),
        ),
    ]
    ranked = _rank_grid_rows(rows=rows, top=2)
    assert [(r.fast, r.slow) for r in ranked] == [(12, 30), (10, 30)]


def test_write_grid_results_csv(tmp_path: Path) -> None:
    out = tmp_path / "grid" / "results.csv"
    rows = [
        GridResultRow(
            fast=10,
            slow=30,
            trades=5,
            win_rate_pct=Decimal("40"),
            return_pct=Decimal("10"),
            max_drawdown_pct=Decimal("5"),
            end_equity_usdt=Decimal("1100"),
        )
    ]
    _write_grid_results_csv(path=out, rows=rows)
    text = out.read_text(encoding="utf-8")
    assert "rank,fast,slow,trades,win_rate_pct,return_pct,max_drawdown_pct,end_equity_usdt" in text
    assert "1,10,30,5,40,10,5,1100" in text
