from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class MarketConfig(BaseModel):
    symbol: Optional[str] = None
    interval: Optional[str] = None


class StrategyConfig(BaseModel):
    fast_period: int = Field(default=12, ge=1)
    slow_period: int = Field(default=26, ge=1)


class EmaCrossRunConfig(BaseModel):
    market: MarketConfig = Field(default_factory=MarketConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)

    def validate_logic(self) -> None:
        if self.strategy.fast_period >= self.strategy.slow_period:
            raise ValueError("strategy.fast_period must be < strategy.slow_period")


def load_ema_cross_run_config(path: Path) -> EmaCrossRunConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg = EmaCrossRunConfig.model_validate(raw)
    cfg.validate_logic()
    return cfg
