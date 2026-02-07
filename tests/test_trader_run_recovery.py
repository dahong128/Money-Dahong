import asyncio
from typing import Optional

import pytest

import money_dahong.engine.trader as trader_module
from money_dahong.engine.trader import Trader
from money_dahong.exchange.binance_spot import Kline
from money_dahong.settings import Settings
from money_dahong.strategies.base import Strategy, StrategyContext
from money_dahong.types import Signal


class _NoopStrategy(Strategy):
    strategy_id = "noop"

    def generate_signal(
        self,
        *,
        klines: list[Kline],
        ctx: StrategyContext,
    ) -> Optional[Signal]:
        return None


class _RunClient:
    async def exchange_info(self, *, symbol: str) -> dict[str, object]:
        return {
            "symbols": [
                {
                    "baseAsset": "ETH",
                    "quoteAsset": "USDT",
                    "filters": [],
                }
            ]
        }


class _Notifier:
    def __init__(self, *, fail_error_message: bool = False) -> None:
        self.messages: list[str] = []
        self._fail_error_message = fail_error_message

    async def send(self, text: str) -> None:
        self.messages.append(text)
        if self._fail_error_message and text.startswith("[ERROR]"):
            raise RuntimeError("telegram unavailable")

    def enabled(self) -> bool:
        return False

    async def aclose(self) -> None:
        return


def test_run_recovers_from_tick_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(TRADING_MODE="dry_run", CONFIRM_LIVE_TRADING="")
    notifier = _Notifier()
    trader = Trader(
        settings=settings,
        client=_RunClient(),
        strategy=_NoopStrategy(),
        notifier=notifier,
    )

    tick_calls = 0

    async def fake_tick(*, symbol: str, interval: str) -> float:
        nonlocal tick_calls
        tick_calls += 1
        if tick_calls == 1:
            raise RuntimeError("transient network error")
        return 0.01

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(trader, "_tick", fake_tick)
    monkeypatch.setattr(trader_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(trader.run(symbol="ETHUSDT", interval="1m"))

    assert tick_calls == 2
    assert sleep_calls[0] == trader_module._TICK_ERROR_BACKOFF_SECONDS
    assert any(msg.startswith("[ERROR]") for msg in notifier.messages)


def test_run_recovers_even_when_error_notification_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(TRADING_MODE="dry_run", CONFIRM_LIVE_TRADING="")
    notifier = _Notifier(fail_error_message=True)
    trader = Trader(
        settings=settings,
        client=_RunClient(),
        strategy=_NoopStrategy(),
        notifier=notifier,
    )

    tick_calls = 0

    async def fake_tick(*, symbol: str, interval: str) -> float:
        nonlocal tick_calls
        tick_calls += 1
        if tick_calls == 1:
            raise RuntimeError("transient network error")
        return 0.01

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(trader, "_tick", fake_tick)
    monkeypatch.setattr(trader_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(trader.run(symbol="ETHUSDT", interval="1m"))

    assert tick_calls == 2
    assert sleep_calls[0] == trader_module._TICK_ERROR_BACKOFF_SECONDS
    assert sleep_calls[1] == 0.01
