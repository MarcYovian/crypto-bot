"""WebSocket listener for real-time order and position updates via CCXT Pro."""

import asyncio
import logging
import ccxt.pro as ccxt
from sqlalchemy import select

from config.settings import settings
from src.database.models import Trade, Order
from src.repository.trade_repository import TradeRepository
from src.services.position_manager import PositionManager

logger = logging.getLogger(__name__)


class BinanceStreamListener:
    """Real-time WebSocket listener for Binance user data streams.

    Watches for order status changes via CCXT Pro's ``watch_orders()`` and
    dispatches filled-order events to the ``PositionManager``.
    """

    def __init__(self, trade_repo: TradeRepository, position_manager: PositionManager):
        self.trade_repo = trade_repo
        self.position_manager = position_manager
        self.is_running = False
        
        self.exchange = ccxt.binanceusdm({
            'apiKey': settings.BINANCE_API_KEY,
            'secret': settings.BINANCE_API_SECRET,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        if settings.BINANCE_TESTNET:
            self.exchange.enable_demo_trading(True)
            logger.info("Binance Listener Engine berjalan dalam mode DEMO TRADING.")
        else:
            logger.info("Binance Listener Engine berjalan dalam mode LIVE.")

    async def start(self):
        """Start the WebSocket listener loop.

        Continuously watches for order updates via CCXT Pro.  On connection
        errors it waits 5 seconds before reconnecting.
        """
        self.is_running = True
        logger.info("Starting Binance Listener Engine...")

        while self.is_running:
            try:
                orders = await self.exchange.watch_orders()
                for order_data in orders:
                    await self._process_ws_order_event(order_data)
            except Exception as e:
                logger.error(f"WebSocket Listener Error: {e}")
                await asyncio.sleep(5)

    async def _process_ws_order_event(self, order_data: dict):
        """Parse a single order event from the WebSocket stream and update DB state.

        For filled (``closed``) orders the method also records the execution
        fill and forwards the event to :meth:`PositionManager.handle_order_fill`.
        """
        binance_order_id = str(order_data.get('id'))
        status = order_data.get('status')  # 'closed' (FILLED), 'canceled', dll.
        filled_qty = float(order_data.get('filled') or 0.0)
        avg_price = float(order_data.get('average') or order_data.get('price') or 0.0)

        logger.debug(f"[WS Event] Order ID: {binance_order_id} | Status: {status} | Filled: {filled_qty}")

        # 1. Query Order dari Database menggunakan SQLAlchemy select (dengan Retry jika terjadi Race Condition)
        order = None
        max_retries = 3
        retry_delay = 0.3

        for attempt in range(max_retries):
            stmt = select(Order).where(Order.binance_order_id == binance_order_id)
            result = await self.trade_repo.session.execute(stmt)
            order = result.scalar_one_or_none()
            if order:
                break
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)

        if not order:
            logger.debug(f"[WS Event] Order ID {binance_order_id} not found in DB after retries. Skipping.")
            return

        trade = await self.trade_repo.session.get(Trade, order.trade_id)
        if not trade:
            return

        # 2. Update status order di DB (Mapping CCXT status ke constraint database SQLite)
        status_upper = status.upper() if status else "NEW"
        if status == "closed":
            db_status = "FILLED"
        elif status == "open":
            db_status = "NEW"
        elif status_upper in ("NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED", "REJECTED"):
            db_status = status_upper
        else:
            db_status = "NEW"

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
        """Safely close the WebSocket connection and stop the listener."""
        self.is_running = False
        await self.exchange.close()
        logger.info("Binance WebSocket Listener stopped.")