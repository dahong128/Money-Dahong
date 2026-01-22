# Project: Money-Dahong (Web-Based Quantitative Trading Platform)

## 1. Project Goal
Local, web-based quantitative trading management platform.
- **UI**: Dashboard to view prices, manage API keys, toggle strategies, and view order history.
- **Engine**: Background async strategies on Binance Spot (Live/Testnet).

## 2. Tech Stack
- **Language**: Python 3.12+
- **Web Framework**: FastAPI (async)
- **Database**: SQLite with SQLModel or SQLAlchemy
- **Trading Interface**: ccxt (async)
- **Frontend**: HTML5 + Vue.js 3 (CDN) + TailwindCSS (CDN); no Node.js build steps
- **Task Management**: asyncio background tasks in FastAPI

## 3. Directory Structure
```text
/Money-Dahong
├── /app
│   ├── /api            # API endpoints (routes)
│   ├── /core           # Config, DB setup, events
│   ├── /models         # Database models (SQLModel)
│   ├── /templates      # HTML files (Jinja2)
│   ├── /static         # CSS/JS assets
│   └── main.py         # FastAPI entry point
├── /engine
│   ├── /strategies     # Strategy logic
│   ├── exchange.py     # CCXT wrapper for Binance
│   └── trader.py       # Trading loop manager
├── .env                # Secrets (API keys)
├── requirements.txt
└── ARCHITECT.md
```

## 4. Key Modules

### 4.1 Database Layer (`/app/models`)
- **SystemConfig**: `binance_api_key_live`, `binance_secret_live`, `binance_api_key_sandbox`, `binance_secret_sandbox`, `is_trading_active` (bool).
- **TradeLog**: Executed orders: symbol, side, price, amount, timestamp, profit.

### 4.2 Trading Engine (`/engine`)
- **ExchangeManager**: Singleton around `ccxt.binance`; reloads keys from DB.
- **StrategyRunner**: Async loop, active only when `SystemConfig.is_trading_active` is True.
- **Flow**: Fetch OHLCV → compute indicators (e.g., RSI, MACD) → execute mock or real orders.

### 4.3 Web Interface (`/app`)
- `GET /`: Render dashboard (SPA feel).
- `GET /api/status`: Current BTC price and strategy status (Running/Stopped).
- `POST /api/config`: Update API keys (live/sandbox).
- `POST /api/toggle`: Start/stop trading bot.
- `GET /api/logs`: Recent trade logs.

### 4.4 Frontend UX (Vue.js)
- Top bar: Connection status (green/red).
- Main card: BTC real-time price (poll every 2s).
- Control panel: "Start Bot" / "Stop Bot" buttons.
- Log table: Recent trades.
- Config section: Separate live/sandbox API key inputs.

## 5. Implementation Constraints
- **Concurrency**: Trading loop runs via `asyncio.create_task` in FastAPI startup; must not block the web server.
- **Resilience**: If Binance API fails, log the error; never crash the web server.
- **Style**: TailwindCSS; dark-mode UI.
