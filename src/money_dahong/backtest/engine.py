from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from money_dahong.exchange.binance_spot import Kline
from money_dahong.strategies.base import Strategy, StrategyContext
from money_dahong.types import Signal


@dataclass(frozen=True)
class Trade:
    entry_time_ms: int
    exit_time_ms: int
    side: str
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    pnl_usdt: Decimal


@dataclass(frozen=True)
class BacktestResult:
    symbol: str
    interval: str
    bars: int
    trades: int
    start_equity_usdt: Decimal
    end_equity_usdt: Decimal
    return_pct: Decimal
    max_drawdown_pct: Decimal


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return (numerator / denominator) * Decimal("100")


class Backtester:
    def __init__(
        self,
        *,
        symbol: str,
        interval: str,
        strategy: Strategy,
        initial_cash_usdt: Decimal,
        order_notional_usdt: Decimal,
        fee_rate: Decimal,
        lookback_bars: int,
    ) -> None:
        self._symbol = symbol
        self._interval = interval
        self._strategy = strategy
        self._initial_cash = initial_cash_usdt
        self._order_notional = order_notional_usdt
        self._fee_rate = fee_rate
        self._lookback_bars = lookback_bars

        self._cash = initial_cash_usdt
        self._qty = Decimal("0")
        self._in_position = False

        self.trades: list[Trade] = []
        self._entry_time_ms = 0
        self._entry_price = Decimal("0")
        self._entry_qty = Decimal("0")

    def run(self, *, klines: list[Kline]) -> BacktestResult:
        closed = klines[:-1] if len(klines) > 1 else []
        if not closed:
            return BacktestResult(
                symbol=self._symbol,
                interval=self._interval,
                bars=0,
                trades=0,
                start_equity_usdt=self._initial_cash,
                end_equity_usdt=self._initial_cash,
                return_pct=Decimal("0"),
                max_drawdown_pct=Decimal("0"),
            )

        start_equity = self._initial_cash
        peak_equity = start_equity
        max_drawdown_pct = Decimal("0")

        window: list[Kline] = []
        for k in closed:
            window.append(k)
            if len(window) > self._lookback_bars:
                window = window[-self._lookback_bars :]

            ctx = StrategyContext(
                symbol=self._symbol,
                in_position=self._in_position,
                position_qty=self._qty,
            )
            signal = self._strategy.generate_signal(klines=window, ctx=ctx)
            if signal:
                self._apply_signal(signal=signal, price=k.close, time_ms=k.close_time_ms)

            equity = self._cash + (self._qty * k.close)
            if equity > peak_equity:
                peak_equity = equity
            dd = _pct(peak_equity - equity, peak_equity)
            if dd > max_drawdown_pct:
                max_drawdown_pct = dd

        end_equity = self._cash + (self._qty * closed[-1].close)
        return BacktestResult(
            symbol=self._symbol,
            interval=self._interval,
            bars=len(closed),
            trades=len(self.trades),
            start_equity_usdt=start_equity,
            end_equity_usdt=end_equity,
            return_pct=_pct(end_equity - start_equity, start_equity),
            max_drawdown_pct=max_drawdown_pct,
        )

    def _apply_signal(self, *, signal: Signal, price: Decimal, time_ms: int) -> None:
        if signal.side == "BUY":
            if self._in_position:
                return
            if price <= 0:
                return

            cost = self._order_notional
            fee = cost * self._fee_rate
            total = cost + fee
            if self._cash < total:
                return

            qty = cost / price
            self._cash -= total
            self._qty += qty
            self._in_position = True

            self._entry_time_ms = time_ms
            self._entry_price = price
            self._entry_qty = qty
            return

        if signal.side == "SELL":
            if not self._in_position or self._qty <= 0:
                return

            proceeds = self._qty * price
            fee = proceeds * self._fee_rate
            self._cash += proceeds - fee

            entry_fee = self._order_notional * self._fee_rate
            pnl = (price - self._entry_price) * self._entry_qty - entry_fee - fee
            self.trades.append(
                Trade(
                    entry_time_ms=self._entry_time_ms,
                    exit_time_ms=time_ms,
                    side="LONG",
                    entry_price=self._entry_price,
                    exit_price=price,
                    quantity=self._entry_qty,
                    pnl_usdt=pnl,
                )
            )

            self._qty = Decimal("0")
            self._in_position = False
            self._entry_time_ms = 0
            self._entry_price = Decimal("0")
            self._entry_qty = Decimal("0")
