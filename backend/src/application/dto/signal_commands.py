"""Data Transfer Objects and Commands for Signal Use Cases."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass(frozen=True)
class ParseSignalCommand:
    """Command payload to extract signal parameters from raw text."""

    raw_text: str
    channel_id: Optional[str] = None
    provider_id: Optional[int] = None
    account_id: int = 1
    received_at: Optional[datetime] = None


@dataclass(frozen=True)
class ApproveSignalCommand:
    """Command payload when operator approves a signal."""

    signal_id: int
    account_id: int = 1
    custom_leverage: Optional[int] = None


@dataclass(frozen=True)
class RejectSignalCommand:
    """Command payload when operator rejects a signal."""

    signal_id: int
    reason: str = "OPERATOR_REJECTED"
    account_id: int = 1
