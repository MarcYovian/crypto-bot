"""Pydantic schemas for Bot Settings and Bot Logs."""

from datetime import datetime
from typing import Optional
from pydantic import Field
from src.schemas.common import BaseSchema


# =====================================================================
# 1. BOT SETTING SCHEMAS
# =====================================================================

class BotSettingBase(BaseSchema):
    """Base fields for dynamic key-value bot settings."""
    key: str = Field(..., min_length=2, max_length=100, description="Unique setting key")
    category: Optional[str] = Field(default="GENERAL", description="Setting category, e.g. TRADING, RISK, SYSTEM")
    type: Optional[str] = Field(default="STRING", description="Data type: STRING, INT, FLOAT, BOOLEAN, JSON")
    value: str = Field(..., description="Configuration string value")
    description: Optional[str] = Field(default=None, description="Human-readable description")


class BotSettingCreate(BotSettingBase):
    """Payload for creating a new bot setting."""
    pass


class BotSettingUpdate(BaseSchema):
    """Payload for updating an existing setting value."""
    value: str
    description: Optional[str] = None


class BotSettingRead(BotSettingBase):
    """Response schema for Bot Setting."""
    updated_at: Optional[datetime] = None


# =====================================================================
# 2. BOT LOG SCHEMAS
# =====================================================================

class BotLogBase(BaseSchema):
    """Base fields for database-persisted application log."""
    module: Optional[str] = Field(default=None, description="Source module name")
    level: str = Field(..., pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$", description="Log severity")
    message: str = Field(..., description="Log message text")
    context_json: Optional[str] = Field(default=None, description="JSON string with contextual details")


class BotLogCreate(BotLogBase):
    """Payload for creating a new database log entry."""
    pass


class BotLogRead(BotLogBase):
    """Response schema for Bot Log."""
    id: int
    created_at: Optional[datetime] = None


# =====================================================================
# 3. BOT OPERATIONS & CONFIGURATION DTOS
# =====================================================================

class BotStatusDTO(BaseSchema):
    """Real-time engine runtime and health status."""
    is_running: bool = Field(default=True, description="Engine process execution state")
    is_paused: bool = Field(default=False, description="Manual or circuit breaker pause flag")
    trading_status: str = Field(default="ACTIVE", description="Trading state: ACTIVE or PAUSED")
    circuit_breaker_active: bool = Field(default=False, description="Circuit breaker status")
    binance_ws_connected: bool = Field(default=True, description="Binance User Data WebSocket status")
    telegram_polling_active: bool = Field(default=True, description="Telegram listener status")
    scheduler_jobs_count: int = Field(default=7, description="Active background cron job count")
    last_heartbeat: datetime = Field(..., description="Latest heartbeat timestamp")


class GenericActionResponse(BaseSchema):
    """Standard generic action response schema."""
    success: bool = Field(default=True, description="Action success state")
    message: str = Field(default="Action completed successfully.", description="Status message")


class BotSettingsDTO(BaseSchema):
    """Active bot trading configuration and risk profile."""
    default_leverage: int = Field(default=20, description="Default leverage multiplier")
    confidence_threshold: float = Field(default=0.70, description="Minimum confidence threshold (0.0 - 1.0)")
    risk_percent_per_trade: float = Field(default=2.0, description="Risk percent of equity per trade")
    max_daily_loss_percent: float = Field(default=6.0, description="Maximum daily loss percentage before pause")
    max_open_trades: int = Field(default=3, description="Maximum concurrent active trades")
    is_paused: bool = Field(default=False, description="Engine pause state")


class BotSettingsUpdateRequest(BaseSchema):
    """Payload for modifying bot configuration parameters."""
    default_leverage: Optional[int] = Field(default=None, ge=1, le=125, description="Default leverage (1-125)")
    confidence_threshold: Optional[float] = Field(default=None, ge=0.1, le=1.0, description="Confidence threshold (0.1-1.0)")
    risk_percent_per_trade: Optional[float] = Field(default=None, ge=0.1, le=10.0, description="Risk per trade (0.1-10.0%)")
    max_daily_loss_percent: Optional[float] = Field(default=None, ge=1.0, le=20.0, description="Max daily loss (1.0-20.0%)")
    max_open_trades: Optional[int] = Field(default=None, ge=1, le=10, description="Max concurrent open trades (1-10)")


class TradingCredentialCreateRequest(BaseSchema):
    """Payload for registering and verifying Binance API credentials."""
    api_key: str = Field(..., min_length=10, max_length=200, description="Binance API Key")
    secret_key: str = Field(..., min_length=10, max_length=200, description="Binance Secret Key")
    environment: str = Field(default="TESTNET", description="Target environment (TESTNET or LIVE)")


class PanicCloseRequest(BaseSchema):
    """Confirmation payload for emergency panic close."""
    confirmation: bool = Field(..., description="Must be true to authorize emergency close")


class PanicCloseResponseDTO(BaseSchema):
    """Execution feedback for emergency panic close."""
    success: bool = Field(default=True)
    closed_trades_count: int = Field(..., description="Total trades closed")
    canceled_orders_count: int = Field(..., description="Total pending orders canceled")
    timestamp: datetime = Field(..., description="Execution timestamp")


class CredentialSaveResponseDTO(BaseSchema):
    """Response feedback after successful handshake and credential storage."""
    success: bool = Field(default=True)
    account_id: int = Field(..., description="Trading account ID")
    credential_id: int = Field(..., description="Trading credential record ID")
    wallet_balance_usdt: float = Field(..., description="Verified live wallet balance in USDT")
    environment: str = Field(..., description="Environment (TESTNET or LIVE)")

