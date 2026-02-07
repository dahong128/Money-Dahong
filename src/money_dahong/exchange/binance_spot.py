from __future__ import annotations

import asyncio
import hmac
import time
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Any, cast
from urllib.parse import urlencode

import httpx

from money_dahong.types import Side

_DEFAULT_RECV_WINDOW_MS = 5_000
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_BASE_SECONDS = 0.5
_DEFAULT_RETRY_MAX_SECONDS = 8.0


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


def _compact_params(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None}


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
        recv_window_ms: int = _DEFAULT_RECV_WINDOW_MS,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_base_seconds: float = _DEFAULT_RETRY_BASE_SECONDS,
        retry_max_seconds: float = _DEFAULT_RETRY_MAX_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = base_url.rstrip("/")
        self._recv_window_ms = int(max(1, recv_window_ms))
        self._max_retries = int(max(0, max_retries))
        self._retry_base_seconds = float(max(0.0, retry_base_seconds))
        self._retry_max_seconds = float(max(self._retry_base_seconds, retry_max_seconds))
        self._time_offset_ms = 0
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"X-MBX-APIKEY": api_key} if api_key else {},
            transport=transport,
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

    async def klines(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list[Kline]:
        raw = await self._request(
            "GET",
            "/api/v3/klines",
            signed=False,
            params={
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
                "startTime": start_time_ms,
                "endTime": end_time_ms,
            },
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
        quantity: Decimal | None = None,
        quote_order_qty: Decimal | None = None,
    ) -> dict[str, Any]:
        if (quantity is None) == (quote_order_qty is None):
            raise ValueError("exactly one of quantity or quote_order_qty must be provided")
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
        }
        if quantity is not None:
            params["quantity"] = quantity
        if quote_order_qty is not None:
            params["quoteOrderQty"] = quote_order_qty
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
        attempt = 0
        while True:
            request_params = _compact_params(dict(params))
            if signed:
                if not self._api_secret:
                    raise RuntimeError("BINANCE_API_SECRET is required for signed endpoints")
                request_params.setdefault("recvWindow", self._recv_window_ms)
                request_params.setdefault(
                    "timestamp",
                    int(time.time() * 1000) + self._time_offset_ms,
                )
                query_string = build_query_string(request_params)
                signature = sign_query_string(query_string, self._api_secret)
                request_params["signature"] = signature

            try:
                response = await self._client.request(method, path, params=request_params)
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt >= self._max_retries:
                    raise
                await asyncio.sleep(self._retry_delay_seconds(attempt=attempt, response=None))
                attempt += 1
                continue

            if response.status_code >= 400:
                payload: Any
                try:
                    payload = response.json()
                except Exception:
                    payload = response.text

                if (
                    signed
                    and _is_timestamp_error(payload)
                    and attempt < self._max_retries
                    and await self._sync_time_offset_ms()
                ):
                    attempt += 1
                    continue

                if (
                    _should_retry_http_error(status_code=response.status_code)
                    and attempt < self._max_retries
                ):
                    await asyncio.sleep(
                        self._retry_delay_seconds(attempt=attempt, response=response)
                    )
                    attempt += 1
                    continue

                raise BinanceApiError(status_code=response.status_code, payload=payload)

            return response.json()

    async def _sync_time_offset_ms(self) -> bool:
        try:
            response = await self._client.request("GET", "/api/v3/time", params={})
            if response.status_code >= 400:
                return False
            data = response.json()
            server_ms = int(data["serverTime"])
        except Exception:
            return False
        self._time_offset_ms = server_ms - int(time.time() * 1000)
        return True

    def _retry_delay_seconds(
        self,
        *,
        attempt: int,
        response: httpx.Response | None,
    ) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    value = float(retry_after)
                    if value > 0:
                        return value
                except ValueError:
                    pass
        delay = self._retry_base_seconds * (2**attempt)
        return float(min(delay, self._retry_max_seconds))


def _is_timestamp_error(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    try:
        return int(payload.get("code", 0)) == -1021
    except (TypeError, ValueError):
        return False


def _should_retry_http_error(*, status_code: int) -> bool:
    return status_code in (418, 429) or status_code >= 500
