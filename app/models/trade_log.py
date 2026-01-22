from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class TradeLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(max_length=50)
    side: str = Field(max_length=10)
    price: float
    amount: float
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    profit: Optional[float] = Field(default=None)
