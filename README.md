# Binance Quant Trading Tool

See `README_ZH.md` for the PRD and development plan (Chinese).

Confirmed scope (2026-02-01): Spot / Binance.com / CLI / single symbol + single strategy / engineering-first / ETHUSDT / Telegram alerts.

Docker:
- `cp .env.example .env`
- edit `configs/ma_cross.toml`
- `docker compose build` (or `docker-compose build`)
- `docker compose --profile cli run --rm cli health` (or `docker-compose ...`)
- `docker compose --profile cli run --rm cli backtest`
- `docker compose --profile cli run --rm cli optimize-ma --ma-type sma --fast-min 5 --fast-max 30 --slow-min 20 --slow-max 200 --slow-step 5 --limit 1000`
- `docker compose up -d bot` (or `docker-compose up -d bot`)
