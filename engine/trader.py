import asyncio
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.db import SessionLocal
from app.core.logger import get_logger
from app.core.store import data_store
from app.models.system_config import SystemConfig
from engine.exchange import ExchangeManager

logger = get_logger("TraderBot")


class TraderBot:
    def __init__(self) -> None:
        self.last_price: Optional[float] = None
        self.last_status: str = "Stopped"

    async def _get_or_create_config(self, session: AsyncSession) -> SystemConfig:
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

    async def run_loop(self) -> None:
        exchange = await ExchangeManager.get_instance()
        while True:
            try:
                async with SessionLocal() as session:
                    config = await self._get_or_create_config(session)
                    if config.sandbox_mode:
                        api_key = config.binance_api_key_sandbox
                        secret = config.binance_secret_sandbox
                    else:
                        api_key = config.binance_api_key_live
                        secret = config.binance_secret_live
                    await exchange.initialize(
                        api_key,
                        secret,
                        config.sandbox_mode,
                    )

                    data_store["sandbox_mode"] = config.sandbox_mode
                    data_store["trading_enabled"] = config.trading_enabled
                    data_store["poll_interval_seconds"] = config.poll_interval_seconds or 3
                    allowed_list = [s.strip() for s in (config.allowed_symbols or "").split(",") if s.strip()]
                    if not allowed_list:
                        allowed_list = ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
                    data_store["allowed_symbols"] = allowed_list
                    if data_store.get("symbol") not in allowed_list:
                        data_store["symbol"] = allowed_list[0]

                    if config.is_active:
                        symbol = data_store.get("symbol", "BTC/USDT")
                        price = await exchange.fetch_price(symbol)
                        
                        # Only log if price changed or first run
                        if self.last_price != price:
                            logger.info(f"正在监控行情... {symbol} 最新价: {price}")
                            self.last_price = price
                        
                        # Only log status change
                        if self.last_status != "Active":
                            logger.info("Bot started monitoring")
                            self.last_status = "Active"

                        data_store["price"] = float(price) if price is not None else 0.0
                        data_store["status"] = "Active"
                        
                        # Add log to UI data store only if price changed significantly (optional, keeping verbose for UI)
                        if price is not None:
                            log_msg = f"{symbol} price: {price}"
                            # Simple deduplication for UI logs
                            if not data_store["logs"] or data_store["logs"][0] != log_msg:
                                data_store["logs"].insert(0, log_msg)
                                data_store["logs"] = data_store["logs"][:20]
                    else:
                        data_store["status"] = "Stopped"
                        # Only log status change
                        if self.last_status != "Stopped":
                            logger.info("机器人休眠中...")
                            self.last_status = "Stopped"
            except Exception as exc:
                self.last_status = "Error"
                data_store["status"] = "Error"
                data_store["logs"].insert(0, f"Error: {exc}")
                data_store["logs"] = data_store["logs"][:20]
                logger.error(f"Loop error: {exc}")

            sleep_for = data_store.get("poll_interval_seconds", 3) or 3
            await asyncio.sleep(max(1, int(sleep_for)))
