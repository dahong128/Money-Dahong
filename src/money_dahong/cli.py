from __future__ import annotations

import asyncio
import csv
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import typer

from money_dahong.backtest.engine import Backtester, Trade
from money_dahong.config.ema_cross import load_ema_cross_run_config
from money_dahong.config.ma_cross import load_ma_cross_backtest_config
from money_dahong.engine.trader import Trader
from money_dahong.exchange import BinanceSpotClient
from money_dahong.exchange.binance_spot import Kline
from money_dahong.logging_utils import configure_logging
from money_dahong.notifications.telegram import TelegramNotifier
from money_dahong.settings import Settings
from money_dahong.strategies.ema_cross import EmaCrossParams, EmaCrossStrategy
from money_dahong.strategies.ma_cross import MaCrossParams, MaCrossStrategy

app = typer.Typer(no_args_is_help=True, add_completion=False)
logger = logging.getLogger("money_dahong")

def _q(value: Decimal, pattern: str) -> Decimal:
    return value.quantize(Decimal(pattern), rounding=ROUND_HALF_UP)


def _fmt_pct(value: Decimal) -> str:
    return f"{_q(value, '0.01')}"


def _fmt_usdt(value: Decimal) -> str:
    return f"{_q(value, '0.01')}"


def _ms_to_utc(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")


@dataclass(frozen=True)
class GridResultRow:
    fast: int
    slow: int
    trades: int
    win_rate_pct: Decimal
    return_pct: Decimal
    max_drawdown_pct: Decimal
    end_equity_usdt: Decimal


def _write_trades_csv(*, path: Path, trades: list[Trade]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "entry_time_ms",
                "entry_time_utc",
                "exit_time_ms",
                "exit_time_utc",
                "side",
                "exit_reason",
                "entry_price",
                "exit_price",
                "quantity",
                "pnl_usdt",
                "max_runup_pct",
            ]
        )
        for t in trades:
            writer.writerow(
                [
                    t.entry_time_ms,
                    _ms_to_utc(t.entry_time_ms),
                    t.exit_time_ms,
                    _ms_to_utc(t.exit_time_ms),
                    t.side,
                    t.exit_reason,
                    str(t.entry_price),
                    str(t.exit_price),
                    str(t.quantity),
                    str(t.pnl_usdt),
                    str(t.max_runup_pct),
                ]
            )


def _write_grid_results_csv(*, path: Path, rows: list[GridResultRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "rank",
                "fast",
                "slow",
                "trades",
                "win_rate_pct",
                "return_pct",
                "max_drawdown_pct",
                "end_equity_usdt",
            ]
        )
        for i, row in enumerate(rows, start=1):
            writer.writerow(
                [
                    i,
                    row.fast,
                    row.slow,
                    row.trades,
                    str(row.win_rate_pct),
                    str(row.return_pct),
                    str(row.max_drawdown_pct),
                    str(row.end_equity_usdt),
                ]
            )


def _parse_period_list(*, value: str | None, option_name: str, fallback: int) -> list[int]:
    if value is None or not value.strip():
        return [fallback]
    items: list[int] = []
    for token in value.split(","):
        t = token.strip()
        if not t:
            continue
        if not t.isdigit():
            raise ValueError(f"{option_name} expects comma-separated positive integers")
        v = int(t)
        if v <= 0:
            raise ValueError(f"{option_name} expects values > 0")
        items.append(v)
    if not items:
        raise ValueError(f"{option_name} is empty")
    # Keep order, remove duplicates.
    deduped: list[int] = []
    seen: set[int] = set()
    for v in items:
        if v in seen:
            continue
        seen.add(v)
        deduped.append(v)
    return deduped


def _build_period_pairs(*, fast_values: list[int], slow_values: list[int]) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for fast in fast_values:
        for slow in slow_values:
            if fast < slow:
                pairs.append((fast, slow))
    return pairs


