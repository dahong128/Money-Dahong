from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

Side = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class Signal:
    side: Side
    reason: str


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Side
    quantity: Decimal
    order_type: Literal["MARKET"] = "MARKET"
