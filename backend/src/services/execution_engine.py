"""Async order execution engine for Binance Futures via CCXT Pro."""

import asyncio
import math
import logging
from typing import Optional, List
from dataclasses import dataclass
import ccxt.pro as ccxt

from src.services.precision_filter import PrecisionFilterService, SymbolInfo
from src.services.risk_calculator import RiskCalculationResult, RiskCalculatorService
from src.repository.trade_repository import TradeRepository

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResponse:
    """Result of a trade execution attempt.

    Attributes:
        success: Whether the execution succeeded.
        trade_id: Database ID of the trade.
        execution_type: ``MARKET`` or ``LIMIT``.
        entry_order_id: Binance order ID of the entry order.
        sl_order_id: Binance order ID of the stop-loss order (``None`` for LIMIT).
        tp_order_ids: List of Binance order IDs for TP orders.
        error_message: Error detail if ``success`` is False.
        actual_entry_price: Actual fill price retrieved from Binance.
        actual_margin: Actual margin used on the exchange.
        actual_sl_loss: Calculated loss at stop-loss using actual entry price.
    """
    success: bool
    trade_id: int
    execution_type: str = "UNKNOWN"
    entry_order_id: Optional[str] = None
    sl_order_id: Optional[str] = None
    tp_order_ids: Optional[List[str]] = None
    error_message: Optional[str] = None
    actual_entry_price: Optional[float] = None
    actual_margin: Optional[float] = None
    actual_sl_loss: Optional[float] = None


