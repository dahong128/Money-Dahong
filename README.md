# Binance Quant Trading Tool

See `README_ZH.md` for the PRD and development plan (Chinese).

Confirmed scope (2026-02-01): Spot / Binance.com / CLI / single symbol + single strategy / engineering-first / ETHUSDT / Telegram alerts.

Quickstart:
- `python3.12 -m venv .venv && source .venv/bin/activate`
- `python -m pip install -e '.[dev]'`
- `cp .env.example .env`
- `money-dahong health`
- `money-dahong run`
- `money-dahong backtest --ma-type sma --fast 20 --slow 60 --limit 1000`

Docker:
- `cp .env.example .env`
- `docker compose build` (or `docker-compose build`)
- `docker compose --profile cli run --rm cli health` (or `docker-compose ...`)
- `docker compose --profile cli run --rm cli backtest --ma-type sma --fast 20 --slow 60 --limit 1000`
- `docker compose up -d bot` (or `docker-compose up -d bot`)
