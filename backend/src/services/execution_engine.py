# src/services/execution_engine.py
import asyncio
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import ccxt.pro as ccxt

from pydantic_settings import BaseSettings, SettingsConfigDict


class ExecutionSettings(BaseSettings):
    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    BINANCE_TESTNET: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = ExecutionSettings()
from src.services.precision_filter import PrecisionFilterService, SymbolInfo
from src.services.risk_calculator import RiskCalculationResult
from src.repository.trade_repository import TradeRepository

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResponse:
    success: bool
    trade_id: int
    execution_type: str = "UNKNOWN"  # "MARKET" atau "LIMIT"
    entry_order_id: Optional[str] = None
    sl_order_id: Optional[str] = None
    tp_order_ids: Optional[List[str]] = None
    error_message: Optional[str] = None


class BinanceExecutionEngine:
    """
    Engine Eksekusi Binance Futures Async Modern.
    Mendukung validasi Market State (TP1/SL Guard), Dual Execution (Market vs Limit Order),
    Handling Margin Exception, serta Precision Format.
    """

    def __init__(self, trade_repo: Optional[TradeRepository] = None):
        self.trade_repo = trade_repo
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
                'options': {
                    'defaultType': 'future',
                }
            })

    async def fetch_balance(self) -> dict:
        """Mengambil saldo akun Binance (Mendukung Legacy python-binance & CCXT)."""
        if self.use_legacy:
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(None, self.legacy_client.futures_account)
            # Map respon python-binance ke format dict standar (USDT balance)
            usdt_total = float(res.get("totalWalletBalance", 0.0))
            usdt_free = float(res.get("availableBalance", 0.0))
            usdt_used = float(res.get("totalInitialMargin", 0.0))
            return {
                "USDT": {
                    "total": usdt_total,
                    "free": usdt_free,
                    "used": usdt_used
                }
            }
        else:
            return await self.exchange.fetch_balance()

    async def fetch_positions(self, symbols: List[str]) -> list:
        """Mengambil posisi terbuka di Binance (Mendukung Legacy & CCXT)."""
        if self.use_legacy:
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(None, self.legacy_client.futures_position_information)
            # Map respon python-binance ke format list posisi standar
            filtered = []
            for p in res:
                if p.get('symbol') in symbols:
                    amt = float(p.get('positionAmt', 0.0))
                    filtered.append({
                        'symbol': p.get('symbol'),
                        'contracts': abs(amt),
                        'positionAmt': amt
                    })
            return filtered
        else:
            return await self.exchange.fetch_positions(symbols)

    async def cancel_all_orders(self, symbol: str) -> None:
        """Membatalkan semua open orders untuk simbol terkait."""
        if self.use_legacy:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: self.legacy_client.futures_cancel_all_open_orders(symbol=symbol))
        else:
            await self.exchange.cancel_all_orders(symbol)
        """Mengambil data precision filter dan min notional dari Exchange Info."""
        if self.use_legacy:
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(None, self.legacy_client.futures_exchange_info)
            for s in info['symbols']:
                if s['symbol'] == symbol:
                    price_precision = s['pricePrecision']
                    qty_precision = s['quantityPrecision']
                    tick_size = 0.01
                    step_size = 0.001
                    min_qty = 0.001
                    max_qty = 99999999.0
                    min_notional = 5.0
                    for f in s['filters']:
                        if f['filterType'] == 'PRICE_FILTER':
                            tick_size = float(f['tickSize'])
                        elif f['filterType'] in ['LOT_SIZE', 'MARKET_LOT_SIZE']:
                            step_size = float(f.get('stepSize', step_size))
                            min_qty = float(f.get('minQty', min_qty))
                            if 'maxQty' in f:
                                max_qty = min(max_qty, float(f['maxQty']))
                        elif f['filterType'] == 'MIN_NOTIONAL':
                            min_notional = float(f.get('notional', 5.0))
                    return SymbolInfo(
                        symbol=symbol,
                        price_precision=price_precision,
                        qty_precision=qty_precision,
                        tick_size=tick_size,
                        step_size=step_size,
                        min_qty=min_qty,
                        min_notional=min_notional,
                        max_qty=max_qty
                    )
            # Default fallback
            return SymbolInfo(symbol=symbol, price_precision=2, qty_precision=3, tick_size=0.01, step_size=0.001, min_qty=0.001, min_notional=5.0, max_qty=99999999.0)
        else:
            await self.exchange.load_markets()
            market = self.exchange.market(symbol)
            return SymbolInfo(
                symbol=symbol,
                price_precision=market['precision']['price'],
                qty_precision=market['precision']['amount'],
                tick_size=float(market['limits']['price']['min'] or 0.01),
                step_size=float(market['limits']['amount']['min'] or 0.001),
                min_qty=float(market['limits']['amount']['min'] or 0.001),
                min_notional=float(market['limits']['cost']['min'] or 5.0)
            )

    async def validate_signal_market_state(
        self,
        current_price: float,
        entry_price: float,
        sl_price: float,
        tp1_price: Optional[float],
        side: str
    ) -> tuple[bool, str]:
        """
        Memvalidasi apakah sinyal masih layak dieksekusi berdasarkan harga pasar terkini.
        Mencegah eksekusi jika SL sudah tertembus atau TP1 sudah tercapai.
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
            if self.use_legacy:
                loop = asyncio.get_running_loop()
                ticker_res = await loop.run_in_executor(None, lambda: self.legacy_client.futures_symbol_ticker(symbol=symbol))
                current_price = float(ticker_res['price'])
            else:
                ticker = await self.exchange.fetch_ticker(symbol)
                current_price = float(ticker['last'])

            tp1 = tp_prices[0] if tp_prices else None
            is_valid, validation_msg = await self.validate_signal_market_state(
                current_price=current_price,
                entry_price=risk_res.entry_price,
                sl_price=risk_res.stop_loss_price,
                tp1_price=tp1,
                side=side
            )

            if not is_valid:
                logger.warning(f"[Trade #{trade_id}] {validation_msg}")
                await self.trade_repo.update_trade_status(trade_id, "CANCELLED")
                await self.trade_repo.log_event(trade_id, "FORCE_CLOSE", payload_json=f'{{"reason": "{validation_msg}"}}')
                return ExecutionResponse(success=False, trade_id=trade_id, error_message=validation_msg)

            # 2. Logika Toleransi Harga 0.2% untuk Menentukan Market vs Limit
            TOLERANCE_PCT = 0.002
            tolerance_price = risk_res.entry_price * TOLERANCE_PCT

            use_market_order = False
            if side == "BUY":
                if current_price <= risk_res.entry_price + tolerance_price:
                    use_market_order = True
            elif side == "SELL":
                if current_price >= risk_res.entry_price - tolerance_price:
                    use_market_order = True

            execution_type_str = "MARKET" if use_market_order else "LIMIT"

            # 3. Setup Account Leverage & Margin Type
            await self._setup_account_position(symbol, leverage)

            entry_side = 'buy' if side == 'BUY' else 'sell'
            exit_side = 'sell' if side == 'BUY' else 'buy'

            # 4. Kirim Order Entry
            logger.info(f"[Trade #{trade_id}] Sending {execution_type_str} Entry Order {side} {risk_res.position_size} {symbol}")

            if self.use_legacy:
                loop = asyncio.get_running_loop()
                if use_market_order:
                    entry_order = await loop.run_in_executor(
                        None,
                        lambda: self.legacy_client.futures_create_order(
                            symbol=symbol, side=entry_side.upper(), type='MARKET', quantity=risk_res.position_size
                        )
                    )
                else:
                    entry_order = await loop.run_in_executor(
                        None,
                        lambda: self.legacy_client.futures_create_order(
                            symbol=symbol, side=entry_side.upper(), type='LIMIT', quantity=risk_res.position_size, price=risk_res.entry_price, timeInForce='GTC'
                        )
                    )
                entry_order_id_str = str(entry_order['orderId'])
            else:
                if use_market_order:
                    entry_order = await self.exchange.create_order(
                        symbol=symbol,
                        type='market',
                        side=entry_side,
                        amount=risk_res.position_size
                    )
                else:
                    entry_order = await self.exchange.create_order(
                        symbol=symbol,
                        type='limit',
                        side=entry_side,
                        amount=risk_res.position_size,
                        price=risk_res.entry_price,
                        params={'timeInForce': 'GTC'}
                    )
                entry_order_id_str = str(entry_order['id'])

            # Catat Entry Order ke Database
            await self.trade_repo.create_order(
                trade_id=trade_id,
                purpose="ENTRY",
                order_type=execution_type_str,
                side=side,
                qty=risk_res.position_size,
                price=risk_res.entry_price,
                binance_order_id=entry_order_id_str
            )

            sl_order_id = None
            tp_order_ids = []

            # 5. Jika MARKET Order: Tunggu Posisi Aktif -> Pasang SL & TP Sekarang Juga
            if use_market_order:
                await self._wait_position_active(symbol)
                await self.trade_repo.update_trade_status(trade_id, "OPEN")

                # Pasang Stop Loss
                if self.use_legacy:
                    loop = asyncio.get_running_loop()
                    # Batalkan Stop Loss / Take Profit lama jika ada (mencegah error -4130 closePosition)
                    try:
                        await loop.run_in_executor(None, lambda: self.legacy_client.futures_cancel_all_open_orders(symbol=symbol))
                    except Exception as e:
                        logger.debug(f"Cancel open orders note [{symbol}]: {e}")

                    sl_order = await loop.run_in_executor(
                        None,
                        lambda: self.legacy_client.futures_create_order(
                            symbol=symbol, side=exit_side.upper(), type='STOP_MARKET', stopPrice=risk_res.stop_loss_price, closePosition=True
                        )
                    )
                    sl_order_id = str(sl_order.get('orderId') or sl_order.get('algoId') or sl_order.get('id') or '')
                else:
                    sl_order = await self.exchange.create_order(
                        symbol=symbol,
                        type='STOP_MARKET',
                        side=exit_side,
                        amount=risk_res.position_size,
                        params={
                            'stopPrice': risk_res.stop_loss_price,
                            'reduceOnly': True
                        }
                    )
                    sl_order_id = str(sl_order['id'])

                await self.trade_repo.create_order(
                    trade_id=trade_id,
                    purpose="SL",
                    order_type="STOP_MARKET",
                    side=exit_side.upper(),
                    qty=risk_res.position_size,
                    price=risk_res.stop_loss_price,
                    binance_order_id=sl_order_id
                )

                # Pasang Multiple TP Orders
                if tp_prices and symbol_info:
                    raw_tp_qty = risk_res.position_size / len(tp_prices)
                    tp_qty = PrecisionFilterService.format_qty(raw_tp_qty, symbol_info)

                    for idx, tp_price in enumerate(tp_prices, 1):
                        purpose_name = f"TP{idx}"
                        clean_tp_price = PrecisionFilterService.format_price(tp_price, symbol_info)
                        if self.use_legacy:
                            loop = asyncio.get_running_loop()
                            tp_order = await loop.run_in_executor(
                                None,
                                lambda t_price=clean_tp_price: self.legacy_client.futures_create_order(
                                    symbol=symbol, side=exit_side.upper(), type='TAKE_PROFIT_MARKET', stopPrice=t_price, quantity=tp_qty, reduceOnly=True
                                )
                            )
                            tp_order_id = str(tp_order.get('orderId') or tp_order.get('algoId') or tp_order.get('id') or '')
                        else:
                            tp_order = await self.exchange.create_order(
                                symbol=symbol,
                                type='TAKE_PROFIT_MARKET',
                                side=exit_side,
                                amount=tp_qty,
                                params={
                                    'stopPrice': tp_price,
                                    'reduceOnly': True
                                }
                            )
                            tp_order_id = str(tp_order['id'])

                        tp_order_ids.append(tp_order_id)

                        await self.trade_repo.create_order(
                            trade_id=trade_id,
                            purpose=purpose_name,
                            order_type="TAKE_PROFIT_MARKET",
                            side=exit_side.upper(),
                            qty=tp_qty,
                            price=tp_price,
                            binance_order_id=tp_order_id
                        )

            else:
                # Jika LIMIT Order: Tunda SL & TP (Nanti dipasang oleh WebSocket Stream Listener ketika Entry FILLED)
                await self.trade_repo.update_trade_status(trade_id, "WAITING_ENTRY")

            await self.trade_repo.log_event(
                trade_id, 
                "ENTRY", 
                payload_json=f'{{"entry_order_id": "{entry_order_id_str}", "type": "{execution_type_str}"}}'
            )

            return ExecutionResponse(
                success=True,
                trade_id=trade_id,
                execution_type=execution_type_str,
                entry_order_id=entry_order_id_str,
                sl_order_id=sl_order_id,
                tp_order_ids=tp_order_ids
            )

        except Exception as e:
            logger.error(f"[Trade #{trade_id}] Execution Failed: {str(e)}")
            await self.trade_repo.update_trade_status(trade_id, "CANCELLED")
            await self.trade_repo.log_event(trade_id, "FORCE_CLOSE", payload_json=f'{{"error": "{str(e)}"}}')

            return ExecutionResponse(
                success=False,
                trade_id=trade_id,
                error_message=str(e)
            )

    async def _setup_account_position(self, symbol: str, leverage: int):
        """Mengeset Leverage dan Margin Type (ISOLATED) dengan menangani exception Binance spesifik."""
        if self.use_legacy:
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, lambda: self.legacy_client.futures_change_margin_type(symbol=symbol, marginType='ISOLATED'))
            except Exception as e:
                logger.debug(f"Margin mode setup note [{symbol}]: {e}")
            try:
                await loop.run_in_executor(None, lambda: self.legacy_client.futures_change_leverage(symbol=symbol, leverage=leverage))
            except Exception as e:
                logger.warning(f"Leverage setup note [{symbol}]: {e}")
        else:
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
                if self.use_legacy:
                    loop = asyncio.get_running_loop()
                    positions = await loop.run_in_executor(None, self.legacy_client.futures_position_information, symbol)
                    for pos in positions:
                        if float(pos.get('positionAmt', 0)) != 0:
                            return
                else:
                    positions = await self.exchange.fetch_positions([symbol])
                    for pos in positions:
                        if float(pos.get('contracts', 0) or pos.get('amount', 0)) != 0:
                            return
            except Exception as e:
                logger.debug(f"Waiting position check error: {e}")

    async def close_connection(self):
        """Menutup koneksi."""
        if not self.use_legacy and self.exchange:
            await self.exchange.close()