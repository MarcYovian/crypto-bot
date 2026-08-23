"""Pydantic schemas for master and configuration entities."""

from decimal import Decimal
from typing import Optional
from pydantic import Field, field_validator
from src.schemas.common import BaseSchema, TimestampMixin


# =====================================================================
# 1. EXCHANGE SCHEMAS
# =====================================================================

class ExchangeBase(BaseSchema):
    """Base fields for Exchange entity."""
    code: str = Field(..., min_length=2, max_length=30, description="Unique exchange code, e.g. BINANCE, BYBIT")
    name: str = Field(..., min_length=2, max_length=100, description="Full human-readable exchange name")
    status: bool = Field(default=True, description="Active status flag")

    @field_validator("code")
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        return v.strip().upper()


class ExchangeCreate(ExchangeBase):
    """Payload for creating a new Exchange."""
    pass


class ExchangeUpdate(BaseSchema):
    """Payload for updating an existing Exchange."""
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    status: Optional[bool] = None


class ExchangeRead(ExchangeBase, TimestampMixin):
    """Response schema for Exchange."""
    id: int


# =====================================================================
# 2. TRADING ACCOUNT SCHEMAS
# =====================================================================

class TradingAccountBase(BaseSchema):
    """Base fields for Trading Account."""
    exchange_id: int = Field(..., gt=0, description="FK to exchanges table")
    name: str = Field(..., min_length=2, max_length=100, description="Account label")
    account_type: str = Field(default="FUTURES", description="Account type, e.g. SPOT, FUTURES")
    environment: str = Field(default="MAINNET", description="MAINNET or TESTNET")
    is_active: bool = Field(default=True, description="Account active status")

    @field_validator("environment")
    @classmethod
    def validate_env(cls, v: str) -> str:
        val = v.strip().upper()
        if val not in ("MAINNET", "TESTNET"):
            raise ValueError("environment must be either MAINNET or TESTNET")
        return val


class TradingAccountCreate(TradingAccountBase):
    """Payload for creating a Trading Account."""
    pass


class TradingAccountUpdate(BaseSchema):
    """Payload for updating a Trading Account."""
    name: Optional[str] = None
    account_type: Optional[str] = None
    environment: Optional[str] = None
    is_active: Optional[bool] = None


class TradingAccountRead(TradingAccountBase, TimestampMixin):
    """Response schema for Trading Account."""
    id: int


# =====================================================================
# 3. TRADING CREDENTIAL SCHEMAS (With Security & Masking)
# =====================================================================

class TradingCredentialBase(BaseSchema):
    """Base fields for API credentials."""
    account_id: int = Field(..., gt=0, description="FK to trading_accounts table")
    key_name: str = Field(..., min_length=2, max_length=100, description="Key label / description")
    key_version: int = Field(default=1, ge=1, description="Key rotation version")
    is_active: bool = Field(default=True, description="Active status flag")


class TradingCredentialCreate(TradingCredentialBase):
    """Payload for creating credentials with plain or pre-encrypted keys."""
    api_key: str = Field(..., min_length=10, description="Raw API key to be encrypted")
    secret_key: str = Field(..., min_length=10, description="Raw Secret key to be encrypted")
    passphrase: Optional[str] = Field(default=None, description="Optional passphrase (for Kucoin, OKX, etc.)")


class TradingCredentialUpdate(BaseSchema):
    """Payload for updating credentials."""
    key_name: Optional[str] = None
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    passphrase: Optional[str] = None
    key_version: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None


class TradingCredentialRead(TradingCredentialBase, TimestampMixin):
    """Safe response schema with masked credentials."""
    id: int
    masked_api_key: Optional[str] = Field(default=None, description="Masked API key (e.g. abcd****1234)")

    @classmethod
    def from_orm_model(cls, obj) -> "TradingCredentialRead":
        masked = None
        if hasattr(obj, "encrypted_api_key") and obj.encrypted_api_key:
            raw = str(obj.encrypted_api_key)
            masked = f"{raw[:4]}****{raw[-4:]}" if len(raw) >= 8 else "****"
        return cls(
            id=obj.id,
            account_id=obj.account_id,
            key_name=obj.key_name,
            key_version=obj.key_version,
            is_active=obj.is_active,
            masked_api_key=masked,
            created_at=getattr(obj, "created_at", None),
            updated_at=getattr(obj, "updated_at", None),
        )


