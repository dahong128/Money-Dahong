# Money-Dahong（币安现货量化 CLI 工具）

一个以工程稳定性为优先的 Binance 现货量化程序，当前聚焦在：

- 单进程 bot、单交易对、单策略实例
- CLI 驱动（无 Web 面板）
- 策略：`EMA Cross`、`MA Cross`
- 模式：`dry_run`（演练）与 `live`（实盘）
- 告警：Telegram
- 能力：实盘运行、单次回测、参数网格回测、Docker 部署

英文版见 `README.md`。

## 1. 环境要求

- Python `>=3.12`
- （可选）Docker + Docker Compose
- Binance API Key/Secret（实盘或私有接口需要）
- Telegram Bot Token/Chat ID（可选）

## 2. 快速开始（本地 Python）

```bash
cp .env.example .env
# 修改 .env、configs/ema_cross.toml、configs/ma_cross.toml

python3.14 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

money-dahong health
```

启动 MA 策略（默认读取 `configs/ma_cross.toml`）：

```bash
money-dahong run-ma
```

启动 EMA 策略（读取 `configs/ema_cross.toml`）：

```bash
money-dahong run
```

## 3. 快速开始（Docker）

```bash
cp .env.example .env
# 修改 .env、configs/ema_cross.toml、configs/ma_cross.toml

docker compose build

docker compose --profile cli run --rm cli health
docker compose --profile cli run --rm cli backtest
docker compose --profile cli run --rm cli backtest-grid --fast-values 8,10,12 --slow-values 30,40,60 --top 5 --results-csv build/grid_top5.csv

docker compose up -d bot
docker compose logs -f bot
docker compose down
```

如果你环境里是旧命令，也可用 `docker-compose`。

## 4. 命令总览

```bash
money-dahong --help
```

核心命令：

- `config-init`：初始化 `.env`
- `show-config`：查看生效配置（敏感字段脱敏）
- `health`：连通 Binance 并查看 server time
- `alerts-test`：发送 Telegram 测试消息
- `run`：运行 EMA 策略 bot（读取 `configs/ema_cross.toml`）
- `run-ma`：运行 MA 策略 bot（TOML 配置）
- `backtest`：单组参数回测
- `backtest-grid`：多组 MA 参数网格回测

## 5. 回测说明

### 5.1 单组回测示例

```bash
money-dahong backtest \
  --start 2024-01-01T00:00:00Z \
  --end 2024-12-31T23:59:59Z \
  --limit 5000 \
  --slippage-bps 5 \
  --trades-csv build/backtest_trades.csv
```

### 5.2 参数网格回测示例

```bash
money-dahong backtest-grid \
  --fast-values 8,10,12,15 \
  --slow-values 30,40,60 \
  --start 2024-01-01T00:00:00Z \
  --end 2024-12-31T23:59:59Z \
  --top 10 \
  --results-csv build/grid_top10.csv
```

### 5.3 关键规则

- `limit` 上限：`20000` 根 K 线。
- 指定 `--start` 后会自动分页拉取（每次最多 `1000`）。
- `slippage_bps`：`1 bps = 0.01%`。
- 回测会忽略最后一根可能未收盘的 K 线。

## 6. 配置说明

### 6.1 `.env`（运行态与密钥）

重点字段：

- Binance：`BINANCE_API_KEY`、`BINANCE_API_SECRET`
- 运行态：`SYMBOL`、`INTERVAL`、`TRADING_MODE`、`CONFIRM_LIVE_TRADING`
- 风控：`MAX_ORDER_NOTIONAL_USDT`、`COOLDOWN_SECONDS`
- 告警：`TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`
- 日志：`LOG_LEVEL`

实盘开关必须同时满足：

- `TRADING_MODE=live`
- `CONFIRM_LIVE_TRADING=YES`

### 6.2 `configs/ema_cross.toml`（EMA 实盘参数）

- `[market]`：`symbol`、`interval`
- `[strategy]`：`fast_period`、`slow_period`

### 6.3 `configs/ma_cross.toml`（MA 策略/回测参数）

- `[market]`：`symbol`、`interval`、`limit`、`start_utc`、`end_utc`
- `[strategy]`：`ma_type`、`fast_period`、`slow_period`
- `[backtest]`：仓位模式、手续费、滑点、交易明细 CSV
- `[risk]`：Trailing Stop 参数
- `[telegram]`：回测摘要推送开关

## 7. 当前可靠性能力

已实现：

- Binance 请求重试与退避（超时/传输错误/`429`/`5xx`）
- signed 请求 `recvWindow` + 时间漂移自动校时
- 交易主循环异常恢复（tick 失败后退避并按冷却告警）
- 通知通道失败不影响订单状态更新

## 8. 开发与自检

```bash
ruff check .
mypy src
pytest -q
```

## 9. 风险提示

该程序在满足实盘开关条件时会真实下单。
建议先 `dry_run`，再小额实盘，持续观察日志与告警后再放量。
