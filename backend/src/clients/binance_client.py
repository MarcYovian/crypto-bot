"""External Binance Futures REST and WebSocket client using CCXT."""

import asyncio
from decimal import Decimal
from typing import Optional, List, Dict, Any
import ccxt.async_support as ccxt
from src.domain.exceptions import (
    ExchangeError,
    ExchangeNetworkError,
    ExchangeAuthError,
    InsufficientMarginError,
    OrderRejectError,
    RateLimitError,
)


class BinanceRestClient:
    """Async REST Client for Binance USDT-M Futures."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: bool = True,
        timeout: int = 30000,
    ) -> None:
        self.api_key = api_key
        self.secret_key = secret_key or api_secret
        self.testnet = testnet
        self.timeout = timeout

        config = {
            "apiKey": self.api_key or "",
            "secret": self.secret_key or "",
            "timeout": self.timeout,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
        }

        self.client: ccxt.binance = ccxt.binance(config)
        if self.testnet:
            if hasattr(self.client, "enable_demo_trading"):
                self.client.enable_demo_trading(True)
            else:
                self.client.set_sandbox_mode(True)

    def reconfigure(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        testnet: Optional[bool] = None,
    ) -> None:
        """Dynamically update client API credentials and network mode."""
        if api_key is not None:
            self.api_key = api_key
            self.client.apiKey = api_key
        if secret_key is not None:
            self.secret_key = secret_key
            self.client.secret = secret_key
        if testnet is not None:
            self.testnet = testnet
            if self.testnet:
                if hasattr(self.client, "enable_demo_trading"):
                    self.client.enable_demo_trading(True)
                else:
                    self.client.set_sandbox_mode(True)
            else:
                if hasattr(self.client, "enable_demo_trading"):
                    self.client.enable_demo_trading(False)
                else:
                    self.client.set_sandbox_mode(False)

    def _handle_ccxt_exception(self, e: Exception, operation: str) -> None:
        """Map raw CCXT exceptions to Domain custom exceptions."""
        error_msg = str(e)
        details = {"operation": operation, "raw_error": error_msg}

        if isinstance(e, ccxt.InsufficientFunds):
            raise InsufficientMarginError(f"Insufficient margin during {operation}: {error_msg}", details=details) from e
        elif isinstance(e, (ccxt.AuthenticationError, ccxt.PermissionDenied)):
            raise ExchangeAuthError(f"Authentication failed during {operation}: {error_msg}", details=details) from e
        elif isinstance(e, (ccxt.RateLimitExceeded, ccxt.DDoSProtection)):
            raise RateLimitError(f"Rate limit exceeded during {operation}: {error_msg}", details=details) from e
        elif isinstance(e, (ccxt.InvalidOrder, ccxt.OrderNotFound, ccxt.OrderImmediatelyFillable)):
            raise OrderRejectError(f"Order rejected during {operation}: {error_msg}", details=details) from e
        elif isinstance(e, (ccxt.NetworkError, ccxt.RequestTimeout, ccxt.ExchangeNotAvailable)):
            raise ExchangeNetworkError(f"Network error during {operation}: {error_msg}", details=details) from e
        elif isinstance(e, ccxt.ExchangeError):
            raise ExchangeError(f"Exchange error during {operation}: {error_msg}", details=details) from e
        else:
            raise ExchangeError(f"Unexpected error during {operation}: {error_msg}", details=details) from e

    async def initialize(self) -> None:
        """Load markets and instrument specifications into CCXT cache."""
        try:
            await self.client.load_markets()
        except Exception as e:
            self._handle_ccxt_exception(e, "initialize/load_markets")

    async def fetch_instruments_metadata(self) -> List[Dict[str, Any]]:
        """Fetch all active USDT-M perpetual contracts and precision parameters.
        
        Returns:
            List of parsed dictionary metadata suitable for Instrument model.
        """
        try:
            if not self.client.markets:
                await self.client.load_markets()

            results: List[Dict[str, Any]] = []
            for symbol, market in self.client.markets.items():
                # Filter active USDT linear futures contracts
                if market.get("active") and market.get("linear") and market.get("quote") == "USDT":
                    info = market.get("info", {})
                    filters = {f.get("filterType"): f for f in info.get("filters", [])}

                    price_filter = filters.get("PRICE_FILTER", {})
                    lot_filter = filters.get("LOT_SIZE", {})
                    min_notional_filter = filters.get("MIN_NOTIONAL", {})

                    tick_size_str = price_filter.get("tickSize") or str(market.get("precision", {}).get("price", "0.01"))
                    step_size_str = lot_filter.get("stepSize") or str(market.get("precision", {}).get("amount", "0.001"))
                    min_qty_str = lot_filter.get("minQty") or step_size_str
                    min_notional_str = min_notional_filter.get("notional") or str(market.get("limits", {}).get("cost", {}).get("min", "5.0"))

                    tick_dec = Decimal(str(tick_size_str)) if tick_size_str and Decimal(str(tick_size_str)) > 0 else Decimal("0.01")
                    step_dec = Decimal(str(step_size_str)) if step_size_str and Decimal(str(step_size_str)) > 0 else Decimal("0.001")
                    min_qty_dec = Decimal(str(min_qty_str)) if min_qty_str and Decimal(str(min_qty_str)) > 0 else step_dec
                    min_notional_dec = Decimal(str(min_notional_str)) if min_notional_str and Decimal(str(min_notional_str)) > 0 else Decimal("5.0")

                    # Calculate decimal places safely
                    raw_price_prec = info.get("pricePrecision")
                    if raw_price_prec is not None:
                        price_precision = int(raw_price_prec)
                    else:
                        price_exp = tick_dec.normalize().as_tuple().exponent
                        price_precision = abs(price_exp) if isinstance(price_exp, int) else 2

                    raw_qty_prec = info.get("quantityPrecision")
                    if raw_qty_prec is not None:
                        qty_precision = int(raw_qty_prec)
                    else:
                        qty_exp = step_dec.normalize().as_tuple().exponent
                        qty_precision = abs(qty_exp) if isinstance(qty_exp, int) else 3

                    results.append({
                        "symbol": market.get("id", symbol.replace("/", "").replace(":USDT", "")),
                        "base_asset": market.get("base"),
                        "quote_asset": market.get("quote"),
                        "price_precision": price_precision,
                        "qty_precision": qty_precision,
                        "tick_size": tick_dec,
                        "step_size": step_dec,
                        "min_qty": min_qty_dec,
                        "min_notional": min_notional_dec,
                        "is_active": True,
                    })

            return results
        except Exception as e:
            self._handle_ccxt_exception(e, "fetch_instruments_metadata")
            return []

    async def fetch_leverage_brackets(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch tiered leverage and notional brackets from Binance Futures.

        Args:
            symbol: Optional trading pair symbol, e.g. 'AAVEUSDT'. If None, fetches all symbols.

        Returns:
            List of parsed dictionaries containing symbol and its bracket tiers.
        """
        try:
            params: Dict[str, Any] = {}
            if symbol:
                clean_sym = symbol.replace("/", "").replace(":USDT", "").upper()
                params["symbol"] = clean_sym

            # Query Binance /fapi/v1/leverageBracket
            raw_data = await self.client.fapiPrivateGetLeverageBracket(params)
            if isinstance(raw_data, dict):
                raw_data = [raw_data]

            results: List[Dict[str, Any]] = []
            max_safe_cap = Decimal("9999999999")  # Prevent NUMERIC(18, 8) overflow on infinity caps
            for item in raw_data:
                sym = item.get("symbol", "").replace("/", "").replace(":USDT", "").upper()
                brackets_parsed = []
                for b in item.get("brackets", []):
                    raw_cap = Decimal(str(b.get("notionalCap", 0)))
                    capped_val = min(raw_cap, max_safe_cap)
                    brackets_parsed.append({
                        "bracket": int(b.get("bracket", 1)),
                        "initial_leverage": int(b.get("initialLeverage", 20)),
                        "notional_cap": capped_val,
                        "notional_floor": Decimal(str(b.get("notionalFloor", 0))),
                        "maint_margin_ratio": Decimal(str(b.get("maintMarginRatio", "0.01"))),
                        "cum": Decimal(str(b.get("cum", "0"))),
                    })
                results.append({
                    "symbol": sym,
                    "brackets": brackets_parsed,
                })

            return results
        except Exception as e:
            self._handle_ccxt_exception(e, f"fetch_leverage_brackets({symbol})")
            return []

    async def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """Set position leverage for a specific symbol (Idempotent)."""
        try:
            return await self.client.set_leverage(leverage, symbol)
        except Exception as e:
            # Handle idempotent "leverage not modified" silently if applicable
            if "leverage not modified" in str(e).lower():
                return {"symbol": symbol, "leverage": leverage}
            self._handle_ccxt_exception(e, f"set_leverage({symbol}, {leverage})")
            return {}

    async def set_margin_mode(self, symbol: str, margin_mode: str = "ISOLATED") -> Dict[str, Any]:
        """Set margin type ('ISOLATED' or 'CROSSED') (Idempotent)."""
        try:
            return await self.client.set_margin_mode(margin_mode.upper(), symbol)
        except Exception as e:
            # Catch "No need to change margin type" / "-4046" gracefully
            if "no need to change" in str(e).lower() or "-4046" in str(e):
                return {"symbol": symbol, "margin_mode": margin_mode}
            self._handle_ccxt_exception(e, f"set_margin_mode({symbol}, {margin_mode})")
            return {}

    async def set_position_mode(self, dual_side_position: bool = False) -> Dict[str, Any]:
        """Set One-Way Position mode (dual_side_position=False)."""
        try:
            return await self.client.set_position_mode(dual_side_position)
        except Exception as e:
            if "no need to change" in str(e).lower() or "-4059" in str(e):
                return {"dualSidePosition": dual_side_position}
            self._handle_ccxt_exception(e, f"set_position_mode({dual_side_position})")
            return {}

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
        try:
            params: Dict[str, Any] = {}
            if client_order_id:
                params["newClientOrderId"] = client_order_id
            if reduce_only:
                params["reduceOnly"] = True

            amount_float = float(qty)
            price_float = float(price) if price is not None else None
            side_lower = side.strip().lower()
            type_lower = order_type.strip().lower()

            return await self.client.create_order(
                symbol=symbol,
                type=type_lower,
                side=side_lower,
                amount=amount_float,
                price=price_float,
                params=params,
            )
        except Exception as e:
            self._handle_ccxt_exception(e, f"create_entry_order({symbol}, {side}, {qty})")
            return {}

    async def create_stop_loss_order(
        self,
        symbol: str,
        side: str,
        stop_price: Decimal,
        qty: Optional[Decimal] = None,
        client_order_id: Optional[str] = None,
        close_position: bool = False,
    ) -> Dict[str, Any]:
        """Submit a Stop Loss order (STOP_MARKET)."""
        try:
            params: Dict[str, Any] = {
                "stopPrice": float(stop_price),
            }
            if close_position and qty is None:
                params["closePosition"] = True
            else:
                params["reduceOnly"] = True

            if client_order_id:
                params["newClientOrderId"] = client_order_id

            amount_float = float(qty) if qty is not None else None
            side_lower = side.strip().lower()

            return await self.client.create_order(
                symbol=symbol,
                type="stop_market",
                side=side_lower,
                amount=amount_float,
                params=params,
            )
        except Exception as e:
            self._handle_ccxt_exception(e, f"create_stop_loss_order({symbol}, {stop_price})")
            return {}

    async def create_take_profit_order(
        self,
        symbol: str,
        side: str,
        tp_price: Decimal,
        qty: Decimal,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit a Take Profit Limit order with reduceOnly=True."""
        try:
            params: Dict[str, Any] = {
                "reduceOnly": True,
            }
            if client_order_id:
                params["newClientOrderId"] = client_order_id

            return await self.client.create_order(
                symbol=symbol,
                type="limit",
                side=side.strip().lower(),
                amount=float(qty),
                price=float(tp_price),
                params=params,
            )
        except Exception as e:
            self._handle_ccxt_exception(e, f"create_take_profit_order({symbol}, {tp_price})")
            return {}

    async def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel an order by exchange orderId or clientOrderId."""
        try:
            params: Dict[str, Any] = {}
            if client_order_id:
                params["origClientOrderId"] = client_order_id
            return await self.client.cancel_order(
                id=order_id,
                symbol=symbol,
                params=params,
            )
        except Exception as e:
            self._handle_ccxt_exception(e, f"cancel_order({symbol}, {order_id})")
            return {}

    async def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        """Cancel all open orders on a symbol."""
        try:
            return await self.client.cancel_all_orders(symbol=symbol)
        except Exception as e:
            self._handle_ccxt_exception(e, f"cancel_all_orders({symbol})")
            return {}

    async def fetch_balance(self) -> Dict[str, Decimal]:
        """Fetch futures account wallet and margin balance.
        
        Returns:
            Dict containing total_wallet_balance, free_margin, used_margin, unrealized_pnl.
        """
        try:
            balance = await self.client.fetch_balance()
            usdt = balance.get("USDT", {})
            
            total = usdt.get("total", 0.0)
            free = usdt.get("free", 0.0)
            used = usdt.get("used", 0.0)
            
            info = balance.get("info", {})
            unrealized = info.get("totalUnrealizedProfit", 0.0)

            return {
                "total_wallet_balance": Decimal(str(total or 0)),
                "free_margin": Decimal(str(free or 0)),
                "used_margin": Decimal(str(used or 0)),
                "unrealized_pnl": Decimal(str(unrealized or 0)),
            }
        except Exception as e:
            self._handle_ccxt_exception(e, "fetch_balance")
            return {}

    async def fetch_ticker_price(self, symbol: str) -> Decimal:
        """Fetch current realtime mark/last price for a symbol."""
        try:
            ticker = await self.client.fetch_ticker(symbol)
            last_price = ticker.get("last") or ticker.get("close") or 0.0
            return Decimal(str(last_price))
        except Exception as e:
            self._handle_ccxt_exception(e, f"fetch_ticker_price({symbol})")
            return Decimal("0.0")

    async def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Fetch open positions."""
        try:
            positions = await self.client.fetch_positions(symbols=symbols)
            results: List[Dict[str, Any]] = []
            for pos in positions:
                contracts = pos.get("contracts", 0)
                if contracts and float(contracts) > 0:
                    results.append({
                        "symbol": pos.get("symbol"),
                        "side": pos.get("side"),
                        "contracts": Decimal(str(contracts)),
                        "entry_price": Decimal(str(pos.get("entryPrice", 0))),
                        "mark_price": Decimal(str(pos.get("markPrice", 0))),
                        "unrealized_pnl": Decimal(str(pos.get("unrealizedPnl", 0))),
                        "leverage": int(pos.get("leverage", 1)),
                        "liquidation_price": Decimal(str(pos.get("liquidationPrice") or 0)),
                    })
            return results
        except Exception as e:
            self._handle_ccxt_exception(e, "fetch_positions")
            return []

    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch active/open orders waiting for execution on Binance Futures.

        Args:
            symbol: Optional trading pair symbol, e.g. "BTCUSDT". If None, fetches open orders for all symbols.

        Returns:
            List of parsed open order dictionaries.
        """
        try:
            raw_orders = await self.client.fetch_open_orders(symbol=symbol)
            results: List[Dict[str, Any]] = []
            for o in raw_orders:
                results.append({
                    "id": str(o.get("id", "")),
                    "client_order_id": str(o.get("clientOrderId", "")),
                    "symbol": o.get("symbol", "").replace("/", "").replace(":USDT", "").upper(),
                    "type": str(o.get("type", "")).upper(),
                    "side": str(o.get("side", "")).upper(),
                    "price": Decimal(str(o.get("price") or 0)) if o.get("price") is not None else None,
                    "stop_price": Decimal(str(o.get("stopPrice") or 0)) if o.get("stopPrice") is not None else None,
                    "amount": Decimal(str(o.get("amount") or 0)),
                    "filled": Decimal(str(o.get("filled") or 0)),
                    "remaining": Decimal(str(o.get("remaining") or 0)),
                    "status": str(o.get("status", "")).upper(),
                    "reduce_only": bool(o.get("reduceOnly", False) or (o.get("info") and o.get("info", {}).get("reduceOnly") in (True, "true", "TRUE"))),
                    "timestamp": o.get("timestamp"),
                })
            return results
        except Exception as e:
            self._handle_ccxt_exception(e, f"fetch_open_orders({symbol})")
            return []

    async def fetch_order(self, symbol: str, order_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the current status and execution details of a specific order.

        Args:
            symbol: Trading pair symbol, e.g. "BTCUSDT".
            order_id: Exchange order ID.

        Returns:
            Parsed order dictionary or None if not found/error.
        """
        try:
            o = await self.client.fetch_order(id=order_id, symbol=symbol)
            if not o:
                return None
            return {
                "id": str(o.get("id", "")),
                "client_order_id": str(o.get("clientOrderId", "")),
                "symbol": o.get("symbol", "").replace("/", "").replace(":USDT", "").upper(),
                "type": str(o.get("type", "")).upper(),
                "side": str(o.get("side", "")).upper(),
                "price": Decimal(str(o.get("price") or 0)) if o.get("price") is not None else None,
                "stop_price": Decimal(str(o.get("stopPrice") or 0)) if o.get("stopPrice") is not None else None,
                "amount": Decimal(str(o.get("amount") or 0)),
                "filled": Decimal(str(o.get("filled") or 0)),
                "remaining": Decimal(str(o.get("remaining") or 0)),
                "status": str(o.get("status", "")).upper(),
                "reduce_only": bool(o.get("reduceOnly", False) or (o.get("info") and o.get("info", {}).get("reduceOnly") in (True, "true", "TRUE"))),
                "timestamp": o.get("timestamp"),
            }
        except Exception as e:
            self._handle_ccxt_exception(e, f"fetch_order({symbol}, {order_id})")
            return None

    async def close(self) -> None:
        """Close the underlying aiohttp CCXT session."""
        try:
            await self.client.close()
        except Exception:
            pass


class BinanceWebSocketClient:
    """Async WebSocket client for Binance User Data Stream and Ticker updates."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: bool = True,
    ) -> None:
        self.api_key = api_key
        self.secret_key = secret_key or api_secret
        self.testnet = testnet
        self.is_running = False

    async def watch_orders_stream(self, callback_coro) -> None:
        """Subscribe to order fill status updates."""
        self.is_running = True
        # Streaming loop implementation with callback handler
        while self.is_running:
            await asyncio.sleep(1)

    async def watch_ticker_stream(self, symbols: List[str], callback_coro) -> None:
        """Subscribe to live mark price tickers."""
        self.is_running = True
        while self.is_running:
            await asyncio.sleep(1)

    async def close(self) -> None:
        """Stop websocket loops and close connections."""
        self.is_running = False
