"""Value object defining schedule misfire and downtime recovery policies."""

from enum import Enum
from typing import Union


class MisfirePolicy(str, Enum):
    """Execution policy when a scheduled cron job was missed due to system downtime."""

    RUN_LATEST_ONCE = "RUN_LATEST_ONCE"
    """Execute the missed job once immediately upon system restart (e.g. daily risk snapshot)."""

    SKIP_TO_NEXT = "SKIP_TO_NEXT"
    """Discard missed executions and advance next_run_at to the subsequent window (e.g. hourly heartbeat)."""

    IMMEDIATE = "IMMEDIATE"
    """Run self-healing or synchronization immediately on startup (e.g. failsafe position sync)."""

    @classmethod
    def from_str(cls, value: Union[str, "MisfirePolicy"]) -> "MisfirePolicy":
        if isinstance(value, MisfirePolicy):
            return value
        cleaned = str(value).strip().upper()
        for policy in cls:
            if policy.value == cleaned:
                return policy
        raise ValueError(f"Invalid misfire policy: {value}")

    def __str__(self) -> str:
        return self.value
