from typing import Optional

from fastapi import APIRouter, Depends, Request
import ccxt.async_support as ccxt
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.db import get_session
from app.core.logger import get_logger
from app.core.store import data_store
from app.models.system_config import SystemConfig

logger = get_logger("API")


router = APIRouter()


class ConfigPayload(BaseModel):
    binance_api_key_live: Optional[str] = None
    binance_secret_live: Optional[str] = None
    binance_api_key_sandbox: Optional[str] = None
    binance_secret_sandbox: Optional[str] = None
    sandbox_mode: Optional[bool] = None
    allowed_symbols: Optional[str] = None
    poll_interval_seconds: Optional[int] = None
    trading_enabled: Optional[bool] = None


class SymbolPayload(BaseModel):
    symbol: str


class VerifyPayload(BaseModel):
    binance_api_key_live: Optional[str] = None
    binance_secret_live: Optional[str] = None
    binance_api_key_sandbox: Optional[str] = None
    binance_secret_sandbox: Optional[str] = None
    sandbox_mode: Optional[bool] = True


async def _get_or_create_config(session: AsyncSession) -> SystemConfig:
    result = await session.execute(select(SystemConfig).where(SystemConfig.id == 1))
    config = result.scalars().first()
    if config is None:
        config = SystemConfig(id=1)
        session.add(config)
        await session.commit()
        await session.refresh(config)
    else:
        updated = False
        if config.allowed_symbols is None:
            config.allowed_symbols = "BTC/USDT,ETH/USDT,BNB/USDT"
            updated = True
        if config.poll_interval_seconds is None:
            config.poll_interval_seconds = 3
            updated = True
        if config.sandbox_mode is None:
            config.sandbox_mode = True
            updated = True
        if config.trading_enabled is None:
            config.trading_enabled = True
            updated = True
        if updated:
            session.add(config)
            await session.commit()
            await session.refresh(config)
    return config


@router.get("/api/status")
async def get_status(request: Request, session: AsyncSession = Depends(get_session)):
    config = await _get_or_create_config(session)
    allowed_list = [s.strip() for s in (config.allowed_symbols or "").split(",") if s.strip()]
    if not allowed_list:
        allowed_list = ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
    data_store["allowed_symbols"] = allowed_list
    if data_store.get("symbol") not in allowed_list:
        data_store["symbol"] = allowed_list[0]
    data_store["sandbox_mode"] = config.sandbox_mode
    data_store["poll_interval_seconds"] = config.poll_interval_seconds or 3
    data_store["trading_enabled"] = config.trading_enabled
    return {
        "status": data_store.get("status", "STOPPED"),
        "last_price": data_store.get("price"),
        "symbol": data_store.get("symbol", "BTC/USDT"),
        "allowed_symbols": data_store.get("allowed_symbols", []),
        "sandbox_mode": config.sandbox_mode,
        "poll_interval_seconds": config.poll_interval_seconds,
        "trading_enabled": config.trading_enabled,
        "has_api_key": bool(config.binance_api_key_live),
        "has_api_secret": bool(config.binance_secret_live),
        "has_live_api_key": bool(config.binance_api_key_live),
        "has_live_api_secret": bool(config.binance_secret_live),
        "has_sandbox_api_key": bool(config.binance_api_key_sandbox),
        "has_sandbox_api_secret": bool(config.binance_secret_sandbox),
    }


@router.post("/api/toggle")
async def toggle_bot(session: AsyncSession = Depends(get_session)):
    config = await _get_or_create_config(session)
    config.is_active = not config.is_active
    session.add(config)
    await session.commit()
    await session.refresh(config)
    status = "Active" if config.is_active else "Stopped"
    logger.info(f"Trading bot toggled to {status}")
    return {"status": status}


