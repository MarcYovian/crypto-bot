# src/services/websocket_listener.py
import asyncio
import logging
from sqlalchemy import select
import ccxt.pro as ccxt

from pydantic_settings import BaseSettings, SettingsConfigDict


class StreamSettings(BaseSettings):
    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    BINANCE_TESTNET: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = StreamSettings()

from src.repository.trade_repository import TradeRepository
from src.services.position_manager import PositionManager
from src.database.models import Trade, Order

logger = logging.getLogger(__name__)


class BinanceStreamListener:
    """
    WebSocket Stream Listener untuk mendengarkan perubahan status Order & Posisi
    secara real-time (User Data Stream).
    """

    def __init__(self, trade_repo: TradeRepository, position_manager: PositionManager):
        self.trade_repo = trade_repo
        self.position_manager = position_manager
        self.is_running = False
        
        if settings.BINANCE_TESTNET:
            from binance.client import Client as LegacyBinanceClient
            self.use_legacy = True
            self.legacy_client = LegacyBinanceClient(
                settings.BINANCE_API_KEY,
                settings.BINANCE_API_SECRET,
                testnet=True,
                requests_params={'timeout': 30}
            )
            self.exchange = None
        else:
            self.use_legacy = False
            self.legacy_client = None
            self.exchange = ccxt.binanceusdm({
                'apiKey': settings.BINANCE_API_KEY,
                'secret': settings.BINANCE_API_SECRET,
                'enableRateLimit': True,
                'options': {'defaultType': 'future'}
            })

    async def start(self):
        """Memulai loop pembacaan stream WebSocket / Polling."""
        self.is_running = True
        logger.info("📡 Starting Binance Listener Engine...")

        while self.is_running:
            try:
                if self.use_legacy:
                    # Pada Mode Testnet / Legacy: Polling check order & position update
                    await asyncio.sleep(5)
                else:
                    # Watch orders stream via CCXT Pro
                    orders = await self.exchange.watch_orders()
                    for order_data in orders:
                        await self._process_ws_order_event(order_data)
            except Exception as e:
                logger.error(f"WebSocket Listener Error: {e}")
                await asyncio.sleep(5)  # Reconnect delay jika koneksi terputus

    async def _process_ws_order_event(self, order_data: dict):
        """
        Handler parsing data event order dari WebSocket.
        """
        binance_order_id = str(order_data.get('id'))
        status = order_data.get('status')  # 'closed' (FILLED), 'canceled', dll.
        filled_qty = float(order_data.get('filled') or 0.0)
        avg_price = float(order_data.get('average') or order_data.get('price') or 0.0)

        logger.debug(f"[WS Event] Order ID: {binance_order_id} | Status: {status} | Filled: {filled_qty}")

        # 1. Query Order dari Database menggunakan SQLAlchemy select
        stmt = select(Order).where(Order.binance_order_id == binance_order_id)
        result = await self.trade_repo.session.execute(stmt)
        order = result.scalar_one_or_none()

        if not order:
            return  # Order bukan milik bot ini

        trade = await self.trade_repo.session.get(Trade, order.trade_id)
        if not trade:
            return

        # 2. Update status order di DB
        db_status = "FILLED" if status == "closed" else status.upper()
        await self.trade_repo.update_order_status(binance_order_id, db_status, filled_qty=filled_qty)

        # 3. Jika Order FILLED, rekam Execution & pemicu PositionManager
        if status == "closed":
            await self.trade_repo.record_execution(
                order_id=order.id,
                trade_id=trade.id,
                price=avg_price,
                qty=filled_qty,
                commission=float(order_data.get('fee', {}).get('cost') or 0.0)
            )

            # Teruskan ke PositionManager
            await self.position_manager.handle_order_fill(
                trade=trade,
                filled_order=order,
                fill_price=avg_price,
                fill_qty=filled_qty
            )

    async def stop(self):
        """Menutup koneksi WebSocket secara aman."""
        self.is_running = False
        await self.exchange.close()
        logger.info("🛑 Binance WebSocket Listener Stopped.")