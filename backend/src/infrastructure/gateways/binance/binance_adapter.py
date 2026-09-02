"""Binance Exchange Gateway Adapter implementing IExchangeGateway."""

import asyncio
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from src.domain.ports.gateways import IExchangeGateway
from src.domain.value_objects.side import OrderSide, MarginMode
from src.domain.value_objects.trade_status import OrderType
from src.domain.value_objects.symbol import Symbol
from src.domain.value_objects.price import Price
from src.domain.value_objects.quantity import Quantity
from src.domain.value_objects.leverage import Leverage
from src.infrastructure.gateways.binance.binance_connector import BinanceConnector
from src.infrastructure.gateways.binance.binance_parser import BinanceParser
from src.infrastructure.gateways.binance.binance_validator import BinanceValidator

logger = logging.getLogger(__name__)


class BinanceExchangeAdapter(IExchangeGateway):
    """Orchestrates BinanceConnector, BinanceParser, and BinanceValidator to fulfill IExchangeGateway port."""

    def __init__(
        self,
        connector: BinanceConnector,
        parser: Optional[BinanceParser] = None,
        validator: Optional[BinanceValidator] = None,
    ) -> None:
        self.connector = connector
        self.parser = parser or BinanceParser()
        self.validator = validator or BinanceValidator()

    async def get_balance(self) -> Dict[str, Any]:
        """Fetch total and free account wallet balances."""
        raw = await self.connector.execute_rest("fetch_balance")
        return self.parser.parse_balance(raw)

    async def fetch_balance(self) -> Dict[str, Any]:
        """Alias for get_balance."""
        return await self.get_balance()

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current ticker price and book quotes."""
        clean_sym = self.validator.validate_symbol(symbol)
        ccxt_sym = self.parser.to_ccxt_symbol(clean_sym)
        raw = await self.connector.execute_rest("fetch_ticker", ccxt_sym)
        return self.parser.parse_ticker(raw)

    async def fetch_ticker_price(self, symbol: str) -> Decimal:
        """Fetch current realtime mark/last price for a symbol as Decimal."""
        clean_sym = self.validator.validate_symbol(symbol)
        ccxt_sym = self.parser.to_ccxt_symbol(clean_sym)
        ticker = await self.connector.execute_rest("fetch_ticker", ccxt_sym)
        last_price = ticker.get("last") or ticker.get("close") or 0.0
        return Decimal(str(last_price))

    async def fetch_klines(
        self,
        symbol: str,
        timeframe: str = "1m",
        since: Optional[int] = None,
        limit: int = 30,
    ) -> List[List[Any]]:
        """Fetch OHLCV candlestick data for a symbol."""
        clean_sym = self.validator.validate_symbol(symbol)
        ccxt_sym = self.parser.to_ccxt_symbol(clean_sym)
        klines = await self.connector.execute_rest(
            "fetch_ohlcv", ccxt_sym, timeframe=timeframe, since=since, limit=limit
        )
        return klines or []

    async def has_price_reached_target(
        self,
        symbol: str,
        target_price: Decimal,
        side: str,
        since_timestamp_ms: Optional[int] = None,
        limit: int = 30,
        is_sl: bool = False,
    ) -> bool:
        """Check whether historical candles touched or exceeded a target price (e.g. TP1 / SL)."""
        if not target_price or target_price <= Decimal("0"):
            return False

        try:
            effective_limit = limit if since_timestamp_ms else 2
            klines = await self.fetch_klines(
                symbol=symbol,
                timeframe="1m",
                since=since_timestamp_ms,
                limit=effective_limit,
            )
            if not klines:
                return False

            side_upper = side.upper()
            target = Decimal(str(target_price))

            for candle in klines:
                if len(candle) < 5:
                    continue
                candle_open_ts = int(candle[0])
                if since_timestamp_ms and (candle_open_ts + 60_000 < since_timestamp_ms):
                    continue

                high_price = Decimal(str(candle[2]))
                low_price = Decimal(str(candle[3]))

                if is_sl:
                    # For Stop Loss:
                    # BUY SL is below entry -> triggered when price drops to/below SL
                    # SELL SL is above entry -> triggered when price rises to/above SL
                    if side_upper in ("BUY", "LONG"):
                        if low_price <= target:
                            return True
                    else:
                        if high_price >= target:
                            return True
                else:
                    # For Take Profit:
                    # BUY TP is above entry -> reached when price rises to/above TP
                    # SELL TP is below entry -> reached when price drops to/below TP
                    if side_upper in ("BUY", "LONG"):
                        if high_price >= target:
                            return True
                    else:
                        if low_price <= target:
                            return True

            return False
        except Exception as e:
            logger.warning(f"Failed checking if price reached target {target_price} for {symbol}: {e}")
            return False

    async def set_leverage(self, symbol: str, leverage: Union[int, Leverage]) -> Dict[str, Any]:
        """Set position leverage on exchange."""
        clean_sym = self.validator.validate_symbol(symbol)
        lev_val = self.validator.validate_leverage(leverage)
        ccxt_sym = self.parser.to_ccxt_symbol(clean_sym)
        raw = await self.connector.execute_rest("set_leverage", lev_val, ccxt_sym)
        return {"symbol": clean_sym, "leverage": lev_val, "raw": raw}

    async def set_margin_mode(self, symbol: str, margin_mode: Union[MarginMode, str]) -> Dict[str, Any]:
        """Set ISOLATED or CROSSED margin mode."""
        clean_sym = self.validator.validate_symbol(symbol)
        mode_val = self.validator.validate_margin_mode(margin_mode)
        ccxt_sym = self.parser.to_ccxt_symbol(clean_sym)
        try:
            raw = await self.connector.execute_rest("set_margin_mode", mode_val, ccxt_sym)
            return {"symbol": clean_sym, "margin_mode": mode_val, "raw": raw}
        except Exception as exc:
            # Binance raises if margin mode is already set to the target mode (No need to change margin type)
            if "No need to change" in str(exc):
                return {"symbol": clean_sym, "margin_mode": mode_val, "status": "ALREADY_SET"}
            raise

    async def set_position_mode(self, dual_side_position: bool = False) -> Dict[str, Any]:
        """Set One-Way Position mode (dual_side_position=False) or Hedge Mode."""
        try:
            raw = await self.connector.execute_rest("set_position_mode", dual_side_position)
            return {"dualSidePosition": dual_side_position, "raw": raw}
        except Exception as exc:
            if "no need to change" in str(exc).lower() or "-4059" in str(exc):
                return {"dualSidePosition": dual_side_position, "status": "ALREADY_SET"}
            raise

    async def create_order(
        self,
        symbol: str,
        side: Union[OrderSide, str],
        order_type: Union[OrderType, str],
        qty: Union[Decimal, Quantity, float],
        price: Optional[Union[Decimal, Price, float]] = None,
        stop_price: Optional[Union[Decimal, Price, float]] = None,
        client_order_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Submit a single futures order (MARKET, LIMIT, STOP_MARKET, TAKE_PROFIT_MARKET)."""
        effective_price = price or stop_price
        self.validator.validate_order(symbol, side, order_type, qty, effective_price)

        clean_sym = Symbol.normalize(symbol)
        ccxt_sym = self.parser.to_ccxt_symbol(clean_sym)
        side_val = (side.value if isinstance(side, OrderSide) else str(side)).lower()
        type_val = (order_type.value if isinstance(order_type, OrderType) else str(order_type)).lower()

        qty_float = float(qty.value if isinstance(qty, Quantity) else Decimal(str(qty)))
        price_float = float(effective_price.value if isinstance(effective_price, Price) else Decimal(str(effective_price))) if effective_price else None

        req_params = dict(params or {})
        if client_order_id:
            req_params["newClientOrderId"] = client_order_id
        if stop_price:
            stop_val = float(stop_price.value if isinstance(stop_price, Price) else Decimal(str(stop_price)))
            req_params["stopPrice"] = stop_val
            if "workingType" not in req_params:
                req_params["workingType"] = "MARK_PRICE"

        raw = await self.connector.execute_rest(
            "create_order",
            ccxt_sym,
            type_val,
            side_val,
            qty_float,
            price_float,
            req_params,
        )
        return self.parser.parse_order(raw)

    async def create_entry_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: Decimal,
        price: Optional[Decimal] = None,
        client_order_id: Optional[str] = None,
        reduce_only: bool = False,
    ) -> Dict[str, Any]:
        """Submit an Entry order (MARKET or LIMIT)."""
        params: Dict[str, Any] = {}
        if client_order_id:
            params["newClientOrderId"] = client_order_id
        if reduce_only:
            params["reduceOnly"] = True

        return await self.create_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            qty=qty,
            price=price,
            params=params,
        )

    async def create_stop_loss_order(
        self,
        symbol: str,
        side: str,
        stop_price: Decimal,
        qty: Optional[Decimal] = None,
        client_order_id: Optional[str] = None,
        close_position: bool = True,
        working_type: str = "MARK_PRICE",
    ) -> Dict[str, Any]:
        """Submit a Stop Loss order (STOP_MARKET)."""
        clean_sym = self.validator.validate_symbol(symbol)
        ccxt_sym = self.parser.to_ccxt_symbol(clean_sym)
        params: Dict[str, Any] = {
            "stopPrice": float(stop_price),
            "workingType": working_type,
            "priceProtect": "TRUE",
        }
        if close_position:
            params["closePosition"] = True
        else:
            params["reduceOnly"] = True

        if client_order_id:
            params["newClientOrderId"] = client_order_id

        amount_float = float(qty) if (qty is not None and not close_position) else None
        side_lower = side.strip().lower()

        raw = await self.connector.execute_rest(
            "create_order",
            ccxt_sym,
            "stop_market",
            side_lower,
            amount_float,
            params=params,
        )
        return self.parser.parse_order(raw)

    async def create_take_profit_order(
        self,
        symbol: str,
        side: str,
        tp_price: Decimal,
        qty: Decimal,
        client_order_id: Optional[str] = None,
        working_type: str = "MARK_PRICE",
    ) -> Dict[str, Any]:
        """Submit a Take Profit Market order."""
        clean_sym = self.validator.validate_symbol(symbol)
        ccxt_sym = self.parser.to_ccxt_symbol(clean_sym)
        params: Dict[str, Any] = {
            "stopPrice": float(tp_price),
            "workingType": working_type,
            "reduceOnly": True,
        }
        if client_order_id:
            params["newClientOrderId"] = client_order_id

        raw = await self.connector.execute_rest(
            "create_order",
            ccxt_sym,
            "take_profit_market",
            side.strip().lower(),
            float(qty),
            params=params,
        )
        return self.parser.parse_order(raw)

    async def cancel_order(
        self,
        symbol: str,
        exchange_order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel an open order by ID."""
        clean_sym = self.validator.validate_symbol(symbol)
        ccxt_sym = self.parser.to_ccxt_symbol(clean_sym)

        order_id = exchange_order_id
        params: Dict[str, Any] = {}
        if client_order_id and not exchange_order_id:
            params["clientOrderId"] = client_order_id
            order_id = client_order_id

        raw = await self.connector.execute_rest("cancel_order", order_id, ccxt_sym, params)
        return self.parser.parse_order(raw)

    async def cancel_all_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Cancel all open orders for a symbol."""
        clean_sym = self.validator.validate_symbol(symbol)
        ccxt_sym = self.parser.to_ccxt_symbol(clean_sym)
        raw_list = await self.connector.execute_rest("cancel_all_orders", ccxt_sym)
        if isinstance(raw_list, list):
            results = []
            for o in raw_list:
                try:
                    results.append(self.parser.parse_order(o))
                except Exception:
                    results.append({"status": "CANCELED", "raw": o})
            return results
        return [{"status": "ALL_CANCELLED", "symbol": clean_sym, "raw": raw_list}]

    async def cancel_all_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Alias for cancel_all_orders."""
        return await self.cancel_all_orders(symbol)

    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch active open orders."""
        ccxt_sym = self.parser.to_ccxt_symbol(symbol) if symbol else None
        raw_list = await self.connector.execute_rest("fetch_open_orders", ccxt_sym)
        return [self.parser.parse_order(o) for o in (raw_list or [])]

    async def fetch_order(self, symbol: str, order_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the current status and execution details of a specific order."""
        clean_sym = self.validator.validate_symbol(symbol)
        ccxt_sym = self.parser.to_ccxt_symbol(clean_sym)
        raw = await self.connector.execute_rest("fetch_order", order_id, ccxt_sym)
        if not raw:
            return None
        return self.parser.parse_order(raw)

    async def fetch_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch open futures positions."""
        ccxt_sym = self.parser.to_ccxt_symbol(symbol) if symbol else None
        raw_list = await self.connector.execute_rest("fetch_positions", [ccxt_sym] if ccxt_sym else None)
        return [self.parser.parse_position(p) for p in (raw_list or [])]

    async def fetch_leverage_brackets(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch leverage bracket tiers."""
        clean_sym = self.validator.validate_symbol(symbol) if symbol else None
        if hasattr(self.connector, "fetch_leverage_brackets"):
            raw = await self.connector.fetch_leverage_brackets(clean_sym)
        else:
            ccxt_sym = self.parser.to_ccxt_symbol(clean_sym) if clean_sym else None
            raw = await self.connector.execute_rest("fetch_leverage_brackets", [ccxt_sym] if ccxt_sym else None)
        return self.parser.parse_leverage_brackets(raw)

    async def edit_order(
        self,
        order_id: str,
        symbol: str,
        side: Union[OrderSide, str],
        order_type: Union[OrderType, str],
        qty: Optional[Union[Decimal, Quantity, float]] = None,
        price: Optional[Union[Decimal, Price, float]] = None,
        stop_price: Optional[Union[Decimal, Price, float]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Modify an active order in-place without cancel/recreate race conditions."""
        clean_sym = self.validator.validate_symbol(symbol)
        ccxt_sym = self.parser.to_ccxt_symbol(clean_sym)
        side_val = (side.value if isinstance(side, OrderSide) else str(side)).lower()
        type_val = (order_type.value if isinstance(order_type, OrderType) else str(order_type)).lower()

        qty_float = float(qty.value if isinstance(qty, Quantity) else Decimal(str(qty))) if qty is not None else None
        price_float = float(price.value if isinstance(price, Price) else Decimal(str(price))) if price is not None else None

        req_params = dict(params or {})
        if stop_price is not None:
            req_params["stopPrice"] = float(stop_price.value if isinstance(stop_price, Price) else Decimal(str(stop_price)))

        raw = await self.connector.execute_rest(
            "edit_order",
            order_id,
            ccxt_sym,
            type_val,
            side_val,
            qty_float,
            price_float,
            params=req_params,
        )
        return self.parser.parse_order(raw)

    async def fetch_my_trades(
        self,
        symbol: Optional[str] = None,
        since: Optional[int] = None,
        limit: Optional[int] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch executed trades from exchange."""
        clean_sym = self.validator.validate_symbol(symbol) if symbol else None
        ccxt_sym = self.parser.to_ccxt_symbol(clean_sym) if clean_sym else None
        raw_trades = await self.connector.execute_rest(
            "fetch_my_trades",
            ccxt_sym,
            since=since,
            limit=limit or 20,
            params=params or {},
        )
        return raw_trades or []

    async def cancel_stop_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Cancel all stop-market and take-profit open orders for a symbol safely."""
        clean_sym = self.validator.validate_symbol(symbol)
        open_orders = await self.fetch_open_orders(clean_sym)
        cancelled = []
        for o in open_orders:
            otype = str(o.get("order_type") or o.get("type") or "").upper()
            if "STOP" in otype or "TAKE_PROFIT" in otype:
                oid = o.get("exchange_order_id") or o.get("id")
                if oid:
                    try:
                        res = await self.cancel_order(clean_sym, exchange_order_id=str(oid))
                        cancelled.append(res)
                    except Exception as exc:
                        logger.debug("Could not cancel stop order %s: %s", oid, exc)
        return cancelled

    async def fetch_instruments_metadata(self) -> List[Dict[str, Any]]:
        """Fetch active trading pairs and precision rules from exchange."""
        if hasattr(self.connector, "fetch_instruments_metadata"):
            return await self.connector.fetch_instruments_metadata()
        if hasattr(self.connector, "rest_client") and hasattr(self.connector.rest_client, "fetch_instruments_metadata"):
            return await self.connector.rest_client.fetch_instruments_metadata()
        return []

    def reconfigure(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        testnet: Optional[bool] = None,
    ) -> None:
        """Dynamically update credentials and network mode on the underlying connector."""
        self.connector.reconfigure(api_key=api_key, secret_key=secret_key, testnet=testnet)

    async def close(self) -> None:
        """Close the underlying connector sessions."""
        await self.connector.close()

    async def watch_orders_stream(self, callback_coro: Any) -> None:
        """Subscribe and stream live order fill updates via BinanceConnector."""
        await self.connector.watch_orders_stream(callback_coro=callback_coro)

    def start_order_stream_task(self, on_fill_coro: Any) -> Optional[Any]:
        """Start the background order stream task if API key is configured."""
        if not self.connector.api_key:
            return None
        return asyncio.create_task(self.watch_orders_stream(callback_coro=on_fill_coro))

    async def process_ws_order_event(
        self,
        raw_event: Dict[str, Any],
        handle_fill_use_case: Optional[Any] = None,
    ) -> Optional[Any]:
        """Process raw exchange WebSocket event through HandleOrderFillUseCase."""
        if not raw_event or not isinstance(raw_event, dict):
            return None
        if handle_fill_use_case and hasattr(handle_fill_use_case, "execute_from_raw_event"):
            return await handle_fill_use_case.execute_from_raw_event(raw_event)
        return None

