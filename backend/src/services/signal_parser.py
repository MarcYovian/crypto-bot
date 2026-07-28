"""Regex-based parser for extracting trading signal parameters from Telegram messages."""

import re
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class ParsedSignal:
    """Structured representation of a parsed trading signal.

    Attributes:
        symbol: Trading pair (e.g. ``BTCUSDT``).
        side: ``BUY`` (long) or ``SELL`` (short).
        entry_min: Lower bound of the entry price range.
        entry_max: Upper bound of the entry price range.
        sl_price: Stop-loss price.
        tp_prices: List of take-profit prices.
        confidence: Optional confidence score (0.0 – 1.0).
        raw_text: Original unparsed message text.
        is_valid: Whether the signal passed all parsing and validation rules.
        error_message: Human-readable error description if ``is_valid`` is False.
    """
    symbol: str
    side: str
    entry_min: float
    entry_max: float
    sl_price: float
    tp_prices: List[float]
    confidence: Optional[float] = None
    raw_text: str = ""
    is_valid: bool = False
    error_message: Optional[str] = None


class SignalParserService:
    """Regex-based parser that extracts trading parameters from Telegram signal messages.

    Supports multi-stage extraction: symbol, side, entry zone, stop-loss,
    take-profits, and an optional confidence score.  Basic trading-logic
    validation is performed (SL must be on the correct side of entry).
    """

    #: Match symbol (e.g. ``BTCUSDT``, ``ETH/USDT``, ``SOLPERP``).
    SYMBOL_PATTERN = r"(?:#|PAIR\s*:\s*|SYMBOL\s*:\s*)?([A-Z0-9]{2,10}(?:/)?(?:USDT|BUSD|PERP))"
    #: Match side (LONG/BUY → BUY; SHORT/SELL → SELL).
    SIDE_PATTERN = r"(?:POSITION|SIDE|TYPE)?\s*:?\s*(LONG|SHORT|BUY|SELL)"
    #: Match entry price or price range (e.g. ``ENTRY: 1.2345 - 1.2355``).
    ENTRY_PATTERN = r"(?:BUY|ENTRY(?:\s*ZONE)?|ENTRIES|PRICE)\s*:?\s*(\d+(?:\.\d+)?)(?:\s*(?:-|TO|/)\s*(\d+(?:\.\d+)?))?"
    #: Match stop-loss price.
    SL_PATTERN = r"(?:STOP\s*LOSS|SL)\s*:?\s*(\d+(?:\.\d+)?)"
    #: Match take-profit prices (multiple allowed).
    TP_PATTERN = r"(?:TAKE\s*PROFIT|TARGET|TP)\s*(?:\d+)?\s*:?\s*(\d+(?:\.\d+)?)"
    #: Match optional confidence score (e.g. ``Confidence: 72%``).
    CONFIDENCE_PATTERN = r"(?:CONFIDENCE(?:\s*SCORE)?(?:\s*\(.*?\))?|ACCURACY|WINRATE)\s*:?\s*(\d+(?:\.\d+)?)\s*%?"

    @classmethod
    def parse(cls, raw_text: str) -> ParsedSignal:
        """Parse a raw Telegram message into a structured ``ParsedSignal``.

        Extraction steps:
        1. Symbol (e.g. ``BTCUSDT``)
        2. Side (``LONG`` / ``SHORT`` → ``BUY`` / ``SELL``)
        3. Entry price or zone (``1.2345 - 1.2355``)
        4. Stop-loss price
        5. Take-profit prices (one or more)
        6. Optional confidence score (e.g. ``Confidence: 72%``)

        Basic validation ensures the stop-loss is on the correct side of the
        entry (SL below entry for BUY, above entry for SELL).

        Args:
            raw_text: The raw message text from Telegram.

        Returns:
            A ``ParsedSignal`` with ``is_valid`` set accordingly and an
            ``error_message`` if any extraction or validation step fails.
        """
        text_upper = raw_text.upper()

        # 1. Extract symbol
        symbol_match = re.search(cls.SYMBOL_PATTERN, text_upper)
        if not symbol_match:
            return cls._invalid(raw_text, "Symbol/pair not found")

        symbol = symbol_match.group(1).replace("/", "")
        if not symbol.endswith("USDT"):
            symbol = symbol.replace("PERP", "").replace("BUSD", "") + "USDT"

        # 2. Extract side
        side_match = re.search(cls.SIDE_PATTERN, text_upper)
        if not side_match:
            return cls._invalid(raw_text, "Side (LONG/SHORT) not found", symbol=symbol)
        raw_side = side_match.group(1)
        side = "BUY" if raw_side in ["LONG", "BUY"] else "SELL"

        # 3. Extract entry prices
        entry_match = re.search(cls.ENTRY_PATTERN, text_upper)
        if not entry_match:
            return cls._invalid(raw_text, "Entry price not found", symbol=symbol, side=side)
        e1 = float(entry_match.group(1))
        e2 = float(entry_match.group(2)) if entry_match.group(2) else e1
        entry_min, entry_max = min(e1, e2), max(e1, e2)

        # 4. Extract stop-loss
        sl_match = re.search(cls.SL_PATTERN, text_upper)
        if not sl_match:
            return cls._invalid(raw_text, "Stop-loss not found", symbol=symbol, side=side, entry_min=entry_min, entry_max=entry_max)
        sl_price = float(sl_match.group(1))

        # 5. Extract take-profits
        tp_matches = re.findall(cls.TP_PATTERN, text_upper)
        if not tp_matches:
            return cls._invalid(raw_text, "Take-profit not found", symbol=symbol, side=side, entry_min=entry_min, entry_max=entry_max, sl_price=sl_price)
        tp_prices = [float(tp) for tp in tp_matches]

        # 6. Extract optional confidence
        confidence = None
        conf_match = re.search(cls.CONFIDENCE_PATTERN, text_upper)
        if conf_match:
            val = float(conf_match.group(1))
            confidence = val / 100.0 if val > 1.0 else val

        # 7. Basic trading-logic validation
        if side == "BUY" and sl_price >= entry_min:
            return cls._invalid(raw_text, "For BUY, SL must be below entry", symbol=symbol, side=side, entry_min=entry_min, entry_max=entry_max, sl_price=sl_price, tp_prices=tp_prices)
        if side == "SELL" and sl_price <= entry_max:
            return cls._invalid(raw_text, "For SELL, SL must be above entry", symbol=symbol, side=side, entry_min=entry_min, entry_max=entry_max, sl_price=sl_price, tp_prices=tp_prices)

        return ParsedSignal(
            symbol=symbol, side=side, entry_min=entry_min, entry_max=entry_max,
            sl_price=sl_price, tp_prices=tp_prices, confidence=confidence,
            raw_text=raw_text, is_valid=True
        )

    @classmethod
    def _invalid(cls, raw_text: str, error_message: str, **kwargs) -> ParsedSignal:
        """Build an invalid ``ParsedSignal`` with the given error message."""
        return ParsedSignal(
            symbol=kwargs.get("symbol", ""),
            side=kwargs.get("side", ""),
            entry_min=kwargs.get("entry_min", 0),
            entry_max=kwargs.get("entry_max", 0),
            sl_price=kwargs.get("sl_price", 0),
            tp_prices=kwargs.get("tp_prices", []),
            raw_text=raw_text, is_valid=False, error_message=error_message
        )