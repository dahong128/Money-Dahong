import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.api.routes import router
from app.core.db import init_db
from app.core.logger import EndpointFilter, get_logger
from engine.trader import TraderBot

logger = get_logger("Main")


trader_bot = TraderBot()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Suppress uvicorn access logs for polling endpoints
    logging.getLogger("uvicorn.access").addFilter(EndpointFilter("/api/status"))

    logger.info("Starting Money-Dahong...")
    await init_db()
    logger.info("Database initialized")
    app.state.trader_bot = trader_bot
    task = asyncio.create_task(trader_bot.run_loop())
    app.state.trader_task = task
    logger.info("Trading bot task started")
    try:
        yield
    finally:
        logger.info("Shutting down...")
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        logger.info("Money-Dahong stopped")


app = FastAPI(lifespan=lifespan)

templates = Jinja2Templates(directory="app/templates")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/trading", response_class=HTMLResponse)
async def trading(request: Request):
    return templates.TemplateResponse("trading.html", {"request": request})


@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})
