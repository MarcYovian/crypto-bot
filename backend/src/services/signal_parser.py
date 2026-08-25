"""Telegram signal parser service supporting multiple channel formats."""

import re
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Tuple
from src.domain.entities.signal import ParsedSignalDTO
from src.domain.exceptions.signal import SignalParseError, InvalidSignalDataError


class SignalParserService:
    """Service for parsing raw Telegram signals into structured ParsedSignalDTO."""

    # Regex Patterns for Symbols
    SYMBOL_PATTERN = re.compile(
        r"(?:#|PAIR:\s*|COIN:\s*|SYMBOL:\s*)?([A-Z0-9]{2,10}(?:/|-|_)?[A-Z0-9]{2,6}(?:\.P)?)",
        re.IGNORECASE,
    )
    # Direction / Side Patterns
    SIDE_PATTERN = re.compile(
        r"\b(BUY|LONG|SELL|SHORT)\b",
        re.IGNORECASE,
    )
    # Entry Patterns
    ENTRY_ZONE_PATTERN = re.compile(
        r"(?:ENTRY\s*(?:ZONE|RANGE|TARGETS?|PRICE)?|\bENTRIES|\bBUY\s*AROUND|\bSELL\s*AROUND)[:\s]*([0-9.,]+)(?:\s*(?:-|–|—|TO|\/)\s*([0-9.,]+))?",
        re.IGNORECASE,
    )
    # Stop Loss Patterns
    SL_PATTERN = re.compile(
        r"(?:STOP\s*LOSS|STOPLOSS|\bSL|\bSTOP)[:\s]*([0-9.,]+)",
        re.IGNORECASE,
    )
    # Take Profit Patterns
    TP_PATTERN = re.compile(
        r"(?:TP|TARGET|TAKE\s*PROFIT)\s*\d*[:\s]*([0-9.,]+)",
        re.IGNORECASE,
    )
    TP_TARGETS_LIST_PATTERN = re.compile(
        r"(?:TARGETS|TPS|TAKE\s*PROFITS?)[:\s]*((?:[0-9.,]+(?:\s*[-–—,\/]\s*|\s+))+[0-9.,]+)",
        re.IGNORECASE,
    )
    # Leverage Pattern
    LEVERAGE_PATTERN = re.compile(
        r"(?:LEVERAGE|LEV)[:\s]*(?:CROSS|ISOLATED)?\s*(\d+)x?",
        re.IGNORECASE,
    )

    def parse(self, raw_text: str, strict: bool = False) -> ParsedSignalDTO:
        """Parse raw signal string into ParsedSignalDTO.
        
        Args:
            raw_text: Raw message string from Telegram.
            strict: If True, raises SignalParseError on failure instead of returning invalid DTO.
            
        Returns:
            ParsedSignalDTO with extraction results and validation status.
        """
        clean_text = raw_text.strip()
        if not clean_text:
            if strict:
                raise SignalParseError("Empty signal text", raw_text=raw_text)
            return ParsedSignalDTO(raw_text=raw_text, symbol="", side="", is_valid=False, error_message="Empty signal text")

        symbol = self._extract_symbol(clean_text)
        side = self._extract_side(clean_text)
        entry_min, entry_max, entry_targets = self._extract_entries(clean_text)
        sl_price = self._extract_stop_loss(clean_text)
        tp_targets = self._extract_take_profits(clean_text)
        leverage = self._extract_leverage(clean_text)

        # Basic presence validation
        missing: List[str] = []
        if not symbol:
            missing.append("symbol")
        if not side:
            missing.append("side")
        if entry_min <= Decimal("0") and entry_max <= Decimal("0"):
            missing.append("entry_price")
        if sl_price <= Decimal("0"):
            missing.append("stop_loss")
        if not tp_targets:
            missing.append("take_profit")

        if missing:
            msg = f"Missing required signal fields: {', '.join(missing)}"
            if strict:
                raise SignalParseError(msg, raw_text=raw_text)
            return ParsedSignalDTO(
                raw_text=raw_text,
                symbol=symbol or "",
                side=side or "",
                entry_min=entry_min,
                entry_max=entry_max,
                entry_targets=entry_targets,
                sl_price=sl_price,
                tp_targets=tp_targets,
                leverage=leverage,
                is_valid=False,
                error_message=msg,
                confidence_score=0.0,
            )

        # Logical price consistency validation
        is_valid, validation_err = self._validate_price_logic(str(side), entry_min, entry_max, sl_price, tp_targets)
        if not is_valid and strict:
            raise InvalidSignalDataError(validation_err or "Invalid price logic", raw_text=raw_text)

        assert symbol is not None and side is not None
        confidence = self._compute_confidence(symbol, side, entry_min, sl_price, tp_targets, leverage)

        return ParsedSignalDTO(
            raw_text=raw_text,
            symbol=symbol,
            side=side,
            order_type="LIMIT" if (entry_min != entry_max or len(entry_targets) > 1) else "MARKET",
            entry_min=entry_min,
            entry_max=entry_max,
            entry_targets=entry_targets,
            sl_price=sl_price,
            tp_targets=tp_targets,
            leverage=leverage,
            confidence_score=confidence,
            is_valid=is_valid,
            error_message=validation_err,
        )

    def _extract_symbol(self, text: str) -> Optional[str]:
        """Extract and normalize trading pair symbol to standard format (e.g. BTCUSDT)."""
        # Look for explicit lines like "PAIR: BTC/USDT" or "#BTC/USDT"
        lines = text.splitlines()
        for line in lines:
            match = re.search(r"(?:#|PAIR:\s*|COIN:\s*|SYMBOL:\s*)([A-Z0-9]{2,10}(?:/|-|_)?[A-Z0-9]{2,6}(?:\.P)?)", line, re.IGNORECASE)
            if match:
                raw_sym = match.group(1).upper()
                return self._normalize_symbol(raw_sym)

        # Fallback to general text search
        match = self.SYMBOL_PATTERN.search(text)
        if match:
            raw_sym = match.group(1).upper()
            return self._normalize_symbol(raw_sym)
        return None

    def _normalize_symbol(self, raw_symbol: str) -> str:
        """Normalize symbol string."""
        sym = raw_symbol.replace("#", "").replace("/", "").replace("-", "").replace("_", "").replace(".P", "").replace(":USDT", "")
        # If symbol does not end with quote asset (USDT, BUSD, USDC), append USDT
        if not (sym.endswith("USDT") or sym.endswith("BUSD") or sym.endswith("USDC")):
            sym += "USDT"
        return sym

    def _extract_side(self, text: str) -> Optional[str]:
        """Extract trade direction (BUY / SELL)."""
        match = self.SIDE_PATTERN.search(text)
        if match:
            direction = match.group(1).upper()
            if direction in ("BUY", "LONG"):
                return "BUY"
            if direction in ("SELL", "SHORT"):
                return "SELL"
        return None

    def _extract_entries(self, text: str) -> Tuple[Decimal, Decimal, List[Decimal]]:
        """Extract entry price zone / targets."""
        match = self.ENTRY_ZONE_PATTERN.search(text)
        if match:
            p1_str = match.group(1).replace(",", "")
            p2_str = match.group(2).replace(",", "") if match.group(2) else None
            try:
                p1 = Decimal(p1_str)
                if p2_str:
                    p2 = Decimal(p2_str)
                    e_min = min(p1, p2)
                    e_max = max(p1, p2)
                    return e_min, e_max, [e_min, e_max]
                return p1, p1, [p1]
            except (InvalidOperation, TypeError):
                pass
        return Decimal("0"), Decimal("0"), []

    def _extract_stop_loss(self, text: str) -> Decimal:
        """Extract Stop Loss price."""
        match = self.SL_PATTERN.search(text)
        if match:
            try:
                return Decimal(match.group(1).replace(",", ""))
            except (InvalidOperation, TypeError):
                pass
        return Decimal("0")

    def _extract_take_profits(self, text: str) -> List[Decimal]:
        """Extract Take Profit targets."""
        # Check individual TP lines first (TP1: ..., TP2: ...)
        individual_matches = self.TP_PATTERN.findall(text)
        if individual_matches:
            tps: List[Decimal] = []
            for m in individual_matches:
                try:
                    val = Decimal(m.replace(",", ""))
                    if val not in tps:
                        tps.append(val)
                except (InvalidOperation, TypeError):
                    continue
            if tps:
                return tps

        # Check list format (Targets: 61000 - 62000 - 63000)
        list_match = self.TP_TARGETS_LIST_PATTERN.search(text)
        if list_match:
            raw_list = list_match.group(1)
            parts = re.split(r"[-–—,\/\s]+", raw_list.strip())
            tps = []
            for p in parts:
                try:
                    if p:
                        val = Decimal(p.replace(",", ""))
                        if val not in tps:
                            tps.append(val)
                except (InvalidOperation, TypeError):
                    continue
            if tps:
                return tps

        return []

    def _extract_leverage(self, text: str) -> Optional[int]:
        """Extract recommended leverage multiplier."""
        match = self.LEVERAGE_PATTERN.search(text)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                pass
        return None

    def _validate_price_logic(
        self,
        side: str,
        entry_min: Decimal,
        entry_max: Decimal,
        sl: Decimal,
        tps: List[Decimal],
    ) -> Tuple[bool, Optional[str]]:
        """Validate financial consistency of SL and TP relative to Entry."""
        if side == "BUY":
            if sl >= entry_min:
                return False, f"Invalid BUY logic: Stop Loss ({sl}) must be lower than Entry ({entry_min})"
            for tp in tps:
                if tp <= entry_max:
                    return False, f"Invalid BUY logic: Take Profit ({tp}) must be higher than Entry ({entry_max})"
        elif side == "SELL":
            if sl <= entry_max:
                return False, f"Invalid SELL logic: Stop Loss ({sl}) must be higher than Entry ({entry_max})"
            for tp in tps:
                if tp >= entry_min:
                    return False, f"Invalid SELL logic: Take Profit ({tp}) must be lower than Entry ({entry_min})"

        return True, None

    def _compute_confidence(
        self,
        symbol: Optional[str],
        side: Optional[str],
        entry: Decimal,
        sl: Decimal,
        tps: List[Decimal],
        leverage: Optional[int],
    ) -> float:
        """Calculate confidence score of extracted signal."""
        score = 0.0
        if symbol:
            score += 0.2
        if side:
            score += 0.2
        if entry > 0:
            score += 0.2
        if sl > 0:
            score += 0.2
        if tps:
            score += 0.15
        if leverage:
            score += 0.05
        return round(score, 2)