def _rank_grid_rows(*, rows: list[GridResultRow], top: int) -> list[GridResultRow]:
    sorted_rows = sorted(rows, key=lambda r: (-r.return_pct, r.max_drawdown_pct, -r.trades))
    return sorted_rows[: max(0, top)]


def _parse_utc_to_ms(value: str) -> int:
    s = value.strip()
    if not s:
        raise ValueError("datetime is empty")
    normalized = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as e:
        raise ValueError(
            "invalid datetime format; use ISO-8601 like 2024-01-01T00:00:00Z"
        ) from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


async def _load_backtest_klines(
    *,
    client: BinanceSpotClient,
    symbol: str,
    interval: str,
    limit: int,
    start_time_ms: int | None,
    end_time_ms: int | None,
) -> list[Kline]:
    if start_time_ms is None:
        return await client.klines(
            symbol=symbol,
            interval=interval,
            limit=limit,
            end_time_ms=end_time_ms,
        )

    collected: list[Kline] = []
    next_start_ms = start_time_ms
    while len(collected) < limit:
        batch_limit = min(1000, limit - len(collected))
        batch = await client.klines(
            symbol=symbol,
            interval=interval,
            limit=batch_limit,
            start_time_ms=next_start_ms,
            end_time_ms=end_time_ms,
        )
        if not batch:
            break
        collected.extend(batch)
        if len(batch) < batch_limit:
            break
        next_start_ms = batch[-1].open_time_ms + 1
        if end_time_ms is not None and next_start_ms > end_time_ms:
            break
    return collected


