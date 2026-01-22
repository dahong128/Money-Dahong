from typing import Optional

from sqlmodel import Field, SQLModel


class SystemConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=1, primary_key=True)
    binance_api_key_live: Optional[str] = Field(default=None, max_length=255)
    binance_secret_live: Optional[str] = Field(default=None, max_length=255)
    binance_api_key_sandbox: Optional[str] = Field(default=None, max_length=255)
    binance_secret_sandbox: Optional[str] = Field(default=None, max_length=255)
    sandbox_mode: bool = Field(default=True, index=True)
    allowed_symbols: str = Field(
        default="BTC/USDT,ETH/USDT,BNB/USDT",
        max_length=512,
        description="Comma separated symbols list",
    )
    poll_interval_seconds: int = Field(default=3)
    trading_enabled: bool = Field(default=True, index=True)
    is_active: bool = Field(default=False, index=True)
