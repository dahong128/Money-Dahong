import asyncio
from typing import Optional

import ccxt.async_support as ccxt


class ExchangeManager:
    _instance_lock = asyncio.Lock()
    _instance: Optional["ExchangeManager"] = None

    def __init__(self) -> None:
        self._client: Optional[ccxt.binance] = None
        self._initialized = False
        self._sandbox_mode: bool = True
        self._api_key: str = ""
        self._secret: str = ""

    @classmethod
    async def get_instance(cls) -> "ExchangeManager":
        if cls._instance is None:
            async with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    async def initialize(self, api_key: Optional[str], secret: Optional[str], sandbox_mode: bool = True) -> None:
        should_reinit = (
            not self._initialized
            or self._api_key != (api_key or "")
            or self._secret != (secret or "")
            or self._sandbox_mode != sandbox_mode
        )

        if not should_reinit:
            return

        if self._client is not None:
            await self._client.close()

        self._client = ccxt.binance({
            "apiKey": api_key or "",
            "secret": secret or "",
        })
        self._client.set_sandbox_mode(sandbox_mode)
        self._sandbox_mode = sandbox_mode
        self._api_key = api_key or ""
        self._secret = secret or ""
        self._initialized = True

    async def fetch_price(self, symbol: str) -> Optional[float]:
        if self._client is None:
            return None
        ticker = await self._client.fetch_ticker(symbol)
        return float(ticker.get("last")) if ticker else None

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
