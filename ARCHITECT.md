# Project: Money-Dahong (Web-Based Quantitative Trading Platform)

## 1. Project Goal
本地化 Web 量化交易管理平台。
- **UI**: Dashboard 查看实时价格，Trading 页面切换交易对，Settings 页面管理 API 密钥和配置。
- **Engine**: Binance 现货交易背景异步任务（Live/Testnet），当前实现实时价格监控。

## 2. Tech Stack
- **Language**: Python 3.12+
- **Web Framework**: FastAPI (async)
- **Database**: SQLite with SQLModel
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
│   ├── /templates      # HTML files (Jinja2 + Vue.js)
│   ├── /static         # CSS/JS assets (empty)
│   └── main.py         # FastAPI entry point
├── /engine
│   ├── /strategies     # Strategy logic (empty, for future implementation)
│   ├── exchange.py     # CCXT wrapper for Binance
│   └── trader.py       # Trading loop manager
├── .env                # Secrets (API keys)
├── requirements.txt
├── ARCHITECT.md
└── README.md
```

## 4. Key Modules

### 4.1 Database Layer (`/app/models`)
- **SystemConfig**:
  - `binance_api_key_live`, `binance_secret_live`: Live API credentials
  - `binance_api_key_sandbox`, `binance_secret_sandbox`: Sandbox API credentials
  - `sandbox_mode`: Toggle between Live/Sandbox (default: True)
  - `allowed_symbols`: Comma-separated trading pairs (e.g., "BTC/USDT,ETH/USDT")
  - `poll_interval_seconds`: Price fetch interval (default: 3s)
  - `trading_enabled`: Enable/disable trading (default: True)
  - `is_active`: Bot running status (default: False)

- **TradeLog**:
  - Executed orders: symbol, side, price, amount, timestamp, profit
  - Not yet implemented in current version

### 4.2 Trading Engine (`/engine`)
- **ExchangeManager** (`exchange.py`): Singleton wrapper around `ccxt.binance`; loads API keys from database.
- **TraderBot** (`trader.py`):
  - `run_loop()`: Main async loop
  - Fetches current price for selected symbol every N seconds
  - Updates `data_store` with price and status
  - Logs errors without crashing

### 4.3 Web Interface (`/app/api/routes.py`)
- `GET /`: Render dashboard page
- `GET /trading`: Render trading pair selection page
- `GET /settings`: Render configuration page
- `GET /api/status`: Current price, symbol, status, config info
- `POST /api/toggle`: Start/stop trading bot
- `POST /api/config`: Update API keys, sandbox mode, symbols, poll interval
- `POST /api/symbol`: Change current trading pair
- `POST /api/verify_keys`: Verify Binance API credentials
- `GET /api/logs`: Recent system logs (in-memory)

### 4.4 Frontend (Vue.js 3 + TailwindCSS)
**Dashboard (`index.html`)**:
- Real-time price display (poll every 2s)
- Start/Stop bot control button
- System logs table

**Trading (`trading.html`)**:
- Trading pair dropdown selector
- Current symbol and price cards
- Link to settings for adding more symbols

**Settings (`settings.html`)**:
- Live/Sandbox API key configuration
- Sandbox mode toggle
- Allowed symbols editor
- Poll interval slider
- Trading enabled toggle
- API key verification button

## 5. Implementation Constraints
- **Concurrency**: Trading loop runs via `asyncio.create_task` in FastAPI startup; must not block the web server.
- **Resilience**: If Binance API fails, log error and continue; never crash the web server.
- **Style**: TailwindCSS with dark-mode UI.
- **No Build Process**: Frontend uses Vue.js 3 and TailwindCSS via CDN; no Node.js/npm required.

## 6. Current Implementation Status

### ✅ Completed Features
- FastAPI backend with SQLite database
- Binance Spot price monitoring (Live/Sandbox)
- Vue.js 3 frontend with multi-page navigation
- Real-time price display and bot control
- API key management and verification
- Trading pair selection and configuration
- System logging

### 🚧 To Be Implemented
- Trading strategies (RSI, MACD, etc.)
- Real order execution (buy/sell)
- Trade log recording
- Profit/Loss calculation and statistics
- More advanced technical indicators
- WebSocket support for real-time updates (optional)

## 7. API Key Setup
Create `.env` file in project root:
```bash
# Optional: Default API keys (can also be set via UI)
BINANCE_API_KEY_LIVE=your_live_api_key
BINANCE_SECRET_LIVE=your_live_secret
BINANCE_API_KEY_SANDBOX=your_sandbox_api_key
BINANCE_SECRET_SANDBOX=your_sandbox_secret
```

Or configure via web interface at `/settings`.

## 8. Running the Application
```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Access at http://localhost:8000
```
