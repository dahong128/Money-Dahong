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
    # Binance MARKET BUY supports either `quantity` (base asset qty)
    # or `quoteOrderQty` (quote notional).
    # We use `quote_order_qty` for sizing by USDT notional.
    quantity: Decimal | None = None
    quote_order_qty: Decimal | None = None
    order_type: Literal["MARKET"] = "MARKET"
