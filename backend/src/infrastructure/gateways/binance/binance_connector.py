"""Low-level CCXT & CCXT Pro connector with error translation, dynamic credential reconfiguration, and lifecycle management."""

import asyncio
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
import ccxt.async_support as ccxt
import ccxt.pro as ccxtpro

from src.domain.exceptions import (
    ExchangeError,
    ExchangeNetworkError,
    ExchangeAuthError,
    InsufficientMarginError,
    OrderRejectError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


class BinanceConnector:
    """Manages the raw async CCXT REST and CCXT Pro WebSocket sessions with dynamic reconfiguration support."""

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
        self._exchange: Optional[ccxt.binanceusdm] = None
        self._ws_exchange: Optional[ccxtpro.binanceusdm] = None
        self._lock = asyncio.Lock()

    def _build_exchange_config(self) -> Dict[str, Any]:
        cfg: Dict[str, Any] = {
            "timeout": self.timeout,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
                "recvWindow": 10000,
            },
        }
        if self.api_key and self.secret_key:
            cfg["apiKey"] = self.api_key
            cfg["secret"] = self.secret_key
        return cfg

    def _apply_sandbox_mode(self, client: Any, is_testnet: bool) -> None:
        """Apply testnet / demo trading mode to a CCXT instance."""
        if is_testnet:
            if hasattr(client, "enable_demo_trading"):
                client.enable_demo_trading(True)
            else:
                client.set_sandbox_mode(True)
        else:
            if hasattr(client, "enable_demo_trading"):
                client.enable_demo_trading(False)
            else:
                client.set_sandbox_mode(False)

    def reconfigure(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        testnet: Optional[bool] = None,
    ) -> None:
        """Dynamically update client API credentials and network mode at runtime (e.g. from database rotation)."""
        if api_key is not None:
            self.api_key = api_key
            if self._exchange:
                self._exchange.apiKey = api_key
            if self._ws_exchange:
                self._ws_exchange.apiKey = api_key

        if secret_key is not None:
            self.secret_key = secret_key
            if self._exchange:
                self._exchange.secret = secret_key
            if self._ws_exchange:
                self._ws_exchange.secret = secret_key

        if testnet is not None:
            self.testnet = testnet
            if self._exchange:
                self._apply_sandbox_mode(self._exchange, testnet)
            if self._ws_exchange:
                self._apply_sandbox_mode(self._ws_exchange, testnet)

        logger.info(
            "BinanceConnector reconfigured: testnet=%s, key_set=%s",
            self.testnet,
            bool(self.api_key),
        )

    async def get_rest_exchange(self) -> ccxt.binanceusdm:
        """Get or initialize the CCXT REST client instance (thread-safe)."""
        async with self._lock:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if self._exchange is not None and loop is not None:
                ex_loop = getattr(self._exchange, "asyncio_loop", None) or getattr(self._exchange, "loop", None)
                if ex_loop is not None and (ex_loop.is_closed() or ex_loop is not loop):
                    self._exchange = None

            if self._exchange is None:
                config = self._build_exchange_config()
                if loop is not None:
                    config["asyncio_loop"] = loop
                self._exchange = ccxt.binanceusdm(config)
                self._apply_sandbox_mode(self._exchange, self.testnet)
            return self._exchange

    async def get_ws_exchange(self) -> ccxtpro.binanceusdm:
        """Get or initialize the CCXT Pro WebSocket client instance (thread-safe)."""
        async with self._lock:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if self._ws_exchange is not None and loop is not None:
                ex_loop = getattr(self._ws_exchange, "asyncio_loop", None) or getattr(self._ws_exchange, "loop", None)
                if ex_loop is not None and (ex_loop.is_closed() or ex_loop is not loop):
                    self._ws_exchange = None

            if self._ws_exchange is None:
                config = self._build_exchange_config()
                if loop is not None:
                    config["asyncio_loop"] = loop
                self._ws_exchange = ccxtpro.binanceusdm(config)
                self._apply_sandbox_mode(self._ws_exchange, self.testnet)
            return self._ws_exchange

    def _translate_exception(self, exc: Exception, operation: str = "") -> Exception:
        """Translate CCXT raw exceptions into Domain exceptions."""
        if isinstance(exc, ccxt.AuthenticationError):
            logger.error("Binance Auth Error in %s: %s", operation, exc)
            return ExchangeAuthError(f"Binance authentication failed: {exc}")
        elif isinstance(exc, ccxt.InsufficientFunds):
            logger.error("Binance Insufficient Funds in %s: %s", operation, exc)
            return InsufficientMarginError(f"Insufficient account margin: {exc}")
        elif isinstance(exc, (ccxt.RateLimitExceeded, ccxt.DDoSProtection)):
            logger.warning("Binance Rate Limit in %s: %s", operation, exc)
            return RateLimitError(f"Exchange rate limit exceeded: {exc}")
        elif isinstance(exc, (ccxt.NetworkError, ccxt.RequestTimeout, asyncio.TimeoutError)):
            logger.warning("Binance Network Error in %s: %s", operation, exc)
            return ExchangeNetworkError(f"Network error communicating with Binance: {exc}")
        elif isinstance(exc, (ccxt.InvalidOrder, ccxt.OrderNotFound, ccxt.OrderImmediatelyFillable)):
            logger.error("Binance Order Reject in %s: %s", operation, exc)
            return OrderRejectError(f"Binance rejected operation: {exc}")
        elif isinstance(exc, ccxt.ExchangeError):
            logger.error("Binance Exchange Error in %s: %s", operation, exc)
            return OrderRejectError(f"Binance rejected operation: {exc}")
        else:
            logger.exception("Unexpected error in Binance connector (%s): %s", operation, exc)
            return ExchangeError(f"Unexpected exchange error: {exc}")

    async def execute_rest(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Execute a raw CCXT REST call with automatic domain exception translation."""
        exchange = await self.get_rest_exchange()

        # Handle specific methods that may map to Binance-specific private endpoints
        if method_name == "fetch_leverage_brackets":
            return await self.fetch_leverage_brackets(*args, **kwargs)

        func = getattr(exchange, method_name, None)
        if not func:
            raise AttributeError(f"CCXT BinanceUSDM has no method '{method_name}'")

        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            raise self._translate_exception(exc, method_name) from exc

    async def fetch_instruments_metadata(self) -> List[Dict[str, Any]]:
        """Fetch all active USDT-M perpetual contracts and precision parameters from Binance."""
        try:
            exchange = await self.get_rest_exchange()
            if not getattr(exchange, "markets", None):
                await exchange.load_markets()

            results: List[Dict[str, Any]] = []
            markets = exchange.markets or {}
            for symbol, market in markets.items():
                if market.get("active") and market.get("linear") and market.get("quote") == "USDT":
                    info = market.get("info", {})
                    filters = {f.get("filterType"): f for f in info.get("filters", [])}
                    price_filter = filters.get("PRICE_FILTER", {})
                    lot_filter = filters.get("LOT_SIZE", {})
                    min_notional_filter = filters.get("MIN_NOTIONAL", {})

                    price_prec = info.get("pricePrecision") or market.get("precision", {}).get("price")
                    qty_prec = info.get("quantityPrecision") or market.get("precision", {}).get("amount")

                    price_limit_min = market.get("limits", {}).get("price", {}).get("min")
                    amount_limit_min = market.get("limits", {}).get("amount", {}).get("min")

                    tick_size_str = price_filter.get("tickSize") or str(price_limit_min or "0.01")
                    step_size_str = lot_filter.get("stepSize") or str(amount_limit_min or "0.001")
                    min_qty_str = lot_filter.get("minQty") or str(amount_limit_min or step_size_str)
                    min_notional_str = min_notional_filter.get("notional") or str(
                        market.get("limits", {}).get("cost", {}).get("min", "5.0")
                    )

                    tick_dec = Decimal(str(tick_size_str)) if tick_size_str and Decimal(str(tick_size_str)) > 0 else Decimal("0.01")
                    step_dec = Decimal(str(step_size_str)) if step_size_str and Decimal(str(step_size_str)) > 0 else Decimal("0.001")
                    min_qty_dec = Decimal(str(min_qty_str)) if min_qty_str and Decimal(str(min_qty_str)) > 0 else step_dec
                    min_notional_dec = Decimal(str(min_notional_str)) if min_notional_str and Decimal(str(min_notional_str)) > 0 else Decimal("5.0")

                    if price_prec is not None:
                        price_precision = int(price_prec)
                    else:
                        price_exp = tick_dec.normalize().as_tuple().exponent
                        price_precision = abs(price_exp) if isinstance(price_exp, int) else 2

                    if qty_prec is not None:
                        qty_precision = int(qty_prec)
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
        except Exception as exc:
            raise self._translate_exception(exc, "fetch_instruments_metadata") from exc

    async def fetch_leverage_brackets(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch tiered leverage and notional brackets from Binance Futures via fapiPrivateGetLeverageBracket."""
        try:
            exchange = await self.get_rest_exchange()
            params: Dict[str, Any] = {}
            if symbol:
                clean_sym = symbol.replace("/", "").replace(":USDT", "").upper()
                params["symbol"] = clean_sym

            if hasattr(exchange, "fapiPrivateGetLeverageBracket"):
                raw_data = await exchange.fapiPrivateGetLeverageBracket(params)
            else:
                raw_data = await exchange.fetch_leverage_tiers(symbol)

            if isinstance(raw_data, dict):
                raw_data = [raw_data]

            results: List[Dict[str, Any]] = []
            max_safe_cap = Decimal("9999999999")  # Prevent NUMERIC(18, 8) overflow on infinity caps
            for item in (raw_data or []):
                sym = item.get("symbol", "").replace("/", "").replace(":USDT", "").upper()
                brackets_parsed = []
                for b in item.get("brackets", []):
                    raw_cap = Decimal(str(b.get("notionalCap", 0)))
                    capped_val = min(raw_cap, max_safe_cap)
                    b_bracket = b.get("bracket")
                    b_lev = b.get("initialLeverage")
                    brackets_parsed.append({
                        "bracket": int(b_bracket) if b_bracket is not None else 1,
                        "initial_leverage": int(b_lev) if b_lev is not None else 20,
                        "notional_cap": capped_val,
                        "notional_floor": Decimal(str(b.get("notionalFloor") or 0)),
                        "maint_margin_ratio": Decimal(str(b.get("maintMarginRatio") or "0.01")),
                        "cum": Decimal(str(b.get("cum") or 0)),
                    })
                results.append({
                    "symbol": sym,
                    "brackets": brackets_parsed,
                })

            return results
        except Exception as exc:
            raise self._translate_exception(exc, f"fetch_leverage_brackets({symbol})") from exc

    async def close(self) -> None:
        """Gracefully close all active CCXT connections."""
        async with self._lock:
            if self._exchange:
                try:
                    await self._exchange.close()
                except Exception as exc:
                    logger.warning("Error closing CCXT REST exchange: %s", exc)
                self._exchange = None

            if self._ws_exchange:
                try:
                    await self._ws_exchange.close()
                except Exception as exc:
                    logger.warning("Error closing CCXT Pro WS exchange: %s", exc)
                self._ws_exchange = None

    async def watch_orders_stream(self, callback_coro: Any) -> None:
        """Subscribe and stream live order fill status updates using CCXT Pro WebSocket."""
        if not self.api_key or not self.secret_key:
            logger.info("BinanceConnector: No API credentials configured for WebSocket order stream. Exiting stream task.")
            return

        logger.info("BinanceConnector: CCXT Pro User Data Stream WebSocket listener active.")
        while True:
            try:
                ws = await self.get_ws_exchange()
                orders = await ws.watch_orders()
                if orders:
                    for order in orders:
                        if order is not None:
                            await callback_coro(order)
            except asyncio.CancelledError:
                logger.info("BinanceConnector: watch_orders_stream cancelled.")
                break
            except Exception as e:
                err_str = str(e)
                if "1002" in err_str or "reserved bits" in err_str:
                    logger.info("Binance WS stream frame reset (1002). Re-establishing stream in 3s...")
                elif "AuthenticationError" in err_str or "API-key" in err_str:
                    logger.warning("Binance WS authentication error: %s. Reconnecting in 5s...", e)
                    await asyncio.sleep(2)
                else:
                    logger.warning("Binance WS watch_orders error: %s. Reconnecting in 3s...", e)
                try:
                    if self._ws_exchange:
                        await self._ws_exchange.close()
                except Exception:
                    pass
                self._ws_exchange = None
                await asyncio.sleep(3)

