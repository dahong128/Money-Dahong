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
    position_sizing: Literal["cash_fraction", "fixed_notional"] = "cash_fraction"
    cash_fraction: float = Field(default=0.8, gt=0, le=1)
    order_notional_usdt: float = Field(default=25.0, gt=0)
    fee_rate: float = Field(default=0.001, ge=0)


class TelegramConfig(BaseModel):
    notify: bool = True


class RiskConfig(BaseModel):
    trailing_stop_enabled: bool = True
    trailing_start_profit_pct: float = Field(default=30.0, ge=0)
    trailing_drawdown_pct: float = Field(default=10.0, ge=0)


class MaCrossBacktestConfig(BaseModel):
    market: MarketConfig = Field(default_factory=MarketConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)

    def validate_logic(self) -> None:
        if self.strategy.fast_period >= self.strategy.slow_period:
            raise ValueError("strategy.fast_period must be < strategy.slow_period")
        if self.backtest.position_sizing == "fixed_notional":
            if self.backtest.order_notional_usdt <= 0:
                raise ValueError("backtest.order_notional_usdt must be > 0")
        if self.backtest.position_sizing == "cash_fraction":
            if not (0 < self.backtest.cash_fraction <= 1):
                raise ValueError("backtest.cash_fraction must be within (0, 1]")
        if self.risk.trailing_stop_enabled:
            if self.risk.trailing_drawdown_pct <= 0:
                raise ValueError("risk.trailing_drawdown_pct must be > 0 when enabled")


def load_ma_cross_backtest_config(path: Path) -> MaCrossBacktestConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg = MaCrossBacktestConfig.model_validate(raw)
    cfg.validate_logic()
    return cfg
