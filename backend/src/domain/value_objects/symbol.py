"""Value object representing a cryptocurrency trading pair symbol."""

import re
from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class Symbol:
    """Immutable Value Object for a normalized trading pair (e.g. BTCUSDT, ETHUSDT)."""

    value: str

    def __post_init__(self) -> None:
        raw = str(self.value).strip().upper()
        # Remove common exchange separators (e.g. BTC/USDT, BTC/USDT:USDT, BTC-USDT)
        cleaned = raw.replace("/", "").replace("-", "").replace("_", "")
        if ":" in cleaned:
            cleaned = cleaned.split(":")[0]

        if not cleaned or not re.match(r"^[A-Z0-9]{3,20}$", cleaned):
            raise ValueError(f"Invalid crypto symbol format: '{self.value}' -> '{cleaned}'")

        object.__setattr__(self, "value", cleaned)

    @property
    def quote_asset(self) -> str:
        """Extract quote asset (USDT, BUSD, USDC, BTC, etc.)."""
        for quote in ("USDT", "BUSD", "USDC", "FDUSD", "TUSD", "BTC", "ETH"):
            if self.value.endswith(quote) and len(self.value) > len(quote):
                return quote
        return "USDT"

    @property
    def base_asset(self) -> str:
        """Extract base asset (BTC, ETH, SOL, etc.)."""
        quote = self.quote_asset
        return self.value[: -len(quote)]

    @classmethod
    def from_str(cls, raw: Union[str, "Symbol"]) -> "Symbol":
        if isinstance(raw, Symbol):
            return raw
        return cls(value=str(raw))

    @classmethod
    def normalize(cls, raw: Union[str, "Symbol"]) -> str:
        """Helper to return normalized string (e.g. 'BTC/USDT:USDT' -> 'BTCUSDT')."""
        if isinstance(raw, Symbol):
            return raw.value
        return cls(value=str(raw)).value

    @classmethod
    def to_ccxt_pair(cls, raw: Union[str, "Symbol"]) -> str:
        """Helper to convert to CCXT USDM format (e.g. 'BTCUSDT' -> 'BTC/USDT:USDT')."""
        sym = cls.from_str(raw)
        return f"{sym.base_asset}/{sym.quote_asset}:{sym.quote_asset}"

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"Symbol('{self.value}')"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Symbol):
            return self.value == other.value
        if isinstance(other, str):
            try:
                return self.value == Symbol(other).value
            except ValueError:
                return False
        return False
