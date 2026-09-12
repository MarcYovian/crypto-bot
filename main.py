"""Main Application Entry Point for the Semi-Automated Binance Futures Trading Bot & Web Dashboard API.

Integrates FastAPI REST & WebSocket API, Telegram Polling Bot, Binance Stream Listener,
and APScheduler Background Cron Jobs through a decoupled Clean Architecture Lifespan Manager.
"""

import logging
import sys
import uvicorn

from config.settings import settings
from src.presentation.api.app import create_app
from src.infrastructure.bootstrap import lifespan
from src.infrastructure.di.container import ApplicationContainer, container, get_container

# Configure global logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("ccxt").setLevel(logging.WARNING)
logger = logging.getLogger("MAIN_APP")

# Instantiate FastAPI application using the decoupled Lifespan context manager
app = create_app(lifespan=lifespan)

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level=settings.LOG_LEVEL.lower(),
    )
