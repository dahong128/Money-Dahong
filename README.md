# Money-Dahong 📈

A web-based quantitative trading management platform with real-time Binance Spot trading monitoring.

---

## ✨ Features

- 🚀 **FastAPI Backend** - High-performance async web framework
- 💾 **SQLite Database** - Lightweight local storage
- 📊 **Real-time Price Monitoring** - Binance Spot live market data
- 🎛️ **Web Control Panel** - Beautiful UI with Vue.js 3 + TailwindCSS
- 🔄 **Live/Sandbox Toggle** - Support for testnet and live environments
- 📈 **Multi-pair Support** - Monitor multiple trading pairs
- 🔒 **API Key Management** - Secure key storage and verification
- 🎨 **Dark Theme** - Eye-friendly dark interface

## 🛠️ Tech Stack

- **Backend**: Python 3.12+, FastAPI, SQLModel, ccxt
- **Frontend**: Vue.js 3 (CDN), TailwindCSS (CDN), HTML5 + Jinja2
- **Database**: SQLite
- **Task Management**: asyncio

## 📦 Quick Start

```bash
# Clone repository
git clone https://github.com/dahong128/Money-Dahong.git
cd Money-Dahong

# Create virtual environment (optional but recommended)
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure API keys (optional, can also be done via web UI)
cp .env.example .env
# Edit .env file and add your Binance API keys

# Run server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Access web interface
# Open browser at http://localhost:8000
```

## 📁 Project Structure

```
Money-Dahong/
├── app/
│   ├── api/          # API routes
│   ├── core/         # Core config (database, store)
│   ├── models/       # Data models
│   ├── templates/    # HTML templates (Vue.js + TailwindCSS)
│   └── main.py       # FastAPI entry point
├── engine/
│   ├── exchange.py   # Binance exchange wrapper
│   ├── trader.py     # Trading loop manager
│   └── strategies/   # Trading strategies (to be implemented)
├── .env              # Environment variables (API keys)
├── requirements.txt  # Python dependencies
├── ARCHITECT.md      # Architecture documentation
└── README.md         # This file (English)
```

## 🎯 Core Features

### 1. Dashboard
- Real-time price display for current trading pair
- Start/Stop trading bot control
- View system logs

### 2. Trading
- Switch monitored trading pairs
- View real-time market data
- Configure more pairs (redirect to Settings)

### 3. Settings
- Configure Live/Sandbox API keys
- Toggle Live/Sandbox mode
- Add/remove trading pairs
- Adjust poll interval
- Verify API key validity

## 🔄 Implementation Status

| Feature | Status |
|---------|--------|
| Real-time price monitoring | ✅ Completed |
| Bot start/stop control | ✅ Completed |
| API key management | ✅ Completed |
| Multi-pair support | ✅ Completed |
| Trading strategies | 🚧 To be implemented |
| Real trading execution | 🚧 To be implemented |
| Trade logging | 🚧 To be implemented |
| P/L statistics | 🚧 To be implemented |

## 🔐 Getting API Keys

1. Sign up at [Binance](https://www.binance.com)
2. Go to **API Management** and create a new API Key
3. Recommended to start with Testnet:
   - [Binance Testnet](https://testnet.binance.vision/)
4. Configure your API keys in Settings page

## 📝 Configuration

**Environment Variables (.env)**:
```bash
# Live Environment
BINANCE_API_KEY_LIVE=your_live_api_key
BINANCE_SECRET_LIVE=your_live_secret

# Sandbox Environment (Testnet)
BINANCE_API_KEY_SANDBOX=your_sandbox_api_key
BINANCE_SECRET_SANDBOX=your_sandbox_secret
```

**Web Configuration**:
- Visit `/settings` page
- Enter API keys and click "Verify"
- Toggle Sandbox/Live mode
- Add trading pairs to monitor

## ⚠️ Disclaimer

- **Security**: Do not commit `.env` file to Git repository
- **Risk**: This project is for educational purposes only. Live trading involves financial risk.
- **Testing**: Test thoroughly in Sandbox environment first.
- **Liability**: The author is not responsible for any trading losses.

## 📄 License

MIT License

---

## 🤝 Contributing

Issues and Pull Requests are welcome!

## 📮 Contact

**Author**: dahong128
**Email**: javierzhou128@gmail.com
**GitHub**: [dahong128](https://github.com/dahong128)

---

<div align="center">

If you find this project helpful, please give it a ⭐️

Made with ❤️ by dahong128

</div>
