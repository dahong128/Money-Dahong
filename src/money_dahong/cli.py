from __future__ import annotations

import asyncio
import csv
import logging
from decimal import Decimal
from pathlib import Path

import typer

from money_dahong.backtest.engine import Backtester, BacktestResult
from money_dahong.backtest.reporting import write_backtest_report
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

def _score_result(*, result: BacktestResult, metric: str) -> Decimal:
    if metric == "return_pct":
        return result.return_pct
    if metric == "end_equity":
        return result.end_equity_usdt
    if metric == "return_over_drawdown":
        dd = result.max_drawdown_pct
        if dd <= 0:
            dd = Decimal("0.0001")
        return result.return_pct / dd
    raise ValueError(f"unknown metric: {metric}")


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
    report_dir: Path = typer.Option(
        Path("reports/backtest"),
        help="Directory to write the backtest report into.",
    ),
    report_name: str = typer.Option("", help="Optional report name suffix."),
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
        result = backtester.run(klines=klines, record_curve=True)
        summary = {
            "symbol": result.symbol,
            "interval": result.interval,
            "strategy_id": strategy.strategy_id,
            "ma_type": ma_type_norm,
            "fast": fast,
            "slow": slow,
            "bars": result.bars,
            "trades": result.trades,
            "start_equity_usdt": str(result.start_equity_usdt),
            "end_equity_usdt": str(result.end_equity_usdt),
            "return_pct": str(result.return_pct),
            "max_drawdown_pct": str(result.max_drawdown_pct),
            "fee_rate": str(fee_rate),
            "order_notional_usdt": str(order_notional_usdt),
        }
        name = report_name.strip() or (
            f"{result.symbol}_{result.interval}_{ma_type_norm}_f{fast}_s{slow}"
        )
        report_dir.mkdir(parents=True, exist_ok=True)
        out_dir = write_backtest_report(
            report_root=report_dir,
            report_name=name,
            summary=summary,
            trades=backtester.trades,
            equity_curve=backtester.equity_curve,
        )
        typer.echo({**summary, "report_dir": str(out_dir)})

    asyncio.run(_run())


