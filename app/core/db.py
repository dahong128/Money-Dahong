from collections.abc import AsyncGenerator

from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


DATABASE_URL = "sqlite+aiosqlite:///titan_quant.db"

engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


async def init_db() -> None:
    """Create database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        result = await conn.exec_driver_sql("PRAGMA table_info('systemconfig')")
        existing_columns = {row[1] for row in result.fetchall()}

        migrations: list[tuple[str, str]] = []
        if "binance_api_key_live" not in existing_columns:
            migrations.append(("binance_api_key_live", "TEXT"))
        if "binance_secret_live" not in existing_columns:
            migrations.append(("binance_secret_live", "TEXT"))
        if "binance_api_key_sandbox" not in existing_columns:
            migrations.append(("binance_api_key_sandbox", "TEXT"))
        if "binance_secret_sandbox" not in existing_columns:
            migrations.append(("binance_secret_sandbox", "TEXT"))
        if "sandbox_mode" not in existing_columns:
            migrations.append(("sandbox_mode", "INTEGER NOT NULL DEFAULT 1"))
        if "allowed_symbols" not in existing_columns:
            migrations.append(("allowed_symbols", "TEXT DEFAULT 'BTC/USDT,ETH/USDT,BNB/USDT'"))
        if "poll_interval_seconds" not in existing_columns:
            migrations.append(("poll_interval_seconds", "INTEGER NOT NULL DEFAULT 3"))
        if "trading_enabled" not in existing_columns:
            migrations.append(("trading_enabled", "INTEGER NOT NULL DEFAULT 1"))

        for column_name, ddl in migrations:
            await conn.exec_driver_sql(
                f"ALTER TABLE systemconfig ADD COLUMN {column_name} {ddl}"
            )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session."""
    async with SessionLocal() as session:
        yield session
