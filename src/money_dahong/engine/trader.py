from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Optional

from money_dahong.exchange import BinanceSpotClient
from money_dahong.exchange.binance_spot import Kline
from money_dahong.notifications import TelegramNotifier
from money_dahong.settings import Settings
from money_dahong.strategies.base import Strategy, StrategyContext
from money_dahong.types import OrderRequest, Signal

logger = logging.getLogger("money_dahong.trader")


@dataclass
class TraderState:
    in_position: bool = False
    position_qty: Decimal = Decimal("0")
    last_processed_close_time_ms: int = 0
    last_trade_time_s: float = 0.0


def _floor_to_step(quantity: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return quantity
    steps = (quantity / step).to_integral_value(rounding=ROUND_DOWN)
    return steps * step


class Trader:
    def __init__(
        self,
        *,
        settings: Settings,
        client: BinanceSpotClient,
        strategy: Strategy,
        notifier: TelegramNotifier,
    ) -> None:
        self._settings = settings
        self._client = client
        self._strategy = strategy
        self._notifier = notifier
        self._state = TraderState()

    async def run(self) -> None:
        symbol = self._settings.symbol
        interval = self._settings.interval

        exchange_info = await self._client.exchange_info(symbol=symbol)
        step_size = self._extract_step_size(exchange_info)

        logger.info(
            "trader_started",
            extra={"symbol": symbol, "strategy_id": self._strategy.strategy_id},
        )
        await self._notifier.send(
            f"Started: {symbol} {self._strategy.strategy_id} mode={self._settings.trading_mode}"
        )

        try:
            while True:
                await self._tick(symbol=symbol, interval=interval, step_size=step_size)
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            raise
        except KeyboardInterrupt:
            logger.info("trader_stopped", extra={"symbol": symbol})
        finally:
            await self._notifier.send(f"Stopped: {symbol} {self._strategy.strategy_id}")

    async def _tick(self, *, symbol: str, interval: str, step_size: Decimal) -> None:
        klines = await self._client.klines(symbol=symbol, interval=interval, limit=200)
        closed_klines = self._closed_only(klines)
        if len(closed_klines) < 3:
            return

        last_closed = closed_klines[-1]
        if last_closed.close_time_ms == self._state.last_processed_close_time_ms:
            return
        self._state.last_processed_close_time_ms = last_closed.close_time_ms

        ctx = StrategyContext(
            symbol=symbol,
            in_position=self._state.in_position,
            position_qty=self._state.position_qty,
        )
        signal = self._strategy.generate_signal(klines=closed_klines, ctx=ctx)
        if not signal:
            logger.info(
                "no_signal",
                extra={"symbol": symbol, "strategy_id": self._strategy.strategy_id},
            )
            return

        if time.time() - self._state.last_trade_time_s < self._settings.cooldown_seconds:
            logger.warning(
                "signal_blocked_cooldown",
                extra={"symbol": symbol, "strategy_id": self._strategy.strategy_id},
            )
            return

        order = self._build_order(signal=signal, last_price=last_closed.close, step_size=step_size)
        if not order:
            logger.warning(
                "signal_blocked_no_order",
                extra={"symbol": symbol, "strategy_id": self._strategy.strategy_id},
            )
            return

        await self._execute(order=order, signal=signal, last_price=last_closed.close)

    def _closed_only(self, klines: list[Kline]) -> list[Kline]:
        # Binance REST `/klines` includes the currently-forming candle as the last item.
        # Use all-but-last as "closed" to avoid acting on partial data.
        if len(klines) <= 1:
            return []
        return klines[:-1]

    def _build_order(
        self,
        *,
        signal: Signal,
        last_price: Decimal,
        step_size: Decimal,
    ) -> Optional[OrderRequest]:
        if signal.side == "BUY":
            notional = Decimal(str(self._settings.max_order_notional_usdt))
            if last_price <= 0:
                return None
            qty = notional / last_price
            qty = _floor_to_step(qty, step_size)
            if qty <= 0:
                return None
            return OrderRequest(symbol=self._settings.symbol, side="BUY", quantity=qty)

        if signal.side == "SELL":
            if self._state.position_qty <= 0:
                return None
            qty = _floor_to_step(self._state.position_qty, step_size)
            if qty <= 0:
                return None
            return OrderRequest(symbol=self._settings.symbol, side="SELL", quantity=qty)

        return None

    async def _execute(self, *, order: OrderRequest, signal: Signal, last_price: Decimal) -> None:
        symbol = order.symbol
        logger.info(
            "signal",
            extra={
                "symbol": symbol,
                "strategy_id": self._strategy.strategy_id,
                "trace_id": signal.reason,
            },
        )

        if not self._settings.live_trading_enabled():
            await self._notifier.send(
                f"[DRY_RUN] {symbol} {signal.side} qty={order.quantity} "
                f"price≈{last_price} reason={signal.reason}"
            )
            self._apply_fill_locally(order=order)
            self._state.last_trade_time_s = time.time()
            return

        resp = await self._client.new_order_market(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
        )
        order_id = str(resp.get("orderId", ""))
        logger.info(
            "order_placed",
            extra={
                "symbol": symbol,
                "strategy_id": self._strategy.strategy_id,
                "order_id": order_id,
            },
        )
        await self._notifier.send(
            f"[LIVE] {symbol} {order.side} qty={order.quantity} "
            f"order_id={order_id} reason={signal.reason}"
        )
        self._apply_fill_locally(order=order)
        self._state.last_trade_time_s = time.time()

    def _apply_fill_locally(self, *, order: OrderRequest) -> None:
        if order.side == "BUY":
            self._state.in_position = True
            self._state.position_qty = self._state.position_qty + order.quantity
        else:
            self._state.in_position = False
            self._state.position_qty = Decimal("0")

    def _extract_step_size(self, exchange_info: dict[str, object]) -> Decimal:
        symbols = exchange_info.get("symbols", [])
        if not isinstance(symbols, list) or not symbols:
            return Decimal("0.0001")
        first = symbols[0]
        if not isinstance(first, dict):
            return Decimal("0.0001")
        filters = first.get("filters", [])
        if not isinstance(filters, list):
            return Decimal("0.0001")
        for f in filters:
            if isinstance(f, dict) and f.get("filterType") == "LOT_SIZE":
                return Decimal(str(f.get("stepSize", "0.0001")))
        return Decimal("0.0001")