@app.command()
def optimize_ma(
    ma_type: str = typer.Option("sma", help="sma|ema"),
    fast_min: int = typer.Option(5, help="Fast MA min period."),
    fast_max: int = typer.Option(30, help="Fast MA max period (inclusive)."),
    slow_min: int = typer.Option(20, help="Slow MA min period."),
    slow_max: int = typer.Option(200, help="Slow MA max period (inclusive)."),
    slow_step: int = typer.Option(5, help="Slow MA step."),
    limit: int = typer.Option(1000, help="Number of latest klines to fetch (max 1000)."),
    initial_cash_usdt: float = typer.Option(1000.0, help="Initial cash in USDT."),
    order_notional_usdt: float = typer.Option(25.0, help="Order notional per BUY in USDT."),
    fee_rate: float = typer.Option(0.001, help="Fee rate (e.g. 0.001 = 0.1%)."),
    metric: str = typer.Option(
        "return_over_drawdown",
        help="return_pct|end_equity|return_over_drawdown",
    ),
    min_trades: int = typer.Option(1, help="Skip parameter sets with fewer trades than this."),
    report_dir: Path = typer.Option(
        Path("reports/optimize_ma"),
        help="Directory to write optimization reports into.",
    ),
    report_per_run: bool = typer.Option(
        True,
        help="Write a report folder for every tested parameter set.",
    ),
    max_runs: int = typer.Option(
        300,
        help="Safety cap for total runs when report_per_run is enabled.",
    ),
) -> None:
    """
    Grid-search MA periods on latest Binance klines and print the best parameters.
    """
    settings = Settings()
    configure_logging(settings.log_level)

    if limit <= 0 or limit > 1000:
        raise typer.BadParameter("limit must be between 1 and 1000")
    if fast_min <= 0 or fast_max <= 0 or slow_min <= 0 or slow_max <= 0 or slow_step <= 0:
        raise typer.BadParameter("periods/step must be > 0")
    if fast_min > fast_max:
        raise typer.BadParameter("fast_min must be <= fast_max")
    if slow_min > slow_max:
        raise typer.BadParameter("slow_min must be <= slow_max")

    ma_type_norm = ma_type.strip().lower()
    if ma_type_norm not in ("sma", "ema"):
        raise typer.BadParameter("ma_type must be 'sma' or 'ema'")

    metric_norm = metric.strip().lower()
    if metric_norm not in ("return_pct", "end_equity", "return_over_drawdown"):
        raise typer.BadParameter("metric must be return_pct|end_equity|return_over_drawdown")

    async def _fetch_klines() -> list[Kline]:
        client = BinanceSpotClient(
            api_key=settings.binance_api_key,
            api_secret=settings.binance_api_secret,
        )
        try:
            return await client.klines(
                symbol=settings.symbol,
                interval=settings.interval,
                limit=limit,
            )
        finally:
            await client.aclose()

    klines = asyncio.run(_fetch_klines())

    candidates: list[tuple[int, int]] = []
    for slow in range(slow_min, slow_max + 1, slow_step):
        for fast in range(fast_min, fast_max + 1):
            if fast >= slow:
                continue
            candidates.append((fast, slow))

    if report_per_run and len(candidates) > max_runs:
        raise typer.BadParameter(
            f"Grid has {len(candidates)} runs; increase --max-runs or set --no-report-per-run"
        )

    report_root = report_dir
    report_root.mkdir(parents=True, exist_ok=True)

    best_score: Decimal | None = None
    best_summary: dict[str, str] | None = None

    results_csv = report_root / "results.csv"
    with results_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ma_type",
                "fast",
                "slow",
                "bars",
                "trades",
                "start_equity_usdt",
                "end_equity_usdt",
                "return_pct",
                "max_drawdown_pct",
                "score",
            ],
        )
        writer.writeheader()

        for fast, slow in candidates:
            strategy = MaCrossStrategy(
                MaCrossParams(
                    fast_period=fast,
                    slow_period=slow,
                    ma_type=ma_type_norm,  # type: ignore[arg-type]
                )
            )
            bt = Backtester(
                symbol=settings.symbol,
                interval=settings.interval,
                strategy=strategy,
                initial_cash_usdt=Decimal(str(initial_cash_usdt)),
                order_notional_usdt=Decimal(str(order_notional_usdt)),
                fee_rate=Decimal(str(fee_rate)),
                lookback_bars=strategy.lookback_bars,
            )
            result = bt.run(klines=klines, record_curve=report_per_run)
            if result.trades < min_trades:
                continue

            score = _score_result(result=result, metric=metric_norm)
            row = {
                "ma_type": ma_type_norm,
                "fast": str(fast),
                "slow": str(slow),
                "bars": str(result.bars),
                "trades": str(result.trades),
                "start_equity_usdt": str(result.start_equity_usdt),
                "end_equity_usdt": str(result.end_equity_usdt),
                "return_pct": str(result.return_pct),
                "max_drawdown_pct": str(result.max_drawdown_pct),
                "score": str(score),
            }
            writer.writerow(row)

            if report_per_run:
                run_name = f"{settings.symbol}_{settings.interval}_{ma_type_norm}_f{fast}_s{slow}"
                write_backtest_report(
                    report_root=report_root / "runs",
                    report_name=run_name,
                    summary={
                        **row,
                        "symbol": settings.symbol,
                        "interval": settings.interval,
                        "strategy_id": strategy.strategy_id,
                        "fee_rate": str(fee_rate),
                        "order_notional_usdt": str(order_notional_usdt),
                    },
                    trades=bt.trades,
                    equity_curve=bt.equity_curve,
                )

            if best_score is None or score > best_score:
                best_score = score
                best_summary = row

    if not best_summary:
        typer.echo({"ok": False, "reason": "no_candidates_matched_constraints"})
        raise typer.Exit(code=1)

    typer.echo(
        {
            "ok": True,
            "metric": metric_norm,
            "best": best_summary,
            "results_csv": str(results_csv),
        }
    )