@app.command()
def config_init(
    path: Path = typer.Option(Path(".env"), help="Path to write a starter .env file."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite if exists."),
) -> None:
    """
    Create a starter `.env` file (copy from `.env.example`).
    """
    example_path = Path(".env.example")
    if not example_path.exists():
        raise typer.Exit(code=2)

    if path.exists() and not overwrite:
        raise typer.Exit(code=1)

    path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
    typer.echo(f"Wrote {path}")


@app.command()
def show_config() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    redacted = settings.model_dump()
    redacted["binance_api_secret"] = "***" if redacted["binance_api_secret"] else ""
    redacted["telegram_bot_token"] = "***" if redacted["telegram_bot_token"] else ""
    logger.info("loaded_config", extra={"symbol": settings.symbol})
    typer.echo(redacted)


@app.command()
def health() -> None:
    """
    Ping Binance and print server time.
    """
    settings = Settings()
    configure_logging(settings.log_level)

    async def _run() -> None:
        client = BinanceSpotClient(
            api_key=settings.binance_api_key,
            api_secret=settings.binance_api_secret,
        )
        try:
            await client.ping()
            server_time = await client.server_time_ms()
            typer.echo({"ok": True, "server_time_ms": server_time, "symbol": settings.symbol})
        finally:
            await client.aclose()

    asyncio.run(_run())


@app.command()
def alerts_test(
    message: str = typer.Option("money-dahong test alert", help="Message to send."),
) -> None:
    settings = Settings()
    configure_logging(settings.log_level)

    async def _run() -> None:
        notifier = TelegramNotifier(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
        try:
            await notifier.send(message)
            typer.echo({"ok": True, "channel": "telegram", "enabled": notifier.enabled()})
        finally:
            await notifier.aclose()

    asyncio.run(_run())


@app.command()
def run(
    config: Path = typer.Option(
        Path("configs/ema_cross.toml"),
        help="EMA cross live config file (TOML).",
    ),
) -> None:
    """
    Run the EMA cross bot using `configs/ema_cross.toml`.
    """
    settings = Settings()
    configure_logging(settings.log_level)

    if not config.exists():
        raise typer.BadParameter(f"config file not found: {config}")

    try:
        cfg = load_ema_cross_run_config(config)
    except Exception as e:
        raise typer.BadParameter(f"invalid config: {e}") from e

    symbol = (cfg.market.symbol or settings.symbol).strip()
    interval = (cfg.market.interval or settings.interval).strip()

    async def _run() -> None:
        client = BinanceSpotClient(
            api_key=settings.binance_api_key,
            api_secret=settings.binance_api_secret,
        )
        notifier = TelegramNotifier(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
        strategy = EmaCrossStrategy(
            EmaCrossParams(
                fast_period=cfg.strategy.fast_period,
                slow_period=cfg.strategy.slow_period,
            )
        )
        max_notional = Decimal(str(settings.max_order_notional_usdt))
        trader = Trader(
            settings=settings,
            client=client,
            strategy=strategy,
            notifier=notifier,
            position_sizing="fixed_notional",
            order_notional_usdt=max_notional,
            max_order_notional_usdt=max_notional,
            trailing_stop_enabled=False,
        )
        try:
            await trader.run(symbol=symbol, interval=interval)
        finally:
            await notifier.aclose()
            await client.aclose()

    asyncio.run(_run())


@app.command()
def run_ma(
    config: Path = typer.Option(
        Path("configs/ma_cross.toml"),
        help="MA cross live config file (TOML).",
    ),
) -> None:
    """
    Run the MA cross bot (double moving average) using `configs/ma_cross.toml`.
    """
    settings = Settings()
    configure_logging(settings.log_level)

    if not config.exists():
        raise typer.BadParameter(f"config file not found: {config}")

    try:
        cfg = load_ma_cross_backtest_config(config)
    except Exception as e:
        raise typer.BadParameter(f"invalid config: {e}") from e

    symbol = (cfg.market.symbol or settings.symbol).strip()
    interval = (cfg.market.interval or settings.interval).strip()

    async def _run() -> None:
        client = BinanceSpotClient(
            api_key=settings.binance_api_key,
            api_secret=settings.binance_api_secret,
        )
        notifier = TelegramNotifier(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
        strategy = MaCrossStrategy(
            MaCrossParams(
                fast_period=cfg.strategy.fast_period,
                slow_period=cfg.strategy.slow_period,
                ma_type=cfg.strategy.ma_type,
            )
        )

        max_notional = Decimal(str(settings.max_order_notional_usdt))
        trader = Trader(
            settings=settings,
            client=client,
            strategy=strategy,
            notifier=notifier,
            position_sizing=cfg.backtest.position_sizing,
            cash_fraction=Decimal(str(cfg.backtest.cash_fraction)),
            order_notional_usdt=Decimal(str(cfg.backtest.order_notional_usdt)),
            max_order_notional_usdt=max_notional,
            trailing_stop_enabled=cfg.risk.trailing_stop_enabled,
            trailing_start_profit_pct=Decimal(str(cfg.risk.trailing_start_profit_pct)),
            trailing_drawdown_pct=Decimal(str(cfg.risk.trailing_drawdown_pct)),
        )
        try:
            await trader.run(symbol=symbol, interval=interval)
        finally:
            await notifier.aclose()
            await client.aclose()

    asyncio.run(_run())


@app.command()
def backtest(
    config: Path = typer.Option(
        Path("configs/ma_cross.toml"),
        help="MA cross backtest config file (TOML).",
    ),
    fast: int | None = typer.Option(None, help="Override: fast MA period."),
    slow: int | None = typer.Option(None, help="Override: slow MA period."),
    ma_type: str | None = typer.Option(None, help="Override: sma|ema"),
    limit: int | None = typer.Option(
        None,
        help="Override: max bars to use in backtest (1-20000).",
    ),
    start: str | None = typer.Option(
        None,
        help="Override: UTC start time (ISO-8601), e.g. 2024-01-01T00:00:00Z.",
    ),
    end: str | None = typer.Option(
        None,
        help="Override: UTC end time (ISO-8601), e.g. 2024-12-31T23:59:59Z.",
    ),
    initial_cash_usdt: float | None = typer.Option(None, help="Override: initial cash in USDT."),
    order_notional_usdt: float | None = typer.Option(
        None,
        help="Override: order notional per BUY in USDT.",
    ),
    fee_rate: float | None = typer.Option(None, help="Override: fee rate (e.g. 0.001 = 0.1%)."),
    slippage_bps: float | None = typer.Option(
        None,
        help="Override: slippage in bps (1 bps = 0.01%).",
    ),
    trades_csv: Path | None = typer.Option(
        None,
        help="Override: write backtest trades to CSV path.",
    ),
    notify_telegram: bool | None = typer.Option(
        None,
        "--notify-telegram/--no-notify-telegram",
        help="Override: push summary to Telegram.",
    ),
) -> None:
    """
    Backtest the MA cross strategy on latest Binance klines (REST).
    """
    settings = Settings()
    configure_logging(settings.log_level)

    if not config.exists():
        raise typer.BadParameter(f"config file not found: {config}")

    try:
        cfg = load_ma_cross_backtest_config(config)
    except Exception as e:
        raise typer.BadParameter(f"invalid config: {e}") from e

    symbol = (cfg.market.symbol or settings.symbol).strip()
    interval = (cfg.market.interval or settings.interval).strip()

    effective_limit = limit if limit is not None else cfg.market.limit
    if effective_limit <= 0 or effective_limit > 20000:
        raise typer.BadParameter("limit must be between 1 and 20000")

    config_start_utc = cfg.market.start_utc.strip() if cfg.market.start_utc else ""
    config_end_utc = cfg.market.end_utc.strip() if cfg.market.end_utc else ""
    effective_start_utc = start if start is not None else (config_start_utc or None)
    effective_end_utc = end if end is not None else (config_end_utc or None)
    try:
        start_time_ms = (
            _parse_utc_to_ms(effective_start_utc) if effective_start_utc is not None else None
        )
    except ValueError as e:
        raise typer.BadParameter(str(e), param_hint="--start") from e
    try:
        end_time_ms = (
            _parse_utc_to_ms(effective_end_utc) if effective_end_utc is not None else None
        )
    except ValueError as e:
        raise typer.BadParameter(str(e), param_hint="--end") from e
    if start_time_ms is not None and end_time_ms is not None and start_time_ms >= end_time_ms:
        raise typer.BadParameter("start must be earlier than end")

    effective_ma_type = (ma_type if ma_type is not None else cfg.strategy.ma_type).strip().lower()
    if effective_ma_type not in ("sma", "ema"):
        raise typer.BadParameter("ma_type must be 'sma' or 'ema'")

    effective_fast = fast if fast is not None else cfg.strategy.fast_period
    effective_slow = slow if slow is not None else cfg.strategy.slow_period
    if effective_fast >= effective_slow:
        raise typer.BadParameter("fast must be < slow")

    effective_initial_cash = (
        initial_cash_usdt if initial_cash_usdt is not None else cfg.backtest.initial_cash_usdt
    )
    effective_fee_rate = fee_rate if fee_rate is not None else cfg.backtest.fee_rate
    effective_slippage_bps = (
        slippage_bps if slippage_bps is not None else cfg.backtest.slippage_bps
    )
    if effective_slippage_bps < 0 or effective_slippage_bps >= 10000:
        raise typer.BadParameter("slippage_bps must be within [0, 10000)")

    config_trades_csv = cfg.backtest.trades_csv.strip() if cfg.backtest.trades_csv else ""
    effective_trades_csv = (
        trades_csv
        if trades_csv is not None
        else (Path(config_trades_csv) if config_trades_csv else None)
    )

    effective_notify = (
        notify_telegram if notify_telegram is not None else cfg.telegram.notify
    )

    position_sizing = cfg.backtest.position_sizing
    cash_fraction = Decimal(str(cfg.backtest.cash_fraction))
    order_notional_value = (
        order_notional_usdt if order_notional_usdt is not None else cfg.backtest.order_notional_usdt
    )
    order_notional_dec = Decimal(str(order_notional_value))

    strategy = MaCrossStrategy(
        MaCrossParams(
            fast_period=effective_fast,
            slow_period=effective_slow,
            ma_type=effective_ma_type,  # type: ignore[arg-type]
        )
    )

    async def _run() -> None:
        client = BinanceSpotClient(
            api_key=settings.binance_api_key,
            api_secret=settings.binance_api_secret,
        )
        notifier = TelegramNotifier(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
        try:
            klines = await _load_backtest_klines(
                client=client,
                symbol=symbol,
                interval=interval,
                limit=effective_limit,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
            )

            backtester = Backtester(
                symbol=symbol,
                interval=interval,
                strategy=strategy,
                initial_cash_usdt=Decimal(str(effective_initial_cash)),
                position_sizing=position_sizing,
                cash_fraction=cash_fraction,
                order_notional_usdt=order_notional_dec,
                fee_rate=Decimal(str(effective_fee_rate)),
                slippage_bps=Decimal(str(effective_slippage_bps)),
                lookback_bars=strategy.lookback_bars,
                trailing_stop_enabled=cfg.risk.trailing_stop_enabled,
                trailing_start_profit_pct=Decimal(str(cfg.risk.trailing_start_profit_pct)),
                trailing_drawdown_pct=Decimal(str(cfg.risk.trailing_drawdown_pct)),
            )
            result = backtester.run(klines=klines)
            trades_csv_written = ""
            if effective_trades_csv is not None:
                _write_trades_csv(path=effective_trades_csv, trades=backtester.trades)
                trades_csv_written = str(effective_trades_csv)
            summary = {
                "symbol": result.symbol,
                "interval": result.interval,
                "strategy_id": strategy.strategy_id,
                "ma_type": effective_ma_type,
                "fast": effective_fast,
                "slow": effective_slow,
                "requested_start_utc": effective_start_utc or "",
                "requested_end_utc": effective_end_utc or "",
                "bars": result.bars,
                "trades": result.trades,
                "start_equity_usdt": str(result.start_equity_usdt),
                "end_equity_usdt": str(result.end_equity_usdt),
                "return_pct": str(result.return_pct),
                "max_drawdown_pct": str(result.max_drawdown_pct),
                "fee_rate": str(effective_fee_rate),
                "slippage_bps": str(effective_slippage_bps),
                "position_sizing": position_sizing,
                "cash_fraction": str(cash_fraction),
                "order_notional_usdt": str(order_notional_dec),
                "trailing_stop_enabled": cfg.risk.trailing_stop_enabled,
                "trailing_start_profit_pct": str(cfg.risk.trailing_start_profit_pct),
                "trailing_drawdown_pct": str(cfg.risk.trailing_drawdown_pct),
                "config": str(config),
                "trades_csv": trades_csv_written,
            }

            wins = sum(1 for t in backtester.trades if t.pnl_usdt > 0)
            trailing_exits = sum(1 for t in backtester.trades if t.exit_reason == "trailing_stop")
            cross_exits = sum(1 for t in backtester.trades if t.exit_reason == "cross_down")
            win_rate = (
                (Decimal(wins) / Decimal(len(backtester.trades))) * Decimal("100")
                if backtester.trades
                else Decimal("0")
            )
            if backtester.trades:
                avg_runup = sum(
                    (t.max_runup_pct for t in backtester.trades),
                    Decimal("0"),
                ) / Decimal(len(backtester.trades))
                max_runup = max((t.max_runup_pct for t in backtester.trades), default=Decimal("0"))
            else:
                avg_runup = Decimal("0")
                max_runup = Decimal("0")

            start_ms = klines[0].close_time_ms if klines else 0
            end_ms = klines[-2].close_time_ms if len(klines) >= 2 else 0
            pnl_usdt = result.end_equity_usdt - result.start_equity_usdt

            fee_rate_pct = Decimal(str(effective_fee_rate)) * Decimal("100")
            slippage_bps_dec = Decimal(str(effective_slippage_bps))
            slippage_pct = slippage_bps_dec / Decimal("100")

            header = (
                f"{result.symbol} | {result.interval} | "
                f"{effective_ma_type.upper()}({effective_fast},{effective_slow})"
            )
            period = f"{_ms_to_utc(start_ms)} ~ {_ms_to_utc(end_ms)}"
            line_stats = (
                f"K线: {result.bars} 交易: {result.trades} 胜率: {_fmt_pct(win_rate)}%"
            )
            line_exits = f"离场: Trailing {trailing_exits} | 死叉 {cross_exits}"
            line_runup = f"峰值浮盈: avg {_fmt_pct(avg_runup)}% max {_fmt_pct(max_runup)}%"
            line_pnl = (
                f"收益: {_fmt_usdt(pnl_usdt)} USDT ({_fmt_pct(result.return_pct)}%) "
                f"期末: {_fmt_usdt(result.end_equity_usdt)}"
            )
            line_risk = f"最大回撤: {_fmt_pct(result.max_drawdown_pct)}%"
            line_pos = (
                f"仓位: 复利 {_fmt_pct(cash_fraction * Decimal('100'))}% 现金"
                if position_sizing == "cash_fraction"
                else f"仓位: 固定名义 {_fmt_usdt(order_notional_dec)} USDT"
            )
            line_trail = (
                "离场保护: 关闭"
                if not cfg.risk.trailing_stop_enabled
                else (
                    "离场保护: Trailing "
                    f"start={_fmt_pct(Decimal(str(cfg.risk.trailing_start_profit_pct)))}% "
                    f"dd={_fmt_pct(Decimal(str(cfg.risk.trailing_drawdown_pct)))}%"
                )
            )
            line_cost = (
                f"成本: fee {_fmt_pct(fee_rate_pct)}% | "
                f"slippage {_fmt_pct(slippage_pct)}% ({slippage_bps_dec} bps)"
            )
            line_window = (
                f"请求区间: {effective_start_utc or '-'} ~ {effective_end_utc or '-'}"
            )
            telegram_text = "\n".join(
                [
                    "回测完成",
                    header,
                    f"区间: {period}",
                    line_stats,
                    line_exits,
                    line_runup,
                    line_pnl,
                    line_risk,
                    line_pos,
                    line_trail,
                    line_cost,
                    line_window,
                    f"交易明细: {trades_csv_written or '未导出'}",
                    f"配置: {str(config)}",
                ]
            )
            if effective_notify:
                await notifier.send(telegram_text)

            typer.echo(
                {
                    **summary,
                    "win_rate_pct": str(win_rate),
                    "trailing_exits": str(trailing_exits),
                    "cross_exits": str(cross_exits),
                    "avg_runup_pct": str(avg_runup),
                    "max_runup_pct": str(max_runup),
                }
            )
        finally:
            await notifier.aclose()
            await client.aclose()

    asyncio.run(_run())


@app.command()
def backtest_grid(
    config: Path = typer.Option(
        Path("configs/ma_cross.toml"),
        help="MA cross backtest config file (TOML).",
    ),
    fast_values: str | None = typer.Option(
        None,
        help="Comma-separated fast periods, e.g. 8,10,12.",
    ),
    slow_values: str | None = typer.Option(
        None,
        help="Comma-separated slow periods, e.g. 30,40,60.",
    ),
    ma_type: str | None = typer.Option(None, help="Override: sma|ema"),
    limit: int | None = typer.Option(
        None,
        help="Override: max bars to use in backtest (1-20000).",
    ),
    start: str | None = typer.Option(
        None,
        help="Override: UTC start time (ISO-8601), e.g. 2024-01-01T00:00:00Z.",
    ),
    end: str | None = typer.Option(
        None,
        help="Override: UTC end time (ISO-8601), e.g. 2024-12-31T23:59:59Z.",
    ),
    initial_cash_usdt: float | None = typer.Option(None, help="Override: initial cash in USDT."),
    order_notional_usdt: float | None = typer.Option(
        None,
        help="Override: order notional per BUY in USDT.",
    ),
    fee_rate: float | None = typer.Option(None, help="Override: fee rate (e.g. 0.001 = 0.1%)."),
    slippage_bps: float | None = typer.Option(
        None,
        help="Override: slippage in bps (1 bps = 0.01%).",
    ),
    top: int = typer.Option(10, help="Show top N parameter pairs."),
    results_csv: Path | None = typer.Option(
        None,
        help="Optional CSV output path for top results.",
    ),
    notify_telegram: bool | None = typer.Option(
        None,
        "--notify-telegram/--no-notify-telegram",
        help="Override: push summary to Telegram.",
    ),
) -> None:
    """
    Grid-search MA parameters (fast/slow) on the same backtest window.
    """
    settings = Settings()
    configure_logging(settings.log_level)

    if not config.exists():
        raise typer.BadParameter(f"config file not found: {config}")
    if top <= 0:
        raise typer.BadParameter("top must be > 0")

    try:
        cfg = load_ma_cross_backtest_config(config)
    except Exception as e:
        raise typer.BadParameter(f"invalid config: {e}") from e

    symbol = (cfg.market.symbol or settings.symbol).strip()
    interval = (cfg.market.interval or settings.interval).strip()

    effective_limit = limit if limit is not None else cfg.market.limit
    if effective_limit <= 0 or effective_limit > 20000:
        raise typer.BadParameter("limit must be between 1 and 20000")

    config_start_utc = cfg.market.start_utc.strip() if cfg.market.start_utc else ""
    config_end_utc = cfg.market.end_utc.strip() if cfg.market.end_utc else ""
    effective_start_utc = start if start is not None else (config_start_utc or None)
    effective_end_utc = end if end is not None else (config_end_utc or None)
    try:
        start_time_ms = (
            _parse_utc_to_ms(effective_start_utc) if effective_start_utc is not None else None
        )
    except ValueError as e:
        raise typer.BadParameter(str(e), param_hint="--start") from e
    try:
        end_time_ms = (
            _parse_utc_to_ms(effective_end_utc) if effective_end_utc is not None else None
        )
    except ValueError as e:
        raise typer.BadParameter(str(e), param_hint="--end") from e
    if start_time_ms is not None and end_time_ms is not None and start_time_ms >= end_time_ms:
        raise typer.BadParameter("start must be earlier than end")

    effective_ma_type = (ma_type if ma_type is not None else cfg.strategy.ma_type).strip().lower()
    if effective_ma_type not in ("sma", "ema"):
        raise typer.BadParameter("ma_type must be 'sma' or 'ema'")

    try:
        fast_list = _parse_period_list(
            value=fast_values,
            option_name="--fast-values",
            fallback=cfg.strategy.fast_period,
        )
        slow_list = _parse_period_list(
            value=slow_values,
            option_name="--slow-values",
            fallback=cfg.strategy.slow_period,
        )
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e

    pairs = _build_period_pairs(fast_values=fast_list, slow_values=slow_list)
    if not pairs:
        raise typer.BadParameter("no valid pair; ensure at least one fast < slow")

    effective_initial_cash = (
        initial_cash_usdt if initial_cash_usdt is not None else cfg.backtest.initial_cash_usdt
    )
    effective_fee_rate = fee_rate if fee_rate is not None else cfg.backtest.fee_rate
    effective_slippage_bps = (
        slippage_bps if slippage_bps is not None else cfg.backtest.slippage_bps
    )
    if effective_slippage_bps < 0 or effective_slippage_bps >= 10000:
        raise typer.BadParameter("slippage_bps must be within [0, 10000)")

    effective_notify = notify_telegram if notify_telegram is not None else cfg.telegram.notify
    position_sizing = cfg.backtest.position_sizing
    cash_fraction = Decimal(str(cfg.backtest.cash_fraction))
    order_notional_value = (
        order_notional_usdt if order_notional_usdt is not None else cfg.backtest.order_notional_usdt
    )
    order_notional_dec = Decimal(str(order_notional_value))

    async def _run() -> None:
        client = BinanceSpotClient(
            api_key=settings.binance_api_key,
            api_secret=settings.binance_api_secret,
        )
        notifier = TelegramNotifier(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
        try:
            klines = await _load_backtest_klines(
                client=client,
                symbol=symbol,
                interval=interval,
                limit=effective_limit,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
            )
            rows: list[GridResultRow] = []
            for fast, slow in pairs:
                strategy = MaCrossStrategy(
                    MaCrossParams(
                        fast_period=fast,
                        slow_period=slow,
                        ma_type=effective_ma_type,  # type: ignore[arg-type]
                    )
                )
                backtester = Backtester(
                    symbol=symbol,
                    interval=interval,
                    strategy=strategy,
                    initial_cash_usdt=Decimal(str(effective_initial_cash)),
                    position_sizing=position_sizing,
                    cash_fraction=cash_fraction,
                    order_notional_usdt=order_notional_dec,
                    fee_rate=Decimal(str(effective_fee_rate)),
                    slippage_bps=Decimal(str(effective_slippage_bps)),
                    lookback_bars=strategy.lookback_bars,
                    trailing_stop_enabled=cfg.risk.trailing_stop_enabled,
                    trailing_start_profit_pct=Decimal(str(cfg.risk.trailing_start_profit_pct)),
                    trailing_drawdown_pct=Decimal(str(cfg.risk.trailing_drawdown_pct)),
                )
                result = backtester.run(klines=klines)
                wins = sum(1 for t in backtester.trades if t.pnl_usdt > 0)
                win_rate = (
                    (Decimal(wins) / Decimal(len(backtester.trades))) * Decimal("100")
                    if backtester.trades
                    else Decimal("0")
                )
                rows.append(
                    GridResultRow(
                        fast=fast,
                        slow=slow,
                        trades=result.trades,
                        win_rate_pct=win_rate,
                        return_pct=result.return_pct,
                        max_drawdown_pct=result.max_drawdown_pct,
                        end_equity_usdt=result.end_equity_usdt,
                    )
                )

            ranked = _rank_grid_rows(rows=rows, top=top)
            if results_csv is not None:
                _write_grid_results_csv(path=results_csv, rows=ranked)

            top_rows = [
                {
                    "rank": i,
                    "fast": row.fast,
                    "slow": row.slow,
                    "trades": row.trades,
                    "win_rate_pct": str(row.win_rate_pct),
                    "return_pct": str(row.return_pct),
                    "max_drawdown_pct": str(row.max_drawdown_pct),
                    "end_equity_usdt": str(row.end_equity_usdt),
                }
                for i, row in enumerate(ranked, start=1)
            ]

            typer.echo(
                {
                    "symbol": symbol,
                    "interval": interval,
                    "ma_type": effective_ma_type,
                    "pairs_total": len(pairs),
                    "top_n": len(ranked),
                    "requested_start_utc": effective_start_utc or "",
                    "requested_end_utc": effective_end_utc or "",
                    "slippage_bps": str(effective_slippage_bps),
                    "results_csv": str(results_csv) if results_csv is not None else "",
                    "results": top_rows,
                }
            )

            if effective_notify and ranked:
                best = ranked[0]
                await notifier.send(
                    "\n".join(
                        [
                            "参数网格回测完成",
                            f"{symbol} | {interval} | {effective_ma_type.upper()}",
                            f"组合: {len(pairs)}  Top: {len(ranked)}",
                            f"最佳: fast={best.fast} slow={best.slow}",
                            (
                                f"收益: {_fmt_pct(best.return_pct)}%  "
                                f"回撤: {_fmt_pct(best.max_drawdown_pct)}%"
                            ),
                        ]
                    )
                )
        finally:
            await notifier.aclose()
            await client.aclose()

    asyncio.run(_run())
