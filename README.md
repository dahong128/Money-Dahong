# Binance Quant Trading Tool

See `README_ZH.md` for the PRD and development plan (Chinese).

Confirmed scope (2026-02-01): Spot / Binance.com / CLI / single symbol + single strategy / engineering-first / ETHUSDT / Telegram alerts.

Docker:
- `cp .env.example .env`
- edit `configs/ma_cross.toml`
- `docker compose build` (or `docker-compose build`)
- `docker compose --profile cli run --rm cli health` (or `docker-compose ...`)
- Backtest (reads `configs/ma_cross.toml`): `docker compose --profile cli run --rm cli backtest`
- Run bot (default = MA cross, reads `configs/ma_cross.toml`): `docker compose up -d bot`

Live trading switch (in `.env`):
- `TRADING_MODE=live` and `CONFIRM_LIVE_TRADING=YES`
- Safety cap per BUY: `MAX_ORDER_NOTIONAL_USDT` (config sizing will be capped by this value)
