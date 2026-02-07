# Money-Dahong

Binance spot quant trading tool (CLI-first, engineering-first).

- Exchange: `Binance.com` spot
- Runtime: single bot process, single symbol, single strategy instance
- Strategies: `EMA Cross` and `MA Cross`
- Modes: `dry_run` and `live`
- Alerts: Telegram
- Includes: live runner, backtest, parameter grid backtest, Docker deployment

For Chinese documentation, see `README_ZH.md`.

## 1. Prerequisites

- Python `>=3.12`
- (Optional) Docker + Docker Compose
- Binance API key/secret (for private endpoints/live trading)
- Telegram bot token/chat id (optional)

## 2. Quick Start (Local Python)

```bash
cp .env.example .env
# edit .env, configs/ema_cross.toml, configs/ma_cross.toml

python3.14 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

money-dahong health
```

Run MA bot (default from `configs/ma_cross.toml`):

```bash
money-dahong run-ma
```

Run EMA bot (reads `configs/ema_cross.toml`):

```bash
money-dahong run
```

## 3. Quick Start (Docker)

```bash
cp .env.example .env
# edit .env, configs/ema_cross.toml, configs/ma_cross.toml

docker compose build

docker compose --profile cli run --rm cli health
docker compose --profile cli run --rm cli backtest
docker compose --profile cli run --rm cli backtest-grid --fast-values 8,10,12 --slow-values 30,40,60 --top 5 --results-csv build/grid_top5.csv

docker compose up -d bot
docker compose logs -f bot
docker compose down
```

`docker-compose` command is also supported if your environment uses legacy compose.

## 4. Command Overview

```bash
money-dahong --help
```

Main commands:

- `config-init`: copy `.env.example` to `.env`
- `show-config`: print effective config (secrets redacted)
- `health`: check Binance connectivity and server time
- `alerts-test`: send test Telegram message
- `run`: run EMA strategy bot via `configs/ema_cross.toml`
- `run-ma`: run MA strategy bot via `configs/ma_cross.toml`
- `backtest`: single MA parameter backtest
- `backtest-grid`: MA parameter grid backtest

## 5. Backtest Usage

Single backtest example:

```bash
money-dahong backtest \
  --start 2024-01-01T00:00:00Z \
  --end 2024-12-31T23:59:59Z \
  --limit 5000 \
  --slippage-bps 5 \
  --trades-csv build/backtest_trades.csv
```

Grid search example:

```bash
money-dahong backtest-grid \
  --fast-values 8,10,12,15 \
  --slow-values 30,40,60 \
  --start 2024-01-01T00:00:00Z \
  --end 2024-12-31T23:59:59Z \
  --top 10 \
  --results-csv build/grid_top10.csv
```

Notes:

- `limit` max is `20000` bars.
- If `--start` is set, klines are fetched with pagination (`1000` per request).
- `slippage_bps`: `1 bps = 0.01%`.
- Backtester ignores the last potentially-forming candle.

## 6. Configuration

### 6.1 `.env` (runtime / secrets)

Important keys in `.env`:

- Binance: `BINANCE_API_KEY`, `BINANCE_API_SECRET`
- Runtime: `SYMBOL`, `INTERVAL`, `TRADING_MODE`, `CONFIRM_LIVE_TRADING`
- Risk: `MAX_ORDER_NOTIONAL_USDT`, `COOLDOWN_SECONDS`
- Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- Logging: `LOG_LEVEL`

Live mode is enabled only when both are true:

- `TRADING_MODE=live`
- `CONFIRM_LIVE_TRADING=YES`

### 6.2 `configs/ema_cross.toml` (EMA live params)

Sections:

- `[market]`: `symbol`, `interval`
- `[strategy]`: `fast_period`, `slow_period`

### 6.3 `configs/ma_cross.toml` (strategy + backtest/live MA params)

Sections:

- `[market]`: `symbol`, `interval`, `limit`, `start_utc`, `end_utc`
- `[strategy]`: `ma_type`, `fast_period`, `slow_period`
- `[backtest]`: sizing, fee, slippage, trade CSV output path
- `[risk]`: trailing stop params
- `[telegram]`: backtest summary notification toggle

## 7. Reliability Notes

Current implementation includes:

- Request retries with backoff for timeout/transport/`429`/`5xx`
- Signed request `recvWindow` and timestamp drift auto-sync handling
- Trader tick-loop exception recovery with cooldown error notifications
- Notification failures do not break order-state updates

## 8. Development

```bash
ruff check .
mypy src
pytest -q
```

## 9. Safety

This software can place real orders when live mode is enabled.
Always start with `dry_run`, then small notional values, and review logs/alerts continuously.
