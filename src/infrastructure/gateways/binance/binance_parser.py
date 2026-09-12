"""Parser for normalizing raw CCXT Binance Futures response dictionaries into domain structures."""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from src.domain.value_objects.symbol import Symbol
from src.domain.value_objects.side import OrderSide, PositionSide, MarginMode
from src.domain.value_objects.trade_status import OrderStatus, OrderType


class BinanceParser:
    """Transforms CCXT unified dictionaries into structured and validated domain payloads."""

    @staticmethod
    def to_ccxt_symbol(symbol: str) -> str:
        """Convert clean symbol 'BTCUSDT' into CCXT USDM Futures pair 'BTC/USDT:USDT'."""
        clean = Symbol.normalize(symbol)
        base = clean[:-4] if clean.endswith("USDT") else clean
        quote = "USDT"
        return f"{base}/{quote}:{quote}"

    @staticmethod
    def from_ccxt_symbol(ccxt_symbol: str) -> str:
        """Convert CCXT pair 'BTC/USDT:USDT' into normalized 'BTCUSDT'."""
        return Symbol.normalize(ccxt_symbol)

    @classmethod
    def parse_balance(cls, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Parse raw CCXT fetch_balance dictionary."""
        info = raw.get("info", {})
        usdt_asset = raw.get("USDT", {})

        total_wallet = Decimal(str(usdt_asset.get("total") or info.get("totalWalletBalance", "0")))
        free_margin = Decimal(str(usdt_asset.get("free") or info.get("availableBalance", "0")))
        used_margin = Decimal(str(usdt_asset.get("used") or info.get("totalMarginBalance", "0")))

        return {
            "total_wallet_balance": total_wallet,
            "free_margin": free_margin,
            "used_margin": used_margin,
            "assets": {
                "USDT": {
                    "total": total_wallet,
                    "free": free_margin,
                    "used": used_margin,
                }
            },
            "raw": raw,
        }

    @classmethod
    def parse_ticker(cls, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Parse raw CCXT fetch_ticker dictionary."""
        return {
            "symbol": cls.from_ccxt_symbol(raw.get("symbol", "")),
            "last_price": Decimal(str(raw.get("last") or raw.get("close") or "0")),
            "bid": Decimal(str(raw.get("bid") or raw.get("last") or "0")),
            "ask": Decimal(str(raw.get("ask") or raw.get("last") or "0")),
            "high": Decimal(str(raw.get("high") or "0")),
            "low": Decimal(str(raw.get("low") or "0")),
            "volume": Decimal(str(raw.get("baseVolume") or "0")),
            "timestamp": raw.get("timestamp"),
        }

    @classmethod
    def parse_order(cls, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Parse raw CCXT create_order / fetch_order dictionary."""
        status_str = str(raw.get("status", "open")).upper()
        if status_str in ("CLOSED", "FILLED"):
            ord_status = OrderStatus.FILLED
        elif status_str in ("PARTIALLY_FILLED", "PARTIAL"):
            ord_status = OrderStatus.PARTIALLY_FILLED
        elif status_str in ("CANCELED", "CANCELLED"):
            ord_status = OrderStatus.CANCELED
        elif status_str == "EXPIRED":
            ord_status = OrderStatus.EXPIRED
        elif status_str == "REJECTED":
            ord_status = OrderStatus.REJECTED
        else:
            ord_status = OrderStatus.NEW

        side_raw = str(raw.get("side", "BUY") or "BUY").upper()
        type_raw = str(raw.get("type", "LIMIT") or "LIMIT").upper()
        try:
            ord_type = OrderType.from_str(type_raw)
        except Exception:
            ord_type = OrderType.MARKET

        fee_info = raw.get("fee") or {}
        fee_cost = Decimal(str(fee_info.get("cost", "0"))) if fee_info else Decimal("0")
        fee_currency = fee_info.get("currency", "USDT") if fee_info else "USDT"

        return {
            "exchange_order_id": str(raw.get("id", "")),
            "client_order_id": str(raw.get("clientOrderId", "")),
            "symbol": cls.from_ccxt_symbol(raw.get("symbol", "")),
            "side": OrderSide.from_str(side_raw),
            "order_type": ord_type,
            "status": ord_status,
            "price": Decimal(str(raw.get("price") or "0")) if raw.get("price") else None,
            "qty": Decimal(str(raw.get("amount") or "0")),
            "filled_qty": Decimal(str(raw.get("filled") or "0")),
            "remaining_qty": Decimal(str(raw.get("remaining") or "0")),
            "avg_price": Decimal(str(raw.get("average") or "0")) if raw.get("average") else None,
            "fee": fee_cost,
            "fee_currency": fee_currency,
            "raw": raw,
        }

    @classmethod
    def parse_position(cls, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Parse raw CCXT position dictionary."""
        contracts = Decimal(str(raw.get("contracts") or "0"))
        entry_price = Decimal(str(raw.get("entryPrice") or "0"))
        unrealized_pnl = Decimal(str(raw.get("unrealizedPnl") or "0"))
        liq_price = Decimal(str(raw.get("liquidationPrice") or "0")) if raw.get("liquidationPrice") else None
        leverage = int(raw.get("leverage") or 1)

        side_str = str(raw.get("side", "long")).upper()
        pos_side = PositionSide.LONG if side_str == "LONG" or (contracts > 0 and side_str != "SHORT") else PositionSide.SHORT

        margin_mode_str = str(raw.get("marginMode") or raw.get("marginType") or "isolated").upper()
        margin_mode = MarginMode.ISOLATED if "ISO" in margin_mode_str else MarginMode.CROSSED

        return {
            "symbol": cls.from_ccxt_symbol(raw.get("symbol", "")),
            "position_side": pos_side,
            "contracts": contracts,
            "entry_price": entry_price,
            "unrealized_pnl": unrealized_pnl,
            "liquidation_price": liq_price,
            "leverage": leverage,
            "margin_mode": margin_mode,
            "raw": raw,
        }

    @classmethod
    def parse_leverage_brackets(cls, raw: Any) -> List[Dict[str, Any]]:
        """Parse raw Binance leverage brackets into standardized tier list."""
        brackets: List[Dict[str, Any]] = []
        items = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) else [])

        for item in items:
            symbol = cls.from_ccxt_symbol(item.get("symbol", ""))
            tiers = item.get("brackets") or [item]
            for tier_idx, t in enumerate(tiers, start=1):
                b_id = t.get("bracket_id") or t.get("bracket", tier_idx)
                init_lev = t.get("initial_leverage") or t.get("initialLeverage", 20)
                max_nom = t.get("max_nominal_value") or t.get("notional_cap") or t.get("notionalCap", 50000)
                maint_ratio = t.get("maint_margin_ratio") or t.get("maintMarginRatio", 0.01)
                cum_fast = t.get("cum_fast_deficit") or t.get("cum", 0)

                brackets.append({
                    "symbol": symbol,
                    "bracket_id": int(b_id),
                    "initial_leverage": int(init_lev),
                    "max_nominal_value": Decimal(str(max_nom)),
                    "maint_margin_ratio": Decimal(str(maint_ratio)),
                    "cum_fast_deficit": Decimal(str(cum_fast)),
                })
        return brackets

