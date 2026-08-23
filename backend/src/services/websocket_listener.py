"""WebSocket listener for real-time order and position updates via CCXT Pro."""

import asyncio
import logging
from decimal import Decimal
from typing import Optional
import ccxt.pro as ccxt
from sqlalchemy import select

from src.database.models import Order
from src.domain.entities.trade import OrderFillDTO
from src.repository.trade_repository import TradeRepository
from src.services.position_manager import PositionManager

logger = logging.getLogger(__name__)


class BinanceStreamListener:
    """Real-time WebSocket listener for Binance user data streams.

    Watches for order status changes via CCXT Pro's ``watch_orders()`` and
    dispatches filled-order events to the ``PositionManager``.
    """

    def __init__(
        self,
        trade_repo: TradeRepository,
        position_manager: PositionManager,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: bool = True,
    ):
        self.trade_repo = trade_repo
        self.position_manager = position_manager
        self.is_running = False
        
        self.exchange = ccxt.binanceusdm({
            'apiKey': api_key or "",
            'secret': api_secret or "",
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        if testnet:
            if hasattr(self.exchange, "enable_demo_trading"):
                self.exchange.enable_demo_trading(True)
            else:
                self.exchange.set_sandbox_mode(True)
            logger.info("Binance Listener Engine berjalan dalam mode DEMO TRADING.")
        else:
            logger.info("Binance Listener Engine berjalan dalam mode LIVE.")

    async def start(self):
        """Start the WebSocket listener loop."""
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
        """Parse a single order event from the WebSocket stream and forward fill DTO to PositionManager."""
        if not order_data or not isinstance(order_data, dict):
            return

        binance_order_id = str(order_data.get('id'))
        if not binance_order_id or binance_order_id == "None":
            return

        status = order_data.get('status')  # 'closed' (FILLED), 'canceled', etc.
        filled_qty = float(order_data.get('filled') or 0.0)
        avg_price = float(order_data.get('average') or order_data.get('price') or 0.0)
        fee_cost = float(order_data.get('fee', {}).get('cost') or 0.0)

        logger.debug(f"[WS Event] Order ID: {binance_order_id} | Status: {status} | Filled: {filled_qty}")

        # 1. Query Order dari Database menggunakan SQLAlchemy select
        order = None
        max_retries = 3
        retry_delay = 0.3

        for attempt in range(max_retries):
            stmt = select(Order).where(Order.exchange_order_id == binance_order_id)
            result = await self.trade_repo.session.execute(stmt)
            order = result.scalar_one_or_none()
            if order:
                break
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)

        if not order:
            logger.debug(f"[WS Event] Order ID {binance_order_id} not found in DB after retries. Skipping.")
            return

        # 2. Jika Order FILLED (closed), kirim OrderFillDTO ke PositionManager
        if status == "closed" or (status and status.upper() == "FILLED"):
            symbol_raw = order_data.get("symbol") or ""
            symbol = str(symbol_raw).replace("/", "").replace(":USDT", "").upper() or "BTCUSDT"
            fill_dto = OrderFillDTO(
                order_id=order.id,
                trade_id=order.trade_id,
                symbol=symbol,
                side=order.side,
                purpose=order.purpose,
                fill_price=Decimal(str(avg_price)),
                fill_qty=Decimal(str(filled_qty)),
                exchange_order_id=binance_order_id,
                client_order_id=order.client_order_id,
                fee=Decimal(str(fee_cost)),
                fee_asset="USDT",
                status="FILLED",
            )
            await self.position_manager.handle_order_fill(fill_dto)

    async def stop(self):
        """Safely close the WebSocket connection and stop the listener."""
        self.is_running = False
        try:
            await self.exchange.close()
        except Exception:
            pass
        logger.info("Binance WebSocket Listener stopped.")