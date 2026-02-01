from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Binance (spot)
    binance_api_key: str = Field(default="", validation_alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="", validation_alias="BINANCE_API_SECRET")

    # Bot
    symbol: str = Field(default="ETHUSDT", validation_alias="SYMBOL")
    interval: str = Field(default="1m", validation_alias="INTERVAL")
    trading_mode: Literal["dry_run", "live"] = Field(
        default="dry_run",
        validation_alias="TRADING_MODE",
    )
    confirm_live_trading: str = Field(default="", validation_alias="CONFIRM_LIVE_TRADING")

    # Risk (MVP)
    max_order_notional_usdt: float = Field(default=25.0, validation_alias="MAX_ORDER_NOTIONAL_USDT")
    cooldown_seconds: int = Field(default=60, validation_alias="COOLDOWN_SECONDS")

    # Strategy (EMA Cross)
    ema_fast_period: int = Field(default=12, validation_alias="EMA_FAST_PERIOD")
    ema_slow_period: int = Field(default=26, validation_alias="EMA_SLOW_PERIOD")

    # Telegram
    telegram_bot_token: str = Field(default="", validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", validation_alias="TELEGRAM_CHAT_ID")

    # Logging
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    def live_trading_enabled(self) -> bool:
        return self.trading_mode == "live" and self.confirm_live_trading.strip().upper() == "YES"
