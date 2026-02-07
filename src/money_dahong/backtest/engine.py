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
    exit_reason: str
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    pnl_usdt: Decimal
    max_runup_pct: Decimal


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
        position_sizing: str,
        cash_fraction: Decimal,
        order_notional_usdt: Decimal,
        fee_rate: Decimal,
        slippage_bps: Decimal,
        lookback_bars: int,
        trailing_stop_enabled: bool,
        trailing_start_profit_pct: Decimal,
        trailing_drawdown_pct: Decimal,
    ) -> None:
        self._symbol = symbol
        self._interval = interval
        self._strategy = strategy
        self._initial_cash = initial_cash_usdt
        self._position_sizing = position_sizing
        self._cash_fraction = cash_fraction
        self._order_notional = order_notional_usdt
        self._fee_rate = fee_rate
        self._slippage_bps = slippage_bps
        self._lookback_bars = lookback_bars
        self._trailing_stop_enabled = trailing_stop_enabled
        self._trailing_start_profit_pct = trailing_start_profit_pct
        self._trailing_drawdown_pct = trailing_drawdown_pct
        if self._slippage_bps < 0:
            raise ValueError("slippage_bps must be >= 0")
        if self._slippage_bps >= Decimal("10000"):
            raise ValueError("slippage_bps must be < 10000")

        self._cash = initial_cash_usdt
        self._qty = Decimal("0")
        self._in_position = False

        self.trades: list[Trade] = []
        self._entry_time_ms = 0
        self._entry_price = Decimal("0")
        self._entry_qty = Decimal("0")
        self._entry_total_usdt = Decimal("0")
        self._peak_price = Decimal("0")

    def run(self, *, klines: list[Kline]) -> BacktestResult:
        # Reset state for a fresh run.
        self._cash = self._initial_cash
        self._qty = Decimal("0")
        self._in_position = False
        self._entry_time_ms = 0
        self._entry_price = Decimal("0")
        self._entry_qty = Decimal("0")
        self._entry_total_usdt = Decimal("0")
        self._peak_price = Decimal("0")

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

        self.trades = []

        start_equity = self._initial_cash
        peak_equity = start_equity
        max_drawdown_pct = Decimal("0")

        window: list[Kline] = []
        for k in closed:
            window.append(k)
            if len(window) > self._lookback_bars:
                window = window[-self._lookback_bars :]

            exited_this_bar = False
            if self._in_position and self._trailing_stop_enabled:
                if self._peak_price <= 0:
                    self._peak_price = self._entry_price
                if k.close > self._peak_price:
                    self._peak_price = k.close
                if self._should_trailing_stop_exit(price=k.close):
                    self._apply_exit(price=k.close, time_ms=k.close_time_ms, reason="trailing_stop")
                    exited_this_bar = True

            ctx = StrategyContext(
                symbol=self._symbol,
                in_position=self._in_position,
                position_qty=self._qty,
            )
            if not exited_this_bar:
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

    def _should_trailing_stop_exit(self, *, price: Decimal) -> bool:
        if self._entry_price <= 0 or self._peak_price <= 0:
            return False
        peak_profit_pct = _pct(self._peak_price - self._entry_price, self._entry_price)
        if peak_profit_pct < self._trailing_start_profit_pct:
            return False
        drawdown_pct = _pct(self._peak_price - price, self._peak_price)
        return drawdown_pct >= self._trailing_drawdown_pct

    def _apply_signal(self, *, signal: Signal, price: Decimal, time_ms: int) -> None:
        if signal.side == "BUY":
            if self._in_position:
                return
            if price <= 0:
                return

            cost, fee, total = self._calc_entry_cost()
            if total <= 0 or self._cash < total:
                return

            entry_price = self._fill_price(price=price, side="BUY")
            if entry_price <= 0:
                return

            qty = cost / entry_price
            self._cash -= total
            self._qty += qty
            self._in_position = True

            self._entry_time_ms = time_ms
            self._entry_price = entry_price
            self._entry_qty = qty
            self._entry_total_usdt = total
            self._peak_price = entry_price
            return

        if signal.side == "SELL":
            self._apply_exit(price=price, time_ms=time_ms, reason="cross_down")

    def _calc_entry_cost(self) -> tuple[Decimal, Decimal, Decimal]:
        """
        Returns (cost, fee, total) in USDT for entry.

        cost: how much USDT is exchanged into the asset
        fee:  cost * fee_rate
        total: cost + fee (cash decrease)
        """
        if self._position_sizing == "cash_fraction":
            allocation = self._cash * self._cash_fraction
            if allocation <= 0:
                return Decimal("0"), Decimal("0"), Decimal("0")
            if self._fee_rate < 0:
                return Decimal("0"), Decimal("0"), Decimal("0")
            # Make total == allocation (i.e., fraction includes fees).
            cost = (
                allocation / (Decimal("1") + self._fee_rate) if self._fee_rate != 0 else allocation
            )
            fee = cost * self._fee_rate
            total = cost + fee
            return cost, fee, total

        # fixed_notional
        cost = self._order_notional
        fee = cost * self._fee_rate
        total = cost + fee
        return cost, fee, total

    def _apply_exit(self, *, price: Decimal, time_ms: int, reason: str) -> None:
        if not self._in_position or self._qty <= 0 or price <= 0:
            return

        exit_price = self._fill_price(price=price, side="SELL")
        if exit_price <= 0:
            return

        proceeds = self._qty * exit_price
        fee = proceeds * self._fee_rate
        exit_total = proceeds - fee
        self._cash += exit_total

        max_runup_pct = (
            _pct(self._peak_price - self._entry_price, self._entry_price)
            if self._entry_price > 0 and self._peak_price > 0
            else Decimal("0")
        )
        pnl = exit_total - self._entry_total_usdt
        self.trades.append(
            Trade(
                entry_time_ms=self._entry_time_ms,
                exit_time_ms=time_ms,
                side="LONG",
                exit_reason=reason,
                entry_price=self._entry_price,
                exit_price=exit_price,
                quantity=self._entry_qty,
                pnl_usdt=pnl,
                max_runup_pct=max_runup_pct,
            )
        )

        self._qty = Decimal("0")
        self._in_position = False
        self._entry_time_ms = 0
        self._entry_price = Decimal("0")
        self._entry_qty = Decimal("0")
        self._entry_total_usdt = Decimal("0")
        self._peak_price = Decimal("0")

    def _fill_price(self, *, price: Decimal, side: str) -> Decimal:
        if price <= 0 or self._slippage_bps <= 0:
            return price
        ratio = self._slippage_bps / Decimal("10000")
        if side == "BUY":
            return price * (Decimal("1") + ratio)
        return price * (Decimal("1") - ratio)
