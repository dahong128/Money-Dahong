from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import typer

from money_dahong.engine.trader import Trader
from money_dahong.exchange import BinanceSpotClient
from money_dahong.logging_utils import configure_logging
from money_dahong.notifications.telegram import TelegramNotifier
from money_dahong.settings import Settings
from money_dahong.strategies.ema_cross import EmaCrossParams, EmaCrossStrategy

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
