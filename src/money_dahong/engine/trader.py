from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Literal, Optional

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
    entry_price: Decimal = Decimal("0")
    peak_price: Decimal = Decimal("0")


@dataclass(frozen=True)
class SymbolTradingRules:
    base_asset: str
    quote_asset: str
    step_size: Decimal
    min_notional: Decimal


def _floor_to_step(quantity: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return quantity
    steps = (quantity / step).to_integral_value(rounding=ROUND_DOWN)
    return steps * step


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return (numerator / denominator) * Decimal("100")


def _should_trailing_stop_exit(
    *,
    entry_price: Decimal,
    peak_price: Decimal,
    price: Decimal,
    start_profit_pct: Decimal,
    drawdown_pct: Decimal,
) -> bool:
    if entry_price <= 0 or peak_price <= 0 or price <= 0:
        return False
    peak_profit_pct = _pct(peak_price - entry_price, entry_price)
    if peak_profit_pct < start_profit_pct:
        return False
    dd_pct = _pct(peak_price - price, peak_price)
    return dd_pct >= drawdown_pct


def _extract_free_balance(*, account: dict[str, object], asset: str) -> Decimal:
    balances = account.get("balances", [])
    if not isinstance(balances, list):
        return Decimal("0")
    for b in balances:
        if not isinstance(b, dict):
            continue
        if str(b.get("asset", "")).upper() != asset.upper():
            continue
        return Decimal(str(b.get("free", "0")))
    return Decimal("0")


class Trader:
    def __init__(
        self,
        *,
        settings: Settings,
        client: BinanceSpotClient,
        strategy: Strategy,
        notifier: TelegramNotifier,
        position_sizing: Literal["cash_fraction", "fixed_notional"] = "fixed_notional",
        cash_fraction: Decimal = Decimal("0.8"),
        order_notional_usdt: Decimal = Decimal("25"),
        max_order_notional_usdt: Decimal = Decimal("25"),
        trailing_stop_enabled: bool = False,
        trailing_start_profit_pct: Decimal = Decimal("30"),
        trailing_drawdown_pct: Decimal = Decimal("10"),
    ) -> None:
        self._settings = settings
        self._client = client
        self._strategy = strategy
        self._notifier = notifier
        self._position_sizing = position_sizing
        self._cash_fraction = cash_fraction
        self._order_notional_usdt = order_notional_usdt
        self._max_order_notional_usdt = max_order_notional_usdt
        self._trailing_stop_enabled = trailing_stop_enabled
        self._trailing_start_profit_pct = trailing_start_profit_pct
        self._trailing_drawdown_pct = trailing_drawdown_pct
        self._state = TraderState()
        self._rules: SymbolTradingRules | None = None
        self._symbol = ""
        self._interval = ""

    async def run(self, *, symbol: str | None = None, interval: str | None = None) -> None:
        symbol = symbol if symbol is not None else self._settings.symbol
        interval = interval if interval is not None else self._settings.interval
        self._symbol = symbol
        self._interval = interval

        exchange_info = await self._client.exchange_info(symbol=symbol)
        self._rules = self._extract_symbol_rules(exchange_info)

        logger.info(
            "trader_started",
            extra={"symbol": symbol, "strategy_id": self._strategy.strategy_id},
        )
        await self._notifier.send(
            f"Started: {symbol} {self._strategy.strategy_id} mode={self._settings.trading_mode}"
        )

        if self._settings.live_trading_enabled() and self._rules is not None:
            try:
                await self._sync_position_from_account(
                    symbol=symbol,
                    base_asset=self._rules.base_asset,
                )
            except Exception:
                logger.exception("sync_position_failed", extra={"symbol": symbol})

        try:
            while True:
                await self._tick(symbol=symbol, interval=interval)
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            raise
        except KeyboardInterrupt:
            logger.info("trader_stopped", extra={"symbol": symbol})
        finally:
            await self._notifier.send(f"Stopped: {symbol} {self._strategy.strategy_id}")

    async def _tick(self, *, symbol: str, interval: str) -> None:
        if self._rules is None:
            return
        klines = await self._client.klines(symbol=symbol, interval=interval, limit=200)
        closed_klines = self._closed_only(klines)
        if len(closed_klines) < 3:
            return

        last_closed = closed_klines[-1]
        if last_closed.close_time_ms == self._state.last_processed_close_time_ms:
            return
        self._state.last_processed_close_time_ms = last_closed.close_time_ms

        last_price = last_closed.close

        # Exit protection: trailing stop has higher priority than the strategy signal.
        if self._state.in_position and self._trailing_stop_enabled:
            if self._state.peak_price <= 0:
                self._state.peak_price = (
                    self._state.entry_price if self._state.entry_price > 0 else last_price
                )
            if last_price > self._state.peak_price:
                self._state.peak_price = last_price

            if _should_trailing_stop_exit(
                entry_price=self._state.entry_price,
                peak_price=self._state.peak_price,
                price=last_price,
                start_profit_pct=self._trailing_start_profit_pct,
                drawdown_pct=self._trailing_drawdown_pct,
            ):
                trailing_signal = Signal(side="SELL", reason="trailing_stop")
                order = await self._build_order(
                    signal=trailing_signal,
                    last_price=last_price,
                    rules=self._rules,
                )
                if order:
                    await self._execute(order=order, signal=trailing_signal, last_price=last_price)
                return

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

        if signal.side == "BUY" and (
            time.time() - self._state.last_trade_time_s < self._settings.cooldown_seconds
        ):
            logger.warning(
                "signal_blocked_cooldown",
                extra={"symbol": symbol, "strategy_id": self._strategy.strategy_id},
            )
            return

        order = await self._build_order(signal=signal, last_price=last_price, rules=self._rules)
        if not order:
            logger.warning(
                "signal_blocked_no_order",
                extra={"symbol": symbol, "strategy_id": self._strategy.strategy_id},
            )
            return

        await self._execute(order=order, signal=signal, last_price=last_price)

    def _closed_only(self, klines: list[Kline]) -> list[Kline]:
        # Binance REST `/klines` includes the currently-forming candle as the last item.
        # Use all-but-last as "closed" to avoid acting on partial data.
        if len(klines) <= 1:
            return []
        return klines[:-1]

    async def _build_order(
        self,
        *,
        signal: Signal,
        last_price: Decimal,
        rules: SymbolTradingRules,
    ) -> Optional[OrderRequest]:
        if signal.side == "BUY":
            quote_notional = await self._buy_quote_notional_usdt(rules=rules)
            if quote_notional <= 0 or quote_notional < rules.min_notional:
                return None
            return OrderRequest(symbol=self._symbol, side="BUY", quote_order_qty=quote_notional)

        if signal.side == "SELL":
            qty = await self._sell_quantity(rules=rules)
            if qty <= 0:
                return None
            return OrderRequest(symbol=self._symbol, side="SELL", quantity=qty)

        return None

    async def _buy_quote_notional_usdt(self, *, rules: SymbolTradingRules) -> Decimal:
        desired = Decimal("0")
        if self._position_sizing == "cash_fraction":
            if self._settings.live_trading_enabled():
                account = await self._client.account()
                free_quote = _extract_free_balance(account=account, asset=rules.quote_asset)
                desired = free_quote * self._cash_fraction
            else:
                desired = self._max_order_notional_usdt
        else:
            desired = self._order_notional_usdt

        if desired <= 0:
            return Decimal("0")
        return min(desired, self._max_order_notional_usdt)

    async def _sell_quantity(self, *, rules: SymbolTradingRules) -> Decimal:
        qty = self._state.position_qty
        if self._settings.live_trading_enabled():
            account = await self._client.account()
            qty = _extract_free_balance(account=account, asset=rules.base_asset)
        qty = _floor_to_step(qty, rules.step_size)
        return qty if qty > 0 else Decimal("0")

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
            quote_asset = self._rules.quote_asset if self._rules else "USDT"
            qty_hint = (
                f"qty={order.quantity}"
                if order.quantity is not None
                else f"quote≈{order.quote_order_qty} {quote_asset}"
            )
            await self._notifier.send(
                f"[DRY_RUN] {symbol} {signal.side} {qty_hint} "
                f"price≈{last_price} reason={signal.reason}"
            )
            self._apply_fill_locally(order=order, last_price=last_price)
            self._state.last_trade_time_s = time.time()
            return

        resp = await self._client.new_order_market(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            quote_order_qty=order.quote_order_qty,
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
        quote_asset = self._rules.quote_asset if self._rules else "USDT"
        qty_hint = (
            f"qty={order.quantity}"
            if order.quantity is not None
            else f"quote={order.quote_order_qty} {quote_asset}"
        )
        await self._notifier.send(
            f"[LIVE] {symbol} {order.side} {qty_hint} order_id={order_id} reason={signal.reason}"
        )
        self._apply_fill_locally(order=order, last_price=last_price, resp=resp)
        self._state.last_trade_time_s = time.time()

    def _apply_fill_locally(
        self,
        *,
        order: OrderRequest,
        last_price: Decimal,
        resp: dict[str, object] | None = None,
    ) -> None:
        executed_qty = Decimal("0")
        avg_price = Decimal("0")

        if resp is not None:
            executed_qty = Decimal(str(resp.get("executedQty", "0")))
            fills = resp.get("fills", [])
            if isinstance(fills, list) and fills:
                total_qty = Decimal("0")
                total_quote = Decimal("0")
                for f in fills:
                    if not isinstance(f, dict):
                        continue
                    q = Decimal(str(f.get("qty", "0")))
                    p = Decimal(str(f.get("price", "0")))
                    total_qty += q
                    total_quote += q * p
                if total_qty > 0:
                    avg_price = total_quote / total_qty

        if order.side == "BUY":
            self._state.in_position = True
            if executed_qty <= 0 and order.quantity is not None:
                executed_qty = order.quantity
            if (
                executed_qty <= 0
                and order.quantity is None
                and order.quote_order_qty is not None
                and last_price > 0
            ):
                executed_qty = order.quote_order_qty / last_price
            if executed_qty > 0:
                self._state.position_qty = self._state.position_qty + executed_qty
            if self._state.entry_price <= 0:
                self._state.entry_price = avg_price if avg_price > 0 else last_price
            if self._state.peak_price <= 0:
                self._state.peak_price = self._state.entry_price
        else:
            self._state.in_position = False
            self._state.position_qty = Decimal("0")
            self._state.entry_price = Decimal("0")
            self._state.peak_price = Decimal("0")

    async def _sync_position_from_account(self, *, symbol: str, base_asset: str) -> None:
        account = await self._client.account()
        qty = _extract_free_balance(account=account, asset=base_asset)
        if qty > 0:
            self._state.in_position = True
            self._state.position_qty = qty
            logger.info("position_synced", extra={"symbol": symbol, "qty": str(qty)})
        else:
            self._state.in_position = False
            self._state.position_qty = Decimal("0")
            logger.info("position_synced", extra={"symbol": symbol, "qty": "0"})

    def _extract_symbol_rules(self, exchange_info: dict[str, object]) -> SymbolTradingRules:
        symbols = exchange_info.get("symbols", [])
        if not isinstance(symbols, list) or not symbols:
            return SymbolTradingRules(
                base_asset="",
                quote_asset="",
                step_size=Decimal("0.0001"),
                min_notional=Decimal("0"),
            )
        first = symbols[0]
        if not isinstance(first, dict):
            return SymbolTradingRules(
                base_asset="",
                quote_asset="",
                step_size=Decimal("0.0001"),
                min_notional=Decimal("0"),
            )

        base_asset = str(first.get("baseAsset", ""))
        quote_asset = str(first.get("quoteAsset", ""))
        filters = first.get("filters", [])
        if not isinstance(filters, list):
            return SymbolTradingRules(
                base_asset=base_asset,
                quote_asset=quote_asset,
                step_size=Decimal("0.0001"),
                min_notional=Decimal("0"),
            )

        step_size = Decimal("0.0001")
        min_notional = Decimal("0")
        for f in filters:
            if isinstance(f, dict) and f.get("filterType") == "LOT_SIZE":
                step_size = Decimal(str(f.get("stepSize", "0.0001")))
            if isinstance(f, dict) and f.get("filterType") in ("MIN_NOTIONAL", "NOTIONAL"):
                min_notional = Decimal(str(f.get("minNotional", "0")))

        return SymbolTradingRules(
            base_asset=base_asset,
            quote_asset=quote_asset,
            step_size=step_size,
            min_notional=min_notional,
        )
