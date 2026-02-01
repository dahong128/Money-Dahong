from __future__ import annotations

from decimal import Decimal


def ema_series(values: list[Decimal], period: int) -> list[Decimal]:
    if period <= 0:
        raise ValueError("period must be > 0")
    if not values:
        return []
    k = Decimal(2) / Decimal(period + 1)
    ema: list[Decimal] = [values[0]]
    for value in values[1:]:
        ema.append((value * k) + (ema[-1] * (Decimal(1) - k)))
    return ema


def sma(values: list[Decimal], period: int) -> Decimal:
    if period <= 0:
        raise ValueError("period must be > 0")
    if len(values) < period:
        raise ValueError("not enough values")
    return sum(values[-period:]) / Decimal(period)
