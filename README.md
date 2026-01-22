# Money-Dahong 📈

基于 Web 的量化交易管理平台，支持 Binance 现货交易实时监控。

A web-based quantitative trading management platform with real-time Binance Spot trading monitoring.

---

## 中文说明

### ✨ 特性

- 🚀 **FastAPI 后端** - 高性能异步 Web 框架
- 💾 **SQLite 数据库** - 轻量级本地存储
- 📊 **实时价格监控** - Binance 现货实时行情
- 🎛️ **Web 控制面板** - Vue.js 3 + TailwindCSS 美观界面
- 🔄 **Live/Sandbox 切换** - 支持测试环境和实盘环境
- 📈 **多交易对支持** - 可配置监控多个交易对
- 🔒 **API 密钥管理** - 安全的密钥存储和验证
- 🎨 **暗色主题** - 护眼的深色界面

### 🛠️ 技术栈

- **后端**: Python 3.12+, FastAPI, SQLModel, ccxt
- **前端**: Vue.js 3 (CDN), TailwindCSS (CDN), HTML5 + Jinja2
- **数据库**: SQLite
- **任务调度**: asyncio

### 📦 快速开始

```bash
# 克隆仓库
git clone https://github.com/dahong128/Money-Dahong.git
cd Money-Dahong

# 创建虚拟环境（可选但推荐）
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 配置 API 密钥（可选，也可通过 Web 界面配置）
cp .env.example .env
# 编辑 .env 文件，填入你的 Binance API 密钥

# 运行服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 访问 Web 界面
# 打开浏览器访问 http://localhost:8000
```

### 📁 项目结构

```
Money-Dahong/
├── app/
│   ├── api/          # API 路由
│   ├── core/         # 核心配置（数据库、存储）
│   ├── models/       # 数据模型
│   ├── templates/    # HTML 模板（Vue.js + TailwindCSS）
│   └── main.py       # FastAPI 入口
├── engine/
│   ├── exchange.py   # Binance 交易所封装
│   ├── trader.py     # 交易循环管理器
│   └── strategies/   # 交易策略（待实现）
├── .env              # 环境变量（API 密钥）
├── requirements.txt  # Python 依赖
├── ARCHITECT.md      # 架构文档
└── README.md         # 本文件
```

### 🎯 核心功能

#### 1. Dashboard（仪表盘）
- 实时显示当前交易对价格
- 启动/停止交易机器人
- 查看系统日志

#### 2. Trading（交易）
- 切换监控的交易对
- 查看实时行情数据
- 配置更多交易对（跳转到 Settings）

#### 3. Settings（设置）
- 配置 Live/Sandbox API 密钥
- 切换 Live/Sandbox 模式
- 添加/删除交易对
- 调整轮询间隔
- 验证 API 密钥有效性

### 🔄 当前实现状态

| 功能 | 状态 |
|------|------|
| 实时价格监控 | ✅ 已完成 |
| 机器人启停控制 | ✅ 已完成 |
| API 密钥管理 | ✅ 已完成 |
| 多交易对支持 | ✅ 已完成 |
| 交易策略 | 🚧 待开发 |
| 实盘交易下单 | 🚧 待开发 |
| 交易日志记录 | 🚧 待开发 |
| 盈亏统计 | 🚧 待开发 |

### 🔐 API 密钥获取

1. 访问 [Binance 官网](https://www.binance.com) 注册账号
2. 进入 **API Management** 创建新 API Key
3. 建议先使用 Testnet 进行测试：
   - [Binance Testnet](https://testnet.binance.vision/)
4. 在 Settings 页面配置你的 API 密钥

### 📝 配置说明

**环境变量（.env）**:
```bash
# Live 环境（实盘）
BINANCE_API_KEY_LIVE=your_live_api_key
BINANCE_SECRET_LIVE=your_live_secret

# Sandbox 环境（测试）
BINANCE_API_KEY_SANDBOX=your_sandbox_api_key
BINANCE_SECRET_SANDBOX=your_sandbox_secret
```

**Web 配置**:
- 访问 `/settings` 页面
- 输入 API 密钥并点击 "Verify" 验证
- 切换 Sandbox/Live 模式
- 添加想要监控的交易对

### ⚠️ 注意事项

- **安全**: 不要将 `.env` 文件提交到 Git 仓库
- **风险**: 本项目目前仅供学习研究使用，实盘交易有资金损失风险
- **测试**: 建议先使用 Sandbox 环境充分测试
- **免责**: 作者不对任何交易损失负责

### 📄 许可证

MIT License

---

## English Documentation

### ✨ Features

- 🚀 **FastAPI Backend** - High-performance async web framework
- 💾 **SQLite Database** - Lightweight local storage
- 📊 **Real-time Price Monitoring** - Binance Spot live market data
- 🎛️ **Web Control Panel** - Beautiful UI with Vue.js 3 + TailwindCSS
- 🔄 **Live/Sandbox Toggle** - Support for testnet and live environments
- 📈 **Multi-pair Support** - Monitor multiple trading pairs
- 🔒 **API Key Management** - Secure key storage and verification
- 🎨 **Dark Theme** - Eye-friendly dark interface

### 🛠️ Tech Stack

- **Backend**: Python 3.12+, FastAPI, SQLModel, ccxt
- **Frontend**: Vue.js 3 (CDN), TailwindCSS (CDN), HTML5 + Jinja2
- **Database**: SQLite
- **Task Management**: asyncio

### 📦 Quick Start

```bash
# Clone the repository
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

# Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Access web interface
# Open browser at http://localhost:8000
```

### 📁 Project Structure

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
└── README.md         # This file
```

### 🎯 Core Features

#### 1. Dashboard
- Real-time price display for current trading pair
- Start/Stop trading bot control
- View system logs

#### 2. Trading
- Switch monitored trading pairs
- View real-time market data
- Configure more pairs (redirect to Settings)

#### 3. Settings
- Configure Live/Sandbox API keys
- Toggle Live/Sandbox mode
- Add/remove trading pairs
- Adjust poll interval
- Verify API key validity

### 🔄 Implementation Status

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

### 🔐 Getting API Keys

1. Sign up at [Binance](https://www.binance.com)
2. Go to **API Management** and create a new API Key
3. Recommended to start with Testnet:
   - [Binance Testnet](https://testnet.binance.vision/)
4. Configure your API keys in the Settings page

### 📝 Configuration

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

### ⚠️ Disclaimer

- **Security**: Do not commit `.env` file to Git repository
- **Risk**: This project is for educational purposes only. Live trading involves financial risk.
- **Testing**: Test thoroughly in Sandbox environment first.
- **Liability**: The author is not responsible for any trading losses.

### 📄 License

MIT License

---

## 🤝 Contributing

欢迎提交 Issue 和 Pull Request！

Issues and Pull Requests are welcome!

## 📮 Contact

**Author**: dahong128
**Email**: javierzhou128@gmail.com
**GitHub**: [dahong128](https://github.com/dahong128)

---

<div align="center">

**如果这个项目对你有帮助，请给个 ⭐️**

**If you find this project helpful, please give it a ⭐️**

Made with ❤️ by dahong128

</div>