# =====================================================================
# 4. INSTRUMENT SCHEMAS
# =====================================================================

class InstrumentBase(BaseSchema):
    """Base fields for trading instruments/pairs."""
    exchange_id: int = Field(..., gt=0, description="FK to exchanges table")
    symbol: str = Field(..., min_length=2, max_length=30, description="Trading pair, e.g. BTCUSDT")
    base_asset: str = Field(..., min_length=1, max_length=20, description="Base asset, e.g. BTC")
    quote_asset: str = Field(..., min_length=1, max_length=20, description="Quote asset, e.g. USDT")
    tick_size: Decimal = Field(..., gt=0, description="Minimum price movement")
    step_size: Decimal = Field(..., gt=0, description="Minimum quantity movement")
    min_qty: Decimal = Field(..., gt=0, description="Minimum order quantity")
    min_notional: Decimal = Field(..., gt=0, description="Minimum order value (price * qty)")
    price_precision: int = Field(default=2, ge=0, le=10, description="Decimal places for price")
    qty_precision: int = Field(default=3, ge=0, le=10, description="Decimal places for quantity")
    is_active: bool = Field(default=True, description="Active status")

    @field_validator("symbol", "base_asset", "quote_asset")
    @classmethod
    def uppercase_assets(cls, v: str) -> str:
        return v.strip().upper()


class InstrumentCreate(InstrumentBase):
    """Payload for registering a new Instrument."""
    pass


class InstrumentUpdate(BaseSchema):
    """Payload for updating an Instrument."""
    tick_size: Optional[Decimal] = Field(default=None, gt=0)
    step_size: Optional[Decimal] = Field(default=None, gt=0)
    min_qty: Optional[Decimal] = Field(default=None, gt=0)
    min_notional: Optional[Decimal] = Field(default=None, gt=0)
    price_precision: Optional[int] = Field(default=None, ge=0, le=10)
    qty_precision: Optional[int] = Field(default=None, ge=0, le=10)
    is_active: Optional[bool] = None


class InstrumentRead(InstrumentBase):
    """Response schema for Instrument."""
    id: int
    updated_at: Optional[TimestampMixin] = None


# =====================================================================
# 4.1 INSTRUMENT LEVERAGE BRACKET SCHEMAS
# =====================================================================

class InstrumentLeverageBracketBase(BaseSchema):
    """Base fields for Instrument Leverage and Notional Brackets."""
    instrument_id: int = Field(..., gt=0, description="FK to instruments table")
    bracket: int = Field(..., ge=1, description="Tier bracket number (1, 2, 3...)")
    initial_leverage: int = Field(..., ge=1, le=125, description="Max allowable leverage for this bracket")
    notional_cap: Decimal = Field(..., ge=0, description="Max notional value in USDT")
    notional_floor: Decimal = Field(..., ge=0, description="Min notional value in USDT")
    maint_margin_ratio: Decimal = Field(..., gt=0, description="Maintenance margin requirement ratio (MMR)")
    cum: Decimal = Field(default=Decimal("0"), ge=0, description="Cumulative deduction factor")


class InstrumentLeverageBracketCreate(InstrumentLeverageBracketBase):
    """Payload for creating a new leverage bracket."""
    pass


class InstrumentLeverageBracketUpdate(BaseSchema):
    """Payload for updating a leverage bracket."""
    initial_leverage: Optional[int] = Field(default=None, ge=1, le=125)
    notional_cap: Optional[Decimal] = Field(default=None, ge=0)
    notional_floor: Optional[Decimal] = Field(default=None, ge=0)
    maint_margin_ratio: Optional[Decimal] = Field(default=None, gt=0)
    cum: Optional[Decimal] = Field(default=None, ge=0)


