import asyncio
import time

import httpx

from money_dahong.exchange.binance_spot import BinanceSpotClient


def test_request_retries_on_timeout_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(200, json={"serverTime": 1234567890})

    client = BinanceSpotClient(
        api_key="",
        api_secret="",
        max_retries=1,
        retry_base_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        server_time = asyncio.run(client.server_time_ms())
    finally:
        asyncio.run(client.aclose())

    assert server_time == 1234567890
    assert calls["n"] == 2


def test_request_retries_on_5xx_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={"code": -1000, "msg": "internal error"})
        return httpx.Response(200, json={})

    client = BinanceSpotClient(
        api_key="",
        api_secret="",
        max_retries=1,
        retry_base_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        asyncio.run(client.ping())
    finally:
        asyncio.run(client.aclose())

    assert calls["n"] == 2


def test_signed_request_syncs_clock_on_timestamp_error() -> None:
    calls = {"account": 0, "time": 0}
    captured_recv_window: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/account":
            calls["account"] += 1
            captured_recv_window.append(request.url.params.get("recvWindow", ""))
            if calls["account"] == 1:
                return httpx.Response(
                    400,
                    json={
                        "code": -1021,
                        "msg": "Timestamp for this request was outside recvWindow.",
                    },
                )
            return httpx.Response(200, json={"balances": []})
        if request.url.path == "/api/v3/time":
            calls["time"] += 1
            return httpx.Response(200, json={"serverTime": int(time.time() * 1000) + 2000})
        raise AssertionError(f"unexpected path: {request.url.path}")

    client = BinanceSpotClient(
        api_key="k",
        api_secret="s",
        max_retries=2,
        retry_base_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        data = asyncio.run(client.account())
    finally:
        asyncio.run(client.aclose())

    assert data["balances"] == []
    assert calls["account"] == 2
    assert calls["time"] == 1
    assert "5000" in captured_recv_window


def test_klines_passes_time_window_params() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["startTime"] = request.url.params.get("startTime", "")
        captured["endTime"] = request.url.params.get("endTime", "")
        return httpx.Response(200, json=[])

    client = BinanceSpotClient(
        api_key="",
        api_secret="",
        transport=httpx.MockTransport(handler),
    )
    try:
        asyncio.run(
            client.klines(
                symbol="ETHUSDT",
                interval="1m",
                limit=10,
                start_time_ms=1_700_000_000_000,
                end_time_ms=1_700_001_000_000,
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert captured["startTime"] == "1700000000000"
    assert captured["endTime"] == "1700001000000"


def test_klines_omits_empty_time_window_params() -> None:
    captured: dict[str, str | bool] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["has_start_time"] = "startTime" in request.url.params
        captured["has_end_time"] = "endTime" in request.url.params
        return httpx.Response(200, json=[])

    client = BinanceSpotClient(
        api_key="",
        api_secret="",
        transport=httpx.MockTransport(handler),
    )
    try:
        asyncio.run(
            client.klines(
                symbol="ETHUSDT",
                interval="1m",
                limit=10,
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert captured["has_start_time"] is False
    assert captured["has_end_time"] is False
