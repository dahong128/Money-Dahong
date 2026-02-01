from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


class MarketConfig(BaseModel):
    symbol: Optional[str] = None
    interval: Optional[str] = None
    limit: int = Field(default=1000, ge=1, le=1000)


class StrategyConfig(BaseModel):
    ma_type: Literal["sma", "ema"] = "sma"
    fast_period: int = Field(default=20, ge=1)
    slow_period: int = Field(default=60, ge=1)


class BacktestConfig(BaseModel):
    initial_cash_usdt: float = Field(default=1000.0, gt=0)
    order_notional_usdt: float = Field(default=25.0, gt=0)
    fee_rate: float = Field(default=0.001, ge=0)


class TelegramConfig(BaseModel):
    notify: bool = True


class MaCrossBacktestConfig(BaseModel):
    market: MarketConfig = Field(default_factory=MarketConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)

    def validate_logic(self) -> None:
        if self.strategy.fast_period >= self.strategy.slow_period:
            raise ValueError("strategy.fast_period must be < strategy.slow_period")


def load_ma_cross_backtest_config(path: Path) -> MaCrossBacktestConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg = MaCrossBacktestConfig.model_validate(raw)
    cfg.validate_logic()
    return cfg