@router.post("/api/config")
async def update_config(payload: ConfigPayload, session: AsyncSession = Depends(get_session)):
    config = await _get_or_create_config(session)
    if payload.binance_api_key_live is not None:
        config.binance_api_key_live = payload.binance_api_key_live
    if payload.binance_secret_live is not None:
        config.binance_secret_live = payload.binance_secret_live
    if payload.binance_api_key_sandbox is not None:
        config.binance_api_key_sandbox = payload.binance_api_key_sandbox
    if payload.binance_secret_sandbox is not None:
        config.binance_secret_sandbox = payload.binance_secret_sandbox
    if payload.sandbox_mode is not None:
        config.sandbox_mode = payload.sandbox_mode
        data_store["sandbox_mode"] = payload.sandbox_mode
        logger.info(f"Switched to {'Sandbox' if payload.sandbox_mode else 'Live'} mode")
    if payload.allowed_symbols is not None:
        config.allowed_symbols = payload.allowed_symbols
        allowed_list = [s.strip() for s in payload.allowed_symbols.split(",") if s.strip()]
        if not allowed_list:
            allowed_list = ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
            config.allowed_symbols = ",".join(allowed_list)
        data_store["allowed_symbols"] = allowed_list
        if allowed_list and data_store.get("symbol") not in allowed_list:
            data_store["symbol"] = allowed_list[0]
        logger.info(f"Updated allowed symbols: {allowed_list}")
    if payload.poll_interval_seconds is not None:
        interval = max(1, payload.poll_interval_seconds)
        config.poll_interval_seconds = interval
        data_store["poll_interval_seconds"] = interval
        logger.info(f"Updated poll interval to {interval}s")
    if payload.trading_enabled is not None:
        config.trading_enabled = payload.trading_enabled
        data_store["trading_enabled"] = payload.trading_enabled
        logger.info(f"Trading {'enabled' if payload.trading_enabled else 'disabled'}")
    session.add(config)
    await session.commit()
    await session.refresh(config)
    allowed_list = [s.strip() for s in (config.allowed_symbols or "").split(",") if s.strip()]
    return {
        "message": "Config updated",
        "allowed_symbols": allowed_list,
        "sandbox_mode": config.sandbox_mode,
        "poll_interval_seconds": config.poll_interval_seconds,
        "trading_enabled": config.trading_enabled,
        "symbol": data_store.get("symbol"),
        "has_api_key": bool(config.binance_api_key_live),
        "has_api_secret": bool(config.binance_secret_live),
        "has_live_api_key": bool(config.binance_api_key_live),
        "has_live_api_secret": bool(config.binance_secret_live),
        "has_sandbox_api_key": bool(config.binance_api_key_sandbox),
        "has_sandbox_api_secret": bool(config.binance_secret_sandbox),
    }


@router.get("/api/logs")
async def get_logs():
    return {"logs": data_store.get("logs", [])}


@router.post("/api/symbol")
async def set_symbol(payload: SymbolPayload, session: AsyncSession = Depends(get_session)):
    config = await _get_or_create_config(session)
    allowed_list = [s.strip() for s in (config.allowed_symbols or "").split(",") if s.strip()]
    data_store["allowed_symbols"] = allowed_list
    if payload.symbol not in allowed_list:
        logger.warning(f"Attempted to switch to invalid symbol: {payload.symbol}")
        return {"error": "Symbol not allowed", "allowed": allowed_list}
    data_store["symbol"] = payload.symbol
    logger.info(f"Switched to symbol: {payload.symbol}")
    return {"symbol": payload.symbol}


@router.post("/api/verify_keys")
async def verify_keys(payload: VerifyPayload, session: AsyncSession = Depends(get_session)):
    config = await _get_or_create_config(session)
    sandbox_mode = True if payload.sandbox_mode is None else payload.sandbox_mode
    if sandbox_mode:
        if not config.binance_api_key_sandbox or not config.binance_secret_sandbox:
            logger.warning("Attempted to verify Sandbox keys but none configured")
            return {"ok": False, "error": "请先在沙盒凭证中完成配置"}
        api_key = config.binance_api_key_sandbox or ""
        secret = config.binance_secret_sandbox or ""
    else:
        api_key = payload.binance_api_key_live or config.binance_api_key_live or ""
        secret = payload.binance_secret_live or config.binance_secret_live or ""

    if not api_key or not secret:
        logger.warning("Attempted to verify keys but API key or secret is missing")
        return {"ok": False, "error": "缺少 API Key 或 Secret"}

    client = ccxt.binance({
        "apiKey": api_key,
        "secret": secret,
    })
    client.set_sandbox_mode(sandbox_mode)

    try:
        await client.fetch_balance({"recvWindow": 5000})
        logger.info(f"API key verification successful ({'Sandbox' if sandbox_mode else 'Live'})")
        return {"ok": True, "sandbox_mode": sandbox_mode}
    except Exception as exc:  # noqa: BLE001
        logger.error(f"API key verification failed: {exc}")
        return {"ok": False, "error": str(exc)}
    finally:
        await client.close()
