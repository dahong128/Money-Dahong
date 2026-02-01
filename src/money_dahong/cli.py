from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import typer

from money_dahong.backtest.engine import Backtester
from money_dahong.config.ma_cross import load_ma_cross_backtest_config
from money_dahong.engine.trader import Trader
from money_dahong.exchange import BinanceSpotClient
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
def run() -> None:
    """
    Run the ETHUSDT bot (single symbol + single strategy).
    """
    settings = Settings()
    configure_logging(settings.log_level)

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
                fast_period=settings.ema_fast_period,
                slow_period=settings.ema_slow_period,
            )
        )
        trader = Trader(settings=settings, client=client, strategy=strategy, notifier=notifier)
        try:
            await trader.run()
        finally:
            await notifier.aclose()
            await client.aclose()

    asyncio.run(_run())


@app.command()
def run_ma() -> None:
    """
    Run the MA cross bot (double moving average, default SMA).
    """
    settings = Settings()
    configure_logging(settings.log_level)

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
                fast_period=settings.ma_fast_period,
                slow_period=settings.ma_slow_period,
                ma_type=settings.ma_type,
            )
        )
        trader = Trader(settings=settings, client=client, strategy=strategy, notifier=notifier)
        try:
            await trader.run()
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
        help="Override: number of latest klines to fetch (max 1000).",
    ),
    initial_cash_usdt: float | None = typer.Option(None, help="Override: initial cash in USDT."),
    order_notional_usdt: float | None = typer.Option(
        None,
        help="Override: order notional per BUY in USDT.",
    ),
    fee_rate: float | None = typer.Option(None, help="Override: fee rate (e.g. 0.001 = 0.1%)."),
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
    if effective_limit <= 0 or effective_limit > 1000:
        raise typer.BadParameter("limit must be between 1 and 1000")

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
            klines = await client.klines(symbol=symbol, interval=interval, limit=effective_limit)

            backtester = Backtester(
                symbol=symbol,
                interval=interval,
                strategy=strategy,
                initial_cash_usdt=Decimal(str(effective_initial_cash)),
                position_sizing=position_sizing,
                cash_fraction=cash_fraction,
                order_notional_usdt=order_notional_dec,
                fee_rate=Decimal(str(effective_fee_rate)),
                lookback_bars=strategy.lookback_bars,
                trailing_stop_enabled=cfg.risk.trailing_stop_enabled,
                trailing_start_profit_pct=Decimal(str(cfg.risk.trailing_start_profit_pct)),
                trailing_drawdown_pct=Decimal(str(cfg.risk.trailing_drawdown_pct)),
            )
            result = backtester.run(klines=klines)
            summary = {
                "symbol": result.symbol,
                "interval": result.interval,
                "strategy_id": strategy.strategy_id,
                "ma_type": effective_ma_type,
                "fast": effective_fast,
                "slow": effective_slow,
                "bars": result.bars,
                "trades": result.trades,
                "start_equity_usdt": str(result.start_equity_usdt),
                "end_equity_usdt": str(result.end_equity_usdt),
                "return_pct": str(result.return_pct),
                "max_drawdown_pct": str(result.max_drawdown_pct),
                "fee_rate": str(effective_fee_rate),
                "position_sizing": position_sizing,
                "cash_fraction": str(cash_fraction),
                "order_notional_usdt": str(order_notional_dec),
                "trailing_stop_enabled": cfg.risk.trailing_stop_enabled,
                "trailing_start_profit_pct": str(cfg.risk.trailing_start_profit_pct),
                "trailing_drawdown_pct": str(cfg.risk.trailing_drawdown_pct),
                "config": str(config),
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
            line_cost = f"手续费: {_fmt_pct(fee_rate_pct)}%"
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
