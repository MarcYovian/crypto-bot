import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class ParsedSignal:
    symbol: str
    side: str            # 'BUY' (LONG) atau 'SELL' (SHORT)
    entry_min: float
    entry_max: float
    sl_price: float
    tp_prices: List[float]
    confidence: Optional[float] = None
    raw_text: str = ""
    is_valid: bool = False
    error_message: Optional[str] = None


class SignalParserService:
    """
    Parser Engine berbasis Regex untuk mengekstrak parameter trading
    dari pesan sinyal Telegram.
    """

    # Regex Patterns (Diperbaiki agar presisi)
    SYMBOL_PATTERN = r"(?:#|PAIR\s*:\s*|SYMBOL\s*:\s*)?([A-Z0-9]{2,10}(?:/)?(?:USDT|BUSD|PERP))"
    SIDE_PATTERN = r"(?:POSITION|SIDE|TYPE)?\s*:?\s*(LONG|SHORT|BUY|SELL)"
    
    # Matching entry: Mendukung "BUY:", "ENTRY:", "ENTRY ZONE:", dengan emoji opsional
    ENTRY_PATTERN = r"(?:BUY|ENTRY(?:\s*ZONE)?|ENTRIES|PRICE)\s*:?\s*(\d+(?:\.\d+)?)(?:\s*(?:-|TO|/)\s*(\d+(?:\.\d+)?))?"
    
    SL_PATTERN = r"(?:STOP\s*LOSS|SL)\s*:?\s*(\d+(?:\.\d+)?)"
    TP_PATTERN = r"(?:TAKE\s*PROFIT|TARGET|TP)\s*(?:\d+)?\s*:?\s*(\d+(?:\.\d+)?)"
    
    # Mendukung "Confidence Score (AI): 72%", "Confidence: 88%", dll.
    CONFIDENCE_PATTERN = r"(?:CONFIDENCE(?:\s*SCORE)?(?:\s*\(.*?\))?|ACCURACY|WINRATE)\s*:?\s*(\d+(?:\.\d+)?)\s*%?"

    @classmethod
    def parse(cls, raw_text: str) -> ParsedSignal:
        text_upper = raw_text.upper()

        # 1. Extract Symbol
        symbol_match = re.search(cls.SYMBOL_PATTERN, text_upper)
        if not symbol_match:
            return ParsedSignal(
                symbol="", side="", entry_min=0, entry_max=0, sl_price=0, tp_prices=[],
                raw_text=raw_text, is_valid=False, error_message="Symbol/Pair tidak ditemukan"
            )
        
        symbol = symbol_match.group(1).replace("/", "")
        if not symbol.endswith("USDT"):
            # Normalize ke USDT standar
            symbol = symbol.replace("PERP", "").replace("BUSD", "") + "USDT"

        # 2. Extract Side (LONG/BUY -> BUY, SHORT/SELL -> SELL)
        side_match = re.search(cls.SIDE_PATTERN, text_upper)
        if not side_match:
            return ParsedSignal(
                symbol=symbol, side="", entry_min=0, entry_max=0, sl_price=0, tp_prices=[],
                raw_text=raw_text, is_valid=False, error_message="Side (LONG/SHORT) tidak ditemukan"
            )
        
        raw_side = side_match.group(1)
        side = "BUY" if raw_side in ["LONG", "BUY"] else "SELL"

        # 3. Extract Entry Prices
        entry_match = re.search(cls.ENTRY_PATTERN, text_upper)
        if not entry_match:
            return ParsedSignal(
                symbol=symbol, side=side, entry_min=0, entry_max=0, sl_price=0, tp_prices=[],
                raw_text=raw_text, is_valid=False, error_message="Entry Price tidak ditemukan"
            )
        
        e1 = float(entry_match.group(1))
        e2 = float(entry_match.group(2)) if entry_match.group(2) else e1
        entry_min, entry_max = min(e1, e2), max(e1, e2)

        # 4. Extract Stop Loss
        sl_match = re.search(cls.SL_PATTERN, text_upper)
        if not sl_match:
            return ParsedSignal(
                symbol=symbol, side=side, entry_min=entry_min, entry_max=entry_max, sl_price=0, tp_prices=[],
                raw_text=raw_text, is_valid=False, error_message="Stop Loss tidak ditemukan"
            )
        sl_price = float(sl_match.group(1))

        # 5. Extract Take Profits (Multiple Matches)
        tp_matches = re.findall(cls.TP_PATTERN, text_upper)
        if not tp_matches:
            return ParsedSignal(
                symbol=symbol, side=side, entry_min=entry_min, entry_max=entry_max, sl_price=sl_price, tp_prices=[],
                raw_text=raw_text, is_valid=False, error_message="Take Profit tidak ditemukan"
            )
        
        tp_prices = [float(tp) for tp in tp_matches]

        # 6. Extract Confidence (Optional)
        confidence = None
        conf_match = re.search(cls.CONFIDENCE_PATTERN, text_upper)
        if conf_match:
            val = float(conf_match.group(1))
            confidence = val / 100.0 if val > 1.0 else val

        # Validasi Logika Trading Dasar
        if side == "BUY" and sl_price >= entry_min:
            return ParsedSignal(
                symbol=symbol, side=side, entry_min=entry_min, entry_max=entry_max, sl_price=sl_price, tp_prices=tp_prices,
                raw_text=raw_text, is_valid=False, error_message="Invalid SL: Untuk BUY, SL harus di bawah Entry"
            )
        elif side == "SELL" and sl_price <= entry_max:
            return ParsedSignal(
                symbol=symbol, side=side, entry_min=entry_min, entry_max=entry_max, sl_price=sl_price, tp_prices=tp_prices,
                raw_text=raw_text, is_valid=False, error_message="Invalid SL: Untuk SELL, SL harus di atas Entry"
            )

        return ParsedSignal(
            symbol=symbol,
            side=side,
            entry_min=entry_min,
            entry_max=entry_max,
            sl_price=sl_price,
            tp_prices=tp_prices,
            confidence=confidence,
            raw_text=raw_text,
            is_valid=True
        )