class InstrumentLeverageBracketRead(InstrumentLeverageBracketBase):
    """Response schema for Instrument Leverage Bracket."""
    id: int
    updated_at: Optional[TimestampMixin] = None


# =====================================================================
# 5. STRATEGY SCHEMAS
# =====================================================================

class StrategyBase(BaseSchema):
    """Base fields for trading strategy."""
    name: str = Field(..., min_length=2, max_length=100, description="Strategy name")
    version: str = Field(default="1.0.0", min_length=1, max_length=20, description="Strategy version")
    description: Optional[str] = Field(default=None, description="Strategy explanation")
    is_active: bool = Field(default=True, description="Active status")


class StrategyCreate(StrategyBase):
    """Payload for creating a Strategy."""
    pass


class StrategyUpdate(BaseSchema):
    """Payload for updating a Strategy."""
    name: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class StrategyRead(StrategyBase):
    """Response schema for Strategy."""
    id: int
    created_at: Optional[TimestampMixin] = None


# =====================================================================
# 6. SIGNAL PROVIDER SCHEMAS
# =====================================================================

class SignalProviderBase(BaseSchema):
    """Base fields for Signal Provider."""
    name: str = Field(..., min_length=2, max_length=100, description="Provider unique identifier name")
    type: str = Field(default="TELEGRAM", description="Provider type, e.g. TELEGRAM, WEBHOOK, REST_API")
    is_active: bool = Field(default=True, description="Active status")


class SignalProviderCreate(SignalProviderBase):
    """Payload for creating a Signal Provider."""
    pass


class SignalProviderUpdate(BaseSchema):
    """Payload for updating a Signal Provider."""
    name: Optional[str] = None
    type: Optional[str] = None
    is_active: Optional[bool] = None


class SignalProviderRead(SignalProviderBase):
    """Response schema for Signal Provider."""
    id: int
    created_at: Optional[TimestampMixin] = None


# =====================================================================
# 7. RISK PROFILE SCHEMAS
# =====================================================================

class RiskProfileBase(BaseSchema):
    """Base fields for Risk Profile management."""
    name: str = Field(..., min_length=2, max_length=100, description="Risk profile name")
    risk_percent: Decimal = Field(default=Decimal("2.0"), gt=0, le=10, description="Risk percentage per trade (0.1% - 10.0%)")
    max_daily_loss: Decimal = Field(default=Decimal("5.0"), gt=0, description="Max daily drawdown limit (%)")
    max_open_trade: int = Field(default=3, ge=1, le=20, description="Max simultaneous open positions")
    is_active: bool = Field(default=True, description="Active status")


class RiskProfileCreate(RiskProfileBase):
    """Payload for creating a Risk Profile."""
    pass


class RiskProfileUpdate(BaseSchema):
    """Payload for updating a Risk Profile."""
    name: Optional[str] = None
    risk_percent: Optional[Decimal] = Field(default=None, gt=0, le=10)
    max_daily_loss: Optional[Decimal] = Field(default=None, gt=0)
    max_open_trade: Optional[int] = Field(default=None, ge=1, le=20)
    is_active: Optional[bool] = None


class RiskProfileRead(RiskProfileBase):
    """Response schema for Risk Profile."""
    id: int


# =====================================================================
# 8. WATCHLIST SCHEMAS
# =====================================================================

class WatchlistBase(BaseSchema):
    """Base fields for Watchlist entry."""
    instrument_id: int = Field(..., gt=0, description="FK to instruments table")
    enabled: bool = Field(default=True, description="Trading enabled for this pair")


class WatchlistCreate(WatchlistBase):
    """Payload for adding an Instrument to Watchlist."""
    pass


class WatchlistUpdate(BaseSchema):
    """Payload for updating Watchlist status."""
    enabled: bool


class WatchlistRead(WatchlistBase, TimestampMixin):
    """Response schema for Watchlist."""
    id: int
    instrument: Optional[InstrumentRead] = None
