from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from money_dahong.exchange.binance_spot import Kline
from money_dahong.types import Signal


@dataclass(frozen=True)
class StrategyContext:
    symbol: str
    in_position: bool
    position_qty: Decimal


class Strategy(ABC):
    strategy_id: str

    @abstractmethod
    def generate_signal(self, *, klines: list[Kline], ctx: StrategyContext) -> Optional[Signal]:
        raise NotImplementedError
