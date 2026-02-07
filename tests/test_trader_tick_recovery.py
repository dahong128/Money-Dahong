import asyncio
from typing import Optional

from money_dahong.engine.trader import (
    _ERROR_NOTIFY_COOLDOWN_SECONDS,
    _TICK_ERROR_BACKOFF_SECONDS,
    Trader,
)
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


class _NoopClient:
    pass


class _CollectingNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text: str) -> None:
        self.messages.append(text)

    def enabled(self) -> bool:
        return True

    async def aclose(self) -> None:
        return


def test_handle_tick_exception_respects_notify_cooldown(monkeypatch: object) -> None:
    settings = Settings(TRADING_MODE="dry_run", CONFIRM_LIVE_TRADING="")
    notifier = _CollectingNotifier()
    trader = Trader(
        settings=settings,
        client=_NoopClient(),  # type: ignore[arg-type]
        strategy=_NoopStrategy(),
        notifier=notifier,  # type: ignore[arg-type]
    )

    clock = {"now": 1000.0}
    monkeypatch.setattr("money_dahong.engine.trader.time.time", lambda: clock["now"])

    backoff_1 = asyncio.run(
        trader._handle_tick_exception(symbol="ETHUSDT", interval="1m", error=RuntimeError("boom1"))
    )
    clock["now"] += 1
    backoff_2 = asyncio.run(
        trader._handle_tick_exception(symbol="ETHUSDT", interval="1m", error=RuntimeError("boom2"))
    )
    clock["now"] += _ERROR_NOTIFY_COOLDOWN_SECONDS + 1
    backoff_3 = asyncio.run(
        trader._handle_tick_exception(symbol="ETHUSDT", interval="1m", error=RuntimeError("boom3"))
    )

    assert backoff_1 == _TICK_ERROR_BACKOFF_SECONDS
    assert backoff_2 == _TICK_ERROR_BACKOFF_SECONDS
    assert backoff_3 == _TICK_ERROR_BACKOFF_SECONDS
    assert len(notifier.messages) == 2
    assert "boom1" in notifier.messages[0]
    assert "boom3" in notifier.messages[1]
