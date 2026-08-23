"""Pydantic schemas for Trading Signals and Telegram parsed payloads."""

from decimal import Decimal
from typing import Optional, List
from pydantic import Field, field_validator, model_validator
from src.schemas.common import BaseSchema, TimestampMixin


class ParsedSignalDTO(BaseSchema):
    """Data Transfer Object representing a raw signal parsed from Telegram/Webhook.
    
    Includes comprehensive business logic validation for price zones and risk boundaries.
    """
    symbol: str = Field(..., min_length=2, max_length=30, description="Trading pair, e.g. BTCUSDT")
    side: str = Field(..., description="Trade side: BUY or SELL")
    order_type: str = Field(default="LIMIT", description="Order type: MARKET or LIMIT")
    entry_min: Decimal = Field(..., gt=0, description="Lower bound of entry zone")
    entry_max: Decimal = Field(..., gt=0, description="Upper bound of entry zone")
    entry_targets: List[Decimal] = Field(default_factory=list, description="Explicit entry target prices")
    sl_price: Decimal = Field(..., gt=0, description="Stop Loss price")
    tp_prices: List[Decimal] = Field(default_factory=list, description="Target Take Profit prices")
    tp_targets: List[Decimal] = Field(default_factory=list, description="Target Take Profit prices alias")
    leverage: Optional[int] = Field(default=None, ge=1, le=125, description="Requested leverage multiplier")
    confidence: Optional[Decimal] = Field(default=None, ge=0, le=1, description="Confidence score (0.0 to 1.0)")
    confidence_score: float = Field(default=1.0, description="Float confidence score alias")
    raw_text: str = Field(default="", description="Original unparsed text message")
    is_valid: bool = Field(default=True, description="Whether signal parsing passed checks")
    error_message: Optional[str] = Field(default=None, description="Reason if parsing/validation failed")

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        val = v.strip().upper()
        if val not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        return val

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="after")
    def validate_price_boundaries(self) -> "ParsedSignalDTO":
        if self.entry_min > self.entry_max:
            raise ValueError(f"entry_min ({self.entry_min}) cannot be greater than entry_max ({self.entry_max})")

        if self.side == "BUY" and self.sl_price >= self.entry_min:
            raise ValueError(f"For BUY signal, sl_price ({self.sl_price}) must be lower than entry_min ({self.entry_min})")

        if self.side == "SELL" and self.sl_price <= self.entry_max:
            raise ValueError(f"For SELL signal, sl_price ({self.sl_price}) must be higher than entry_max ({self.entry_max})")

        return self


class TradingSignalBase(BaseSchema):
    """Base fields for TradingSignal entity."""
    provider_id: int = Field(..., gt=0, description="FK to signal_providers table")
    instrument_id: int = Field(..., gt=0, description="FK to instruments table")
    telegram_message_id: Optional[int] = Field(default=None, description="Original Telegram message ID for dedup")
    timeframe: Optional[str] = Field(default=None, max_length=10, description="Timeframe, e.g. 15m, 1h")
    side: str = Field(..., description="BUY or SELL")
    entry_min: Optional[Decimal] = Field(default=None, gt=0)
    entry_max: Optional[Decimal] = Field(default=None, gt=0)
    sl_price: Decimal = Field(..., gt=0, description="Stop Loss price")
    tp1_price: Optional[Decimal] = Field(default=None, gt=0)
    tp2_price: Optional[Decimal] = Field(default=None, gt=0)
    tp3_price: Optional[Decimal] = Field(default=None, gt=0)
    confidence: Optional[Decimal] = Field(default=None, ge=0, le=1)
    raw_message: Optional[str] = None
    parsed_json: Optional[str] = None
    status: str = Field(default="RECEIVED", description="RECEIVED, EXECUTED, REJECTED, CANCELLED, EXPIRED")
    confirmation_status: str = Field(default="NOT_REQUIRED", description="NOT_REQUIRED, PENDING, APPROVED, REJECTED")


class TradingSignalCreate(TradingSignalBase):
    """Payload for saving a new TradingSignal to the database."""
    pass


class TradingSignalUpdate(BaseSchema):
    """Payload for updating signal status and details."""
    status: Optional[str] = None
    confirmation_status: Optional[str] = None
    parsed_json: Optional[str] = None


class SignalConfirmationDTO(BaseSchema):
    """Payload for user confirmation via Telegram Inline Buttons."""
    signal_id: int = Field(..., gt=0)
    action: str = Field(..., pattern="^(APPROVE|REJECT)$", description="User decision")
    user_id: int = Field(..., description="Telegram user ID taking the action")


class TradingSignalRead(TradingSignalBase, TimestampMixin):
    """Response schema for TradingSignal."""
    id: int