class BinanceExecutionEngine:
    """Async execution engine that submits orders to Binance Futures via CCXT Pro.

    Features:
    - Market-state validation (guard against SL/TP being already triggered).
    - Dual execution: market order when price is near entry, limit order otherwise.
    - Automatic leverage and margin-mode setup.
    - SL and TP order placement (for market entries) or deferred (for limit entries).
    - Actual fill-price and margin retrieval from Binance positions.
    """

    def __init__(
        self,
        trade_repo: Optional[TradeRepository] = None,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        testnet: bool = True,
    ):
        self.trade_repo = trade_repo
        self.api_key = api_key or ""
        self.secret_key = secret_key or ""
        self.testnet = testnet

        self.exchange = ccxt.binanceusdm({
            'apiKey': self.api_key,
            'secret': self.secret_key,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True,
            }
        })

        if self.testnet:
            if hasattr(self.exchange, "enable_demo_trading"):
                self.exchange.enable_demo_trading(True)
            else:
                self.exchange.set_sandbox_mode(True)
            logger.info("BinanceExecutionEngine running in TESTNET mode (Sandbox).")
        else:
            logger.info("BinanceExecutionEngine running in LIVE mode (Real Market).")

    def reconfigure(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        testnet: Optional[bool] = None,
    ) -> None:
        """Dynamically update execution engine credentials and network mode."""
        if api_key is not None:
            self.api_key = api_key
            self.exchange.apiKey = api_key
        if secret_key is not None:
            self.secret_key = secret_key
            self.exchange.secret = secret_key
        if testnet is not None:
            self.testnet = testnet
            if self.testnet:
                if hasattr(self.exchange, "enable_demo_trading"):
                    self.exchange.enable_demo_trading(True)
                else:
                    self.exchange.set_sandbox_mode(True)
                logger.info("BinanceExecutionEngine switched to TESTNET mode.")
            else:
                if hasattr(self.exchange, "enable_demo_trading"):
                    self.exchange.enable_demo_trading(False)
                else:
                    self.exchange.set_sandbox_mode(False)
                logger.info("BinanceExecutionEngine switched to LIVE mode.")

    async def close(self) -> None:
        """Alias for close_connection."""
        await self.close_connection()

    async def fetch_balance(self) -> dict:
        """Fetch the USDT balance from the Binance Futures account.

        Returns:
            A dict with the shape ``{"USDT": {"total": …, "free": …, "used": …}}``.
        """
        balance = await self.exchange.fetch_balance()
        return {
            "USDT": {
                "total": float(balance.get('USDT', {}).get('total', 0.0)),
                "free": float(balance.get('USDT', {}).get('free', 0.0)),
                "used": float(balance.get('USDT', {}).get('used', 0.0)),
            }
        }

    async def fetch_positions(self, symbols: List[str]) -> list:
        """Fetch open positions from Binance for the given symbols."""
        return await self.exchange.fetch_positions(symbols)

    async def cancel_all_orders(self, symbol: str) -> None:
        """Cancel all open orders for a symbol on Binance."""
        await self.exchange.cancel_all_orders(symbol)

    async def fetch_symbol_info(self, symbol: str) -> SymbolInfo:
        """Build a ``SymbolInfo`` dataclass from Binance exchange info for the given symbol.

        Retrieves price precision, tick size, LOT_SIZE limits, min_notional,
        and MARKET_LOT_SIZE max_qty.
        """
        await self.exchange.load_markets()
        market = self.exchange.market(symbol)

        price_precision = market['precision']['price']
        if isinstance(price_precision, (int, float)) and 0 < price_precision < 1:
            tick_size = float(price_precision)
        else:
            tick_size = 10 ** (-int(price_precision)) if isinstance(price_precision, (int, float)) else 0.01

        max_qty = float(market['limits']['amount']['max'] or 99999999.0)
        for f in market.get('info', {}).get('filters', []):
            if f.get('filterType') == 'MARKET_LOT_SIZE' and f.get('maxQty'):
                market_max = float(f['maxQty'])
                if market_max > 0:
                    max_qty = min(max_qty, market_max)

        return SymbolInfo(
            symbol=symbol,
            price_precision=int(market['precision']['price']) if isinstance(market['precision']['price'], int) else int(round(-math.log10(tick_size))),
            qty_precision=int(market['precision']['amount']) if isinstance(market['precision']['amount'], int) else 3,
            tick_size=tick_size,
            step_size=float(market['limits']['amount']['min'] or 0.001),
            min_qty=float(market['limits']['amount']['min'] or 0.001),
            min_notional=float(market['limits']['cost']['min'] or 5.0),
            max_qty=max_qty
        )

    async def validate_signal_market_state(
        self,
        current_price: float,
        entry_price: float,
        sl_price: float,
        tp1_price: Optional[float],
        side: str
    ) -> tuple[bool, str]:
        """Validate whether the signal is still executable given the current market price.

        Rejects if:
        - For BUY: current price is at or below SL (already stopped out).
        - For BUY: current price is at or above TP1 (already taken profit).
        - For SELL: current price is at or above SL (already stopped out).
        - For SELL: current price is at or below TP1 (already taken profit).

        Returns:
            ``(True, "VALID")`` or ``(False, reason_message)``.
        """
        if side == "BUY":  # LONG
            if current_price <= sl_price:
                return False, f"REJECTED: Harga market (${current_price}) sudah menembus/di bawah SL (${sl_price})"
            if tp1_price and current_price >= tp1_price:
                return False, f"EXPIRED: Harga market (${current_price}) sudah mencapai/melewati TP1 (${tp1_price})"

        elif side == "SELL":  # SHORT
            if current_price >= sl_price:
                return False, f"REJECTED: Harga market (${current_price}) sudah menembus/di atas SL (${sl_price})"
            if tp1_price and current_price <= tp1_price:
                return False, f"EXPIRED: Harga market (${current_price}) sudah mencapai/melewati TP1 (${tp1_price})"

        return True, "VALID"

    async def execute_trade_pipeline(
        self,
        trade_id: int,
        symbol: str,
        side: str,                  # 'BUY' atau 'SELL'
        risk_res: RiskCalculationResult,
        tp_prices: List[float],
        leverage: int = 20,
        symbol_info: Optional[SymbolInfo] = None
    ) -> ExecutionResponse:
        """
        Menjalankan alur eksekusi lengkap dengan Pre-Validation & Dual Execution (Market vs Limit).
        """
        try:
            # 1. Fetch Ticker & Pre-Validation Market State
            ticker = await self.exchange.fetch_ticker(symbol)
            current_price = float(ticker['last'])

            entry_price_flt = float(risk_res.entry_price)
            sl_price_flt = float(risk_res.stop_loss_price)
            pos_size_flt = float(risk_res.position_size)

            tp1 = tp_prices[0] if tp_prices else None
            is_valid, validation_msg = await self.validate_signal_market_state(
                current_price=current_price,
                entry_price=entry_price_flt,
                sl_price=sl_price_flt,
                tp1_price=tp1,
                side=side
            )

            if not is_valid:
                logger.warning(f"[Trade #{trade_id}] {validation_msg}")
                if self.trade_repo:
                    await self.trade_repo.update_trade_status(trade_id, "CANCELLED")
                    await self.trade_repo.log_event(trade_id, "FORCE_CLOSE", payload_json=f'{{"reason": "{validation_msg}"}}')
                return ExecutionResponse(success=False, trade_id=trade_id, error_message=validation_msg)

            # 2. Logika Toleransi Harga 0.2% untuk Menentukan Market vs Limit
            TOLERANCE_PCT = 0.002
            tolerance_price = entry_price_flt * TOLERANCE_PCT

            use_market_order = False
            if side == "BUY":
                if current_price <= entry_price_flt + tolerance_price:
                    use_market_order = True
            elif side == "SELL":
                if current_price >= entry_price_flt - tolerance_price:
                    use_market_order = True

            execution_type_str = "MARKET" if use_market_order else "LIMIT"

            # Hitung Ulang Risk & Position Size khusus MARKET Order menggunakan current_price terkini
            final_position_size = pos_size_flt
            if use_market_order:
                if not symbol_info:
                    symbol_info = await self.fetch_symbol_info(symbol)

                recalculated_risk = RiskCalculatorService.calculate_position(
                    daily_risk_amount=risk_res.risk_amount,
                    entry_price=current_price,
                    stop_loss_price=risk_res.stop_loss_price,
                    side=side,
                    max_leverage=leverage,
                    symbol_info=symbol_info
                )
                if recalculated_risk.is_valid and recalculated_risk.position_size > 0:
                    final_position_size = recalculated_risk.position_size
                    logger.info(f"[Trade #{trade_id}] MARKET Order Size Recalculated: {risk_res.position_size} -> {final_position_size} (Entry: {current_price})")

            # 3. Setup Account Leverage & Margin Type
            await self._setup_account_position(symbol, leverage)

            entry_side = 'buy' if side == 'BUY' else 'sell'
            exit_side = 'sell' if side == 'BUY' else 'buy'

            # 4. Kirim Order Entry (dengan Retry untuk RateLimit & Network Error)
            logger.info(f"[Trade #{trade_id}] Sending {execution_type_str} Entry Order {side} {final_position_size} {symbol}")

            async def _create_order_with_retry(**kwargs):
                for attempt in range(2):
                    try:
                        return await self.exchange.create_order(**kwargs)
                    except (ccxt.RateLimitExceeded, ccxt.NetworkError) as err:
                        if attempt == 0:
                            logger.warning(f"Binance transient network/ratelimit error ({err}). Retrying in 1s...")
                            await asyncio.sleep(1)
                        else:
                            raise err

            if use_market_order:
                entry_order = await _create_order_with_retry(
                    symbol=symbol,
                    type='market',
                    side=entry_side,
                    amount=final_position_size
                )
            else:
                entry_order = await _create_order_with_retry(
                    symbol=symbol,
                    type='limit',
                    side=entry_side,
                    amount=final_position_size,
                    price=entry_price_flt,
                    params={'timeInForce': 'GTC'}
                )
                
            entry_order_id_str = str(entry_order['id'])

            # Catat Entry Order ke Database
            if self.trade_repo:
                await self.trade_repo.create_order(
                    trade_id=trade_id,
                    purpose="ENTRY",
                    order_type=execution_type_str,
                    side=side,
                    qty=final_position_size,
                    price=entry_price_flt,
                    binance_order_id=entry_order_id_str
                )

            sl_order_id = None
            tp_order_ids = []

            # 5. Jika MARKET Order: Tunggu Posisi Aktif -> Pasang SL & TP Sekarang Juga
            if use_market_order:
                await self._wait_position_active(symbol)

                if self.trade_repo:
                    await self.trade_repo.update_trade_status(trade_id, "OPEN")

                # Batalkan open order terkait symbol ini sebelum pasang SL (mencegah duplikasi SL/TP)
                try:
                    await self.exchange.cancel_all_orders(symbol)
                except Exception as e:
                    logger.debug(f"Cancel open orders note [{symbol}]: {e}")

                # Pasang Stop Loss
                sl_order = await self.exchange.create_order(
                    symbol=symbol,
                    type='STOP_MARKET',
                    side=exit_side,
                    amount=final_position_size,
                    params={
                        'stopPrice': sl_price_flt,
                        'closePosition': True  # Specific for Binance USDT-M STOP_MARKET
                    }
                )
                sl_order_id = str(sl_order['id'])

                if self.trade_repo:
                    await self.trade_repo.create_order(
                        trade_id=trade_id,
                        purpose="SL",
                        order_type="STOP_MARKET",
                        side=exit_side.upper(),
                        qty=final_position_size,
                        price=sl_price_flt,
                        binance_order_id=sl_order_id
                    )

                # Pasang Multiple TP Orders
                if tp_prices and symbol_info:
                    raw_tp_qty = final_position_size / len(tp_prices)
                    tp_qty = PrecisionFilterService.format_qty(raw_tp_qty, symbol_info)

                    for idx, tp_price in enumerate(tp_prices, 1):
                        purpose_name = f"TP{idx}"
                        clean_tp_price = PrecisionFilterService.format_price(tp_price, symbol_info)
                        
                        tp_order = await self.exchange.create_order(
                            symbol=symbol,
                            type='TAKE_PROFIT_MARKET',
                            side=exit_side,
                            amount=tp_qty,
                            params={
                                'stopPrice': clean_tp_price,
                                'reduceOnly': True
                            }
                        )
                        tp_order_id = str(tp_order['id'])
                        tp_order_ids.append(tp_order_id)

                        if self.trade_repo:
                            await self.trade_repo.create_order(
                                trade_id=trade_id,
                                purpose=purpose_name,
                                order_type="TAKE_PROFIT_MARKET",
                                side=exit_side.upper(),
                                qty=tp_qty,
                                price=clean_tp_price,
                                binance_order_id=tp_order_id
                            )

            else:
                # Jika LIMIT Order: Tunda SL & TP (Nanti dipasang oleh WebSocket Stream Listener ketika Entry FILLED)
                if self.trade_repo:
                    await self.trade_repo.update_trade_status(trade_id, "WAITING_ENTRY")

            # 6. Ambil Data Realita Binance (Actual Fill Price, Margin, dan Potensi Loss SL)
            actual_entry_price = entry_price_flt
            actual_margin = float(risk_res.required_margin)
            actual_sl_loss = float(risk_res.risk_amount)

            try:
                positions = await self.exchange.fetch_positions([symbol])
                for pos in positions:
                    entry_p = float(pos.get('entryPrice') or pos.get('avgPrice') or 0.0)
                    initial_margin = float(pos.get('initialMargin') or pos.get('maintMargin') or 0.0)
                    if entry_p > 0:
                        actual_entry_price = entry_p
                        actual_sl_loss = abs(actual_entry_price - sl_price_flt) * final_position_size
                        if initial_margin > 0:
                            actual_margin = initial_margin
                        else:
                            actual_margin = (actual_entry_price * final_position_size) / leverage
                        break
            except Exception as e:
                logger.debug(f"Failed to fetch actual position stats: {e}")

            if self.trade_repo:
                await self.trade_repo.log_event(
                    trade_id, 
                    "ENTRY", 
                    payload_json=f'{{"entry_order_id": "{entry_order_id_str}", "type": "{execution_type_str}", "actual_entry": {actual_entry_price}}}'
                )

            return ExecutionResponse(
                success=True,
                trade_id=trade_id,
                execution_type=execution_type_str,
                entry_order_id=entry_order_id_str,
                sl_order_id=sl_order_id,
                tp_order_ids=tp_order_ids,
                actual_entry_price=actual_entry_price,
                actual_margin=actual_margin,
                actual_sl_loss=actual_sl_loss
            )

        except Exception as e:
            logger.error(f"[Trade #{trade_id}] Execution Failed: {str(e)}")
            if self.trade_repo:
                await self.trade_repo.update_trade_status(trade_id, "CANCELLED")
                await self.trade_repo.log_event(trade_id, "FORCE_CLOSE", payload_json=f'{{"error": "{str(e)}"}}')

            return ExecutionResponse(
                success=False,
                trade_id=trade_id,
                error_message=str(e)
            )

    async def _setup_account_position(self, symbol: str, leverage: int):
        """Mengeset Leverage dan Margin Type (ISOLATED)."""
        try:
            await self.exchange.set_margin_mode('ISOLATED', symbol)
        except Exception as e:
            logger.debug(f"Margin mode setup note [{symbol}]: {e}")

        try:
            await self.exchange.set_leverage(leverage, symbol)
        except Exception as e:
            logger.warning(f"Leverage setup note [{symbol}]: {e}")

    async def _wait_position_active(self, symbol: str, max_attempts: int = 5):
        """Loop verifikasi singkat untuk memastikan posisi di Binance aktif (positionAmt != 0)."""
        for _ in range(max_attempts):
            await asyncio.sleep(0.5)
            try:
                positions = await self.exchange.fetch_positions([symbol])
                for pos in positions:
                    if float(pos.get('contracts', 0) or pos.get('amount', 0)) != 0:
                        return
            except Exception as e:
                logger.debug(f"Waiting position check error: {e}")

    async def close_connection(self):
        """Menutup koneksi."""
        if self.exchange:
            await self.exchange.close()