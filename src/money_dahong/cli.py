from __future__ import annotations

import asyncio
import csv
import logging
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import typer

from money_dahong.backtest.engine import Backtester, BacktestResult
from money_dahong.backtest.reporting import write_backtest_report
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


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

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
    effective_order_notional = (
        order_notional_usdt if order_notional_usdt is not None else cfg.backtest.order_notional_usdt
    )
    effective_fee_rate = fee_rate if fee_rate is not None else cfg.backtest.fee_rate
    effective_notify = (
        notify_telegram if notify_telegram is not None else cfg.report.notify_telegram
    )

    report_dir = Path(cfg.report.dir)
    report_name = cfg.report.name

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
                order_notional_usdt=Decimal(str(effective_order_notional)),
                fee_rate=Decimal(str(effective_fee_rate)),
                lookback_bars=strategy.lookback_bars,
            )
            result = backtester.run(klines=klines, record_curve=True)
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
                "order_notional_usdt": str(effective_order_notional),
                "config": str(config),
            }

            name = report_name.strip() or (
                f"{result.symbol}_{result.interval}_{effective_ma_type}_f{effective_fast}_s{effective_slow}"
            )
            report_dir.mkdir(parents=True, exist_ok=True)
            out_dir = write_backtest_report(
                report_root=report_dir,
                report_name=name,
                summary=summary,
                trades=backtester.trades,
                equity_curve=backtester.equity_curve,
            )

            wins = sum(1 for t in backtester.trades if t.pnl_usdt > 0)
            win_rate = (
                (Decimal(wins) / Decimal(len(backtester.trades))) * Decimal("100")
                if backtester.trades
                else Decimal("0")
            )

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
            line_pnl = (
                f"收益: {_fmt_usdt(pnl_usdt)} USDT ({_fmt_pct(result.return_pct)}%) "
                f"期末: {_fmt_usdt(result.end_equity_usdt)}"
            )
            line_risk = f"最大回撤: {_fmt_pct(result.max_drawdown_pct)}%"
            line_cost = (
                f"手续费: {_fmt_pct(fee_rate_pct)}% 单笔名义: "
                f"{_fmt_usdt(Decimal(str(effective_order_notional)))} USDT"
            )
            telegram_text = "\n".join(
                [
                    "回测完成",
                    header,
                    f"区间: {period}",
                    line_stats,
                    line_pnl,
                    line_risk,
                    line_cost,
                    f"报告: {str(out_dir)}",
                ]
            )
            if effective_notify:
                await notifier.send(telegram_text)

            typer.echo({**summary, "win_rate_pct": str(win_rate), "report_dir": str(out_dir)})
        finally:
            await notifier.aclose()
            await client.aclose()

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
    session_root = report_root / (
        f"{_utc_stamp()}_{settings.symbol}_{settings.interval}_{ma_type_norm}"
    )
    session_root.mkdir(parents=True, exist_ok=False)

    best_score: Decimal | None = None
    best_summary: dict[str, str] | None = None

    results_csv = session_root / "results.csv"
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
                    report_root=session_root / "runs",
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
            "session_dir": str(session_root),
            "results_csv": str(results_csv),
        }
    )
