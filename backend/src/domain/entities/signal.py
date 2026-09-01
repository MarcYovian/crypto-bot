import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Dict, Any


@dataclass
class SignalTargetDTO:
    """Take profit target specification."""
    target_number: int
    price: Decimal
    allocation_percent: Optional[Decimal] = None


@dataclass
class ParsedSignalDTO:
    """Structured data transfer object representing a parsed Telegram signal."""
    raw_text: str
    symbol: str
    side: str  # "BUY" or "SELL"
    id: Optional[int] = None
    order_type: str = "LIMIT"  # "MARKET" or "LIMIT"
    entry_min: Decimal = Decimal("0")
    entry_max: Decimal = Decimal("0")
    entry_targets: List[Decimal] = field(default_factory=list)
    sl_price: Decimal = Decimal("0")
    tp_targets: List[Decimal] = field(default_factory=list)
    leverage: Optional[int] = None
    timeframe: Optional[str] = None
    pattern: Optional[str] = None
    notes: Optional[str] = None
    confidence_score: float = 1.0
    is_valid: bool = True
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    trace_id: str = field(default_factory=lambda: f"sig-{uuid.uuid4().hex[:8]}")

    @property
    def avg_entry_price(self) -> Decimal:
        """Calculate average expected entry price."""
        if self.entry_targets:
            return sum(self.entry_targets) / Decimal(str(len(self.entry_targets)))
        if self.entry_min > 0 and self.entry_max > 0:
            return (self.entry_min + self.entry_max) / Decimal("2")
        return self.entry_min or self.entry_max

    def to_dict(self) -> Dict[str, Any]:
        """Convert DTO to clean dictionary representation excluding raw_text."""
        d = asdict(self)
        d.pop("raw_text", None)
        return d

    def to_json(self) -> str:
        """Serialize DTO to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], raw_text: str = "") -> "ParsedSignalDTO":
        """Reconstruct ParsedSignalDTO from dictionary with strict Decimal type conversion."""
        entry_targets: List[Decimal] = []
        for p in data.get("entry_targets", []):
            if p is not None and str(p).strip() != "":
                try:
                    entry_targets.append(Decimal(str(p)))
                except (InvalidOperation, TypeError, ValueError):
                    pass

        tp_targets: List[Decimal] = []
        raw_tps = data.get("tp_targets") or data.get("tp_prices") or []
        for p in raw_tps:
            if p is not None and str(p).strip() != "":
                try:
                    tp_targets.append(Decimal(str(p)))
                except (InvalidOperation, TypeError, ValueError):
                    pass

        try:
            entry_min = Decimal(str(data.get("entry_min", "0"))) if data.get("entry_min") is not None else Decimal("0")
        except (InvalidOperation, TypeError, ValueError):
            entry_min = Decimal("0")

        try:
            entry_max = Decimal(str(data.get("entry_max", "0"))) if data.get("entry_max") is not None else Decimal("0")
        except (InvalidOperation, TypeError, ValueError):
            entry_max = Decimal("0")

        try:
            sl_price = Decimal(str(data.get("sl_price", "0"))) if data.get("sl_price") is not None else Decimal("0")
        except (InvalidOperation, TypeError, ValueError):
            sl_price = Decimal("0")

        lev_val = data.get("leverage")
        leverage: Optional[int] = None
        if lev_val is not None and str(lev_val).strip() != "":
            try:
                leverage = int(lev_val)
            except (ValueError, TypeError):
                leverage = None

        conf_val = data.get("confidence_score")
        if conf_val is None:
            conf_val = data.get("confidence", 1.0)
        try:
            confidence_score = float(conf_val) if conf_val is not None else 1.0
        except (ValueError, TypeError):
            confidence_score = 1.0

        created_at = None
        if data.get("created_at"):
            try:
                if isinstance(data["created_at"], datetime):
                    created_at = data["created_at"]
                else:
                    created_at = datetime.fromisoformat(str(data["created_at"]))
            except Exception:
                created_at = None

        return cls(
            raw_text=raw_text or data.get("raw_text", "JSON_RESTORED_SIGNAL"),
            symbol=str(data.get("symbol", "")).upper(),
            side=str(data.get("side", "")).upper(),
            order_type=str(data.get("order_type", "LIMIT")).upper(),
            entry_min=entry_min,
            entry_max=entry_max,
            entry_targets=entry_targets,
            sl_price=sl_price,
            tp_targets=tp_targets,
            leverage=leverage,
            timeframe=data.get("timeframe"),
            pattern=data.get("pattern"),
            notes=data.get("notes"),
            confidence_score=confidence_score,
            is_valid=bool(data.get("is_valid", True)),
            error_message=data.get("error_message"),
            created_at=created_at,
            trace_id=data.get("trace_id") or f"sig-{uuid.uuid4().hex[:8]}",
        )

    @classmethod
    def from_json(cls, json_str: str, raw_text: str = "") -> "ParsedSignalDTO":
        """Deserialize JSON string back into a structured ParsedSignalDTO."""
        data = json.loads(json_str)
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object, got {type(data)}")
        return cls.from_dict(data, raw_text=raw_text)

