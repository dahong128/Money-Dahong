from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from pathlib import Path

import typer

from money_dahong.backtest.engine import Backtester
from money_dahong.engine.trader import Trader
from money_dahong.exchange import BinanceSpotClient
from money_dahong.logging_utils import configure_logging
from money_dahong.notifications.telegram import TelegramNotifier
from money_dahong.settings import Settings
from money_dahong.strategies.ema_cross import EmaCrossParams, EmaCrossStrategy
from money_dahong.strategies.ma_cross import MaCrossParams, MaCrossStrategy

app = typer.Typer(no_args_is_help=True, add_completion=False)
logger = logging.getLogger("money_dahong")


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
    fast: int = typer.Option(20, help="Fast MA period."),
    slow: int = typer.Option(60, help="Slow MA period."),
    ma_type: str = typer.Option("sma", help="sma|ema"),
    limit: int = typer.Option(1000, help="Number of latest klines to fetch (max 1000)."),
    initial_cash_usdt: float = typer.Option(1000.0, help="Initial cash in USDT."),
    order_notional_usdt: float = typer.Option(25.0, help="Order notional per BUY in USDT."),
    fee_rate: float = typer.Option(0.001, help="Fee rate (e.g. 0.001 = 0.1%)."),
) -> None:
    """
    Backtest the MA cross strategy on latest Binance klines (REST).
    """
    settings = Settings()
    configure_logging(settings.log_level)

    if limit <= 0 or limit > 1000:
        raise typer.BadParameter("limit must be between 1 and 1000")

    ma_type_norm = ma_type.strip().lower()
    if ma_type_norm not in ("sma", "ema"):
        raise typer.BadParameter("ma_type must be 'sma' or 'ema'")

    strategy = MaCrossStrategy(
        MaCrossParams(
            fast_period=fast,
            slow_period=slow,
            ma_type=ma_type_norm,  # type: ignore[arg-type]
        )
    )

    async def _run() -> None:
        client = BinanceSpotClient(
            api_key=settings.binance_api_key,
            api_secret=settings.binance_api_secret,
        )
        try:
            klines = await client.klines(
                symbol=settings.symbol,
                interval=settings.interval,
                limit=limit,
            )
        finally:
            await client.aclose()

        backtester = Backtester(
            symbol=settings.symbol,
            interval=settings.interval,
            strategy=strategy,
            initial_cash_usdt=Decimal(str(initial_cash_usdt)),
            order_notional_usdt=Decimal(str(order_notional_usdt)),
            fee_rate=Decimal(str(fee_rate)),
            lookback_bars=strategy.lookback_bars,
        )
        result = backtester.run(klines=klines)
        typer.echo(
            {
                "symbol": result.symbol,
                "interval": result.interval,
                "bars": result.bars,
                "trades": result.trades,
                "start_equity_usdt": str(result.start_equity_usdt),
                "end_equity_usdt": str(result.end_equity_usdt),
                "return_pct": str(result.return_pct),
                "max_drawdown_pct": str(result.max_drawdown_pct),
            }
        )

    asyncio.run(_run())
