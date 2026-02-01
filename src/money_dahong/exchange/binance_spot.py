from __future__ import annotations

import hmac
import time
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Any, cast
from urllib.parse import urlencode

import httpx

from money_dahong.types import Side


class BinanceApiError(RuntimeError):
    def __init__(self, *, status_code: int, payload: Any):
        super().__init__(f"Binance API error: status={status_code} payload={payload!r}")
        self.status_code = status_code
        self.payload = payload


def _normalize_value(value: Any) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def build_query_string(params: dict[str, Any]) -> str:
    items: list[tuple[str, str]] = []
    for key in sorted(params.keys()):
        value = params[key]
        if value is None:
            continue
        items.append((key, _normalize_value(value)))
    return urlencode(items)


def sign_query_string(query_string: str, api_secret: str) -> str:
    mac = hmac.new(api_secret.encode("utf-8"), query_string.encode("utf-8"), sha256)
    return mac.hexdigest()


@dataclass(frozen=True)
class Kline:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    close_time_ms: int


class BinanceSpotClient:
    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        base_url: str = "https://api.binance.com",
        timeout_seconds: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"X-MBX-APIKEY": api_key} if api_key else {},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def ping(self) -> None:
        await self._request("GET", "/api/v3/ping", signed=False, params={})

    async def server_time_ms(self) -> int:
        data = await self._request("GET", "/api/v3/time", signed=False, params={})
        return int(data["serverTime"])

    async def exchange_info(self, *, symbol: str) -> dict[str, Any]:
        data = await self._request(
            "GET",
            "/api/v3/exchangeInfo",
            signed=False,
            params={"symbol": symbol},
        )
        return cast(dict[str, Any], data)

    async def klines(self, *, symbol: str, interval: str, limit: int = 200) -> list[Kline]:
        raw = await self._request(
            "GET",
            "/api/v3/klines",
            signed=False,
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        klines: list[Kline] = []
        for row in raw:
            klines.append(
                Kline(
                    open_time_ms=int(row[0]),
                    open=Decimal(row[1]),
                    high=Decimal(row[2]),
                    low=Decimal(row[3]),
                    close=Decimal(row[4]),
                    volume=Decimal(row[5]),
                    close_time_ms=int(row[6]),
                )
            )
        return klines

    async def account(self) -> dict[str, Any]:
        data = await self._request("GET", "/api/v3/account", signed=True, params={})
        return cast(dict[str, Any], data)

    async def new_order_market(
        self,
        *,
        symbol: str,
        side: Side,
        quantity: Decimal,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": quantity,
        }
        data = await self._request("POST", "/api/v3/order", signed=True, params=params)
        return cast(dict[str, Any], data)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        signed: bool,
        params: dict[str, Any],
    ) -> Any:
        request_params = dict(params)
        if signed:
            if not self._api_secret:
                raise RuntimeError("BINANCE_API_SECRET is required for signed endpoints")
            request_params.setdefault("timestamp", int(time.time() * 1000))
            query_string = build_query_string(request_params)
            signature = sign_query_string(query_string, self._api_secret)
            request_params["signature"] = signature

        response = await self._client.request(method, path, params=request_params)
        if response.status_code >= 400:
            payload: Any
            try:
                payload = response.json()
            except Exception:
                payload = response.text
            raise BinanceApiError(status_code=response.status_code, payload=payload)
        return response.json()
