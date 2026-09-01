"""Base definition for all Domain Events in the trading system."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Base Domain Event dataclass with tracking metadata."""

    event_id: str = field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: str = field(default_factory=lambda: f"trc-{uuid.uuid4().hex[:8]}")

    @property
    def event_name(self) -> str:
        return self.__class__.__name__

    def to_dict(self) -> Dict[str, Any]:
        """Convert event data to dictionary representation."""
        res: Dict[str, Any] = {
            "event_name": self.event_name,
            "event_id": self.event_id,
            "occurred_at": self.occurred_at.isoformat(),
            "trace_id": self.trace_id,
        }
        for k, v in self.__dict__.items():
            if k not in res:
                res[k] = v
        return res
