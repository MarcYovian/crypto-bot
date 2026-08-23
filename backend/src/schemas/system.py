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
