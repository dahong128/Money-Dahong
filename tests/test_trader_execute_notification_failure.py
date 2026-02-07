import asyncio
from decimal import Decimal
from typing import Optional

from money_dahong.engine.trader import Trader
from money_dahong.exchange.binance_spot import Kline
from money_dahong.settings import Settings
from money_dahong.strategies.base import Strategy, StrategyContext
from money_dahong.types import OrderRequest, Signal


class _NoopStrategy(Strategy):
    strategy_id = "noop"

    def generate_signal(
        self,
        *,
        klines: list[Kline],
        ctx: StrategyContext,
    ) -> Optional[Signal]:
        return None


class _RaisingNotifier:
    async def send(self, text: str) -> None:
        raise RuntimeError(f"telegram send failed: {text}")

    def enabled(self) -> bool:
        return True

    async def aclose(self) -> None:
        return


class _FakeClient:
    def __init__(self, *, order_response: dict[str, object]) -> None:
        self.order_response = order_response
        self.new_order_calls = 0

    async def new_order_market(
        self,
        *,
        symbol: str,
        side: str,
        quantity: Decimal | None = None,
        quote_order_qty: Decimal | None = None,
    ) -> dict[str, object]:
        self.new_order_calls += 1
        return self.order_response


def test_execute_dry_run_keeps_state_when_notification_fails() -> None:
    settings = Settings(TRADING_MODE="dry_run", CONFIRM_LIVE_TRADING="")
    trader = Trader(
        settings=settings,
        client=_FakeClient(order_response={}),
        strategy=_NoopStrategy(),
        notifier=_RaisingNotifier(),
    )
    order = OrderRequest(symbol="ETHUSDT", side="BUY", quote_order_qty=Decimal("25"))
    signal = Signal(side="BUY", reason="unit_test")

    asyncio.run(trader._execute(order=order, signal=signal, last_price=Decimal("10")))

    assert trader._state.in_position is True
    assert trader._state.position_qty == Decimal("2.5")
    assert trader._state.last_trade_time_s > 0


def test_execute_live_keeps_state_when_notification_fails() -> None:
    settings = Settings(TRADING_MODE="live", CONFIRM_LIVE_TRADING="YES")
    client = _FakeClient(
        order_response={
            "orderId": 12345,
            "executedQty": "1.2",
            "fills": [{"qty": "1.2", "price": "11"}],
        }
    )
    trader = Trader(
        settings=settings,
        client=client,
        strategy=_NoopStrategy(),
        notifier=_RaisingNotifier(),
    )
    order = OrderRequest(symbol="ETHUSDT", side="BUY", quote_order_qty=Decimal("25"))
    signal = Signal(side="BUY", reason="unit_test")

    asyncio.run(trader._execute(order=order, signal=signal, last_price=Decimal("10")))

    assert client.new_order_calls == 1
    assert trader._state.in_position is True
    assert trader._state.position_qty == Decimal("1.2")
    assert trader._state.entry_price == Decimal("11")
    assert trader._state.last_trade_time_s > 0
