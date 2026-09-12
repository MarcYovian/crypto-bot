"""Registry and metadata configuration for database-driven scheduler tasks."""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone

from src.domain.value_objects.misfire_policy import MisfirePolicy

logger = logging.getLogger(__name__)
WIB_TZ = timezone("Asia/Jakarta")


DEFAULT_SYSTEM_TASKS: List[Dict[str, Any]] = [
    {
        "id": "daily_risk_snapshot",
        "name": "Daily Risk Snapshot & Budgeting",
        "cron_expr": "0 0 * * *",
        "misfire_policy": MisfirePolicy.RUN_LATEST_ONCE,
    },
    {
        "id": "cleanup_orphan_orders",
        "name": "Cleanup Orphan Orders",
        "cron_expr": "0,30 * * * *",
        "misfire_policy": MisfirePolicy.IMMEDIATE,
    },
    {
        "id": "failsafe_sync_check",
        "name": "Failsafe Position Sync",
        "cron_expr": "15,45 * * * *",
        "misfire_policy": MisfirePolicy.IMMEDIATE,
    },
    {
        "id": "sync_instruments_metadata",
        "name": "Sync Instruments Metadata",
        "cron_expr": "0 6,18 * * *",
        "misfire_policy": MisfirePolicy.SKIP_TO_NEXT,
    },
    {
        "id": "purge_old_logs",
        "name": "Purge Old Logs",
        "cron_expr": "0 3 * * *",
        "misfire_policy": MisfirePolicy.SKIP_TO_NEXT,
    },
    {
        "id": "daily_performance_report",
        "name": "Daily Performance Report",
        "cron_expr": "5 0 * * *",
        "misfire_policy": MisfirePolicy.RUN_LATEST_ONCE,
    },
    {
        "id": "heartbeat_health_check",
        "name": "Heartbeat Health Check",
        "cron_expr": "0 * * * *",
        "misfire_policy": MisfirePolicy.SKIP_TO_NEXT,
    },
    {
        "id": "archive_ws_cache",
        "name": "Archive WebSocket Cache",
        "cron_expr": "0 1 * * *",
        "misfire_policy": MisfirePolicy.SKIP_TO_NEXT,
    },
]


def calculate_next_fire_time(
    cron_expr: str,
    reference_time: Optional[datetime] = None,
    tz_name: str = "Asia/Jakarta",
) -> datetime:
    """Calculate the next fire timestamp for a crontab expression in naive local time.

    Args:
        cron_expr: Crontab 5-field expression string.
        reference_time: Datetime to calculate forward from (default: now).
        tz_name: Timezone string name (default: 'Asia/Jakarta').

    Returns:
        Naive datetime object representing the next execution target.
    """
    tz = timezone(tz_name)
    if reference_time is None:
        ref_aware = datetime.now(tz)
    elif reference_time.tzinfo is None:
        ref_aware = tz.localize(reference_time)
    else:
        ref_aware = reference_time.astimezone(tz)

    trigger = CronTrigger.from_crontab(cron_expr, timezone=tz)
    next_dt = trigger.get_next_fire_time(None, ref_aware)
    if next_dt is None:
        return datetime.now().replace(tzinfo=None)
    return next_dt.replace(tzinfo=None)


def interval_to_cron(value: int, unit: Any) -> str:
    """Convert human-friendly interval value and unit into a standard 5-part crontab expression.

    Args:
        value: Positive integer duration (e.g. 15, 30, 1).
        unit: String or Enum value (MINUTES, HOURS, DAYS, WEEKS, MONTHS).

    Returns:
        Standard 5-part crontab expression.
    """
    if value < 1:
        raise ValueError("Interval value must be at least 1.")

    unit_str = str(getattr(unit, "value", unit)).upper()
    if "MINUTES" in unit_str or unit_str == "MINUTE":
        if value == 1:
            return "* * * * *"
        if value < 60:
            return f"*/{value} * * * *"
        hours = value // 60
        return f"0 */{hours} * * *" if hours > 1 else "0 * * * *"
    elif "HOURS" in unit_str or unit_str == "HOUR":
        if value == 1:
            return "0 * * * *"
        if value < 24:
            return f"0 */{value} * * *"
        days = value // 24
        return f"0 0 */{days} * *" if days > 1 else "0 0 * * *"
    elif "DAYS" in unit_str or unit_str == "DAY":
        if value == 1:
            return "0 0 * * *"
        return f"0 0 */{value} * *"
    elif "WEEKS" in unit_str or unit_str == "WEEK":
        return "0 0 * * 0"
    elif "MONTHS" in unit_str or unit_str == "MONTH":
        return "0 0 1 * *"
    else:
        raise ValueError(f"Unsupported interval unit: '{unit}'. Use MINUTES, HOURS, DAYS, WEEKS, or MONTHS.")


def cron_to_human_interval(cron_expr: str) -> tuple[Optional[int], Optional[str], str]:
    """Parse a crontab expression into human-friendly interval value, unit, and readable text.

    Args:
        cron_expr: Standard crontab 5-field expression.

    Returns:
        Tuple of (interval_value, interval_unit_str, cron_human_description).
    """
    import re

    clean = cron_expr.strip()

    # Specific common bot schedules
    if clean == "* * * * *":
        return 1, "MINUTES", "Every 1 minute"
    if clean in ("*/15 * * * *", "15,45 * * * *"):
        return 15, "MINUTES", "Every 15 minutes"
    if clean in ("*/30 * * * *", "0,30 * * * *"):
        return 30, "MINUTES", "Every 30 minutes"
    if clean == "0 * * * *":
        return 1, "HOURS", "Every 1 hour at minute 0"
    if clean == "0 */2 * * *":
        return 2, "HOURS", "Every 2 hours"
    if clean == "0 6,18 * * *":
        return 12, "HOURS", "Every 12 hours (at 06:00 and 18:00 WIB)"
    if clean == "0 0 * * *":
        return 1, "DAYS", "Every day at midnight (00:00 WIB)"
    if clean == "5 0 * * *":
        return 1, "DAYS", "Every day at 00:05 WIB"
    if clean == "0 1 * * *":
        return 1, "DAYS", "Every day at 01:00 WIB"
    if clean == "0 3 * * *":
        return 1, "DAYS", "Every day at 03:00 WIB"
    if clean == "0 0 * * 0":
        return 1, "WEEKS", "Every Sunday at midnight (00:00 WIB)"
    if clean == "0 0 1 * *":
        return 1, "MONTHS", "Every 1st day of month at midnight (00:00 WIB)"

    # Match */N * * * *
    m_min = re.match(r"^\*/(\d+)\s+\*\s+\*\s+\*\s+\*$", clean)
    if m_min:
        val = int(m_min.group(1))
        return val, "MINUTES", f"Every {val} minutes"

    # Match 0 */N * * *
    m_hr = re.match(r"^0\s+\*/(\d+)\s+\*\s+\*\s+\*$", clean)
    if m_hr:
        val = int(m_hr.group(1))
        return val, "HOURS", f"Every {val} hours"

    # Match 0 0 */N * *
    m_day = re.match(r"^0\s+0\s+\*/(\d+)\s+\*\s+\*$", clean)
    if m_day:
        val = int(m_day.group(1))
        return val, "DAYS", f"Every {val} days"

    return None, None, f"Custom schedule: {clean}"
