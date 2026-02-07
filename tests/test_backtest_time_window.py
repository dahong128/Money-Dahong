import asyncio
from decimal import Decimal

import pytest

from money_dahong.cli import _load_backtest_klines, _parse_utc_to_ms
from money_dahong.exchange.binance_spot import Kline


def _k(open_time_ms: int) -> Kline:
    v = Decimal("1")
    return Kline(
        open_time_ms=open_time_ms,
        open=v,
        high=v,
        low=v,
        close=v,
        volume=Decimal("0"),
        close_time_ms=open_time_ms + 60_000,
    )


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, int | None]] = []

    async def klines(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list[Kline]:
        self.calls.append(
            {
                "limit": limit,
                "start_time_ms": start_time_ms,
                "end_time_ms": end_time_ms,
            }
        )
        if start_time_ms is None:
            return [_k(900), _k(1000)][:limit]
        if start_time_ms <= 100:
            return [_k(v) for v in range(100, 1100)][:limit]
        if start_time_ms <= 1100:
            return [_k(1100), _k(1101)][:limit]
        return []


def test_parse_utc_to_ms_accepts_z_and_naive() -> None:
    expected = 1_704_067_200_000  # 2024-01-01T00:00:00Z
    assert _parse_utc_to_ms("2024-01-01T00:00:00Z") == expected
    assert _parse_utc_to_ms("2024-01-01T00:00:00") == expected


def test_parse_utc_to_ms_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        _parse_utc_to_ms("2024/01/01 00:00:00")


def test_load_backtest_klines_single_call_when_start_not_set() -> None:
    client = _FakeClient()
    klines = asyncio.run(
        _load_backtest_klines(
            client=client,  # type: ignore[arg-type]
            symbol="ETHUSDT",
            interval="1m",
            limit=2,
            start_time_ms=None,
            end_time_ms=1_700_000_000_000,
        )
    )
    assert [k.open_time_ms for k in klines] == [900, 1000]
    assert len(client.calls) == 1
    assert client.calls[0]["end_time_ms"] == 1_700_000_000_000


def test_load_backtest_klines_paginates_when_start_set() -> None:
    client = _FakeClient()
    klines = asyncio.run(
        _load_backtest_klines(
            client=client,  # type: ignore[arg-type]
            symbol="ETHUSDT",
            interval="1m",
            limit=1002,
            start_time_ms=100,
            end_time_ms=None,
        )
    )
    assert len(klines) == 1002
    assert klines[0].open_time_ms == 100
    assert klines[-1].open_time_ms == 1101
    assert len(client.calls) == 2
    assert client.calls[0]["limit"] == 1000
    assert client.calls[0]["start_time_ms"] == 100
    assert client.calls[1]["limit"] == 2
    assert client.calls[1]["start_time_ms"] == 1100
