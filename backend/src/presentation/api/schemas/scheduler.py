"""Pydantic schemas and DTOs for Scheduler and Cron Jobs management."""

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class IntervalUnit(str, Enum):
    """Supported time units for human-friendly interval configuration."""

    MINUTES = "MINUTES"
    HOURS = "HOURS"
    DAYS = "DAYS"
    WEEKS = "WEEKS"
    MONTHS = "MONTHS"


class MisfirePolicyEnum(str, Enum):
    """Execution policy applied when a task was missed due to system downtime."""

    RUN_LATEST_ONCE = "RUN_LATEST_ONCE"
    SKIP_TO_NEXT = "SKIP_TO_NEXT"
    IMMEDIATE = "IMMEDIATE"


class SchedulerTaskDTO(BaseModel):
    """Response DTO for a scheduled cron task."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique task identifier", json_schema_extra={"example": "daily_risk_snapshot"})
    name: str = Field(..., description="Task title/description", json_schema_extra={"example": "Daily Risk Snapshot & Budgeting"})
    interval_value: Optional[int] = Field(None, description="Human-friendly interval number", json_schema_extra={"example": 1})
    interval_unit: Optional[IntervalUnit] = Field(None, description="Interval time unit", json_schema_extra={"example": IntervalUnit.DAYS})
    cron_human: Optional[str] = Field(None, description="Human-readable schedule description", json_schema_extra={"example": "Every day at 00:00 WIB"})
    cron_expr: str = Field(..., description="Crontab expression string", json_schema_extra={"example": "0 0 * * *"})
    timezone: str = Field("Asia/Jakarta", description="Timezone name", json_schema_extra={"example": "Asia/Jakarta"})
    is_active: bool = Field(True, description="Whether the task is currently active or paused")
    misfire_policy: MisfirePolicyEnum = Field(..., description="Downtime recovery policy")
    last_run_at: Optional[datetime] = Field(None, description="Timestamp of last execution")
    next_run_at: datetime = Field(..., description="Timestamp of next scheduled execution")
    last_status: str = Field("IDLE", description="Status of last execution (IDLE, RUNNING, SUCCESS, FAILED)")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Update timestamp")


class SchedulerTaskUpdateDTO(BaseModel):
    """Payload for updating task metadata, cron schedule, status, or misfire recovery policy."""

    name: Optional[str] = Field(None, description="Updated task name", json_schema_extra={"example": "High Frequency Orphan Cleaner"})
    interval_value: Optional[int] = Field(None, ge=1, description="Human-friendly duration number (e.g. 15, 30, 1)", json_schema_extra={"example": 30})
    interval_unit: Optional[IntervalUnit] = Field(None, description="Time unit for interval_value", json_schema_extra={"example": IntervalUnit.MINUTES})
    cron_expr: Optional[str] = Field(None, description="Standard 5-part crontab expression (e.g. '*/30 * * * *')", json_schema_extra={"example": "*/30 * * * *"})
    is_active: Optional[bool] = Field(None, description="Toggle active or paused state")
    misfire_policy: Optional[MisfirePolicyEnum] = Field(None, description="Downtime recovery policy")
    timezone: Optional[str] = Field(None, description="Timezone name", json_schema_extra={"example": "Asia/Jakarta"})


class SchedulerTaskRunDTO(BaseModel):
    """Execution audit log record for an individual scheduler job invocation."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Run log primary key", json_schema_extra={"example": 1042})
    task_id: str = Field(..., description="Associated task ID", json_schema_extra={"example": "daily_risk_snapshot"})
    started_at: datetime = Field(..., description="Execution start timestamp")
    finished_at: Optional[datetime] = Field(None, description="Execution completion timestamp")
    duration_ms: Optional[int] = Field(None, description="Duration in milliseconds", json_schema_extra={"example": 2150})
    status: str = Field(..., description="Execution status (SUCCESS or FAILED)", json_schema_extra={"example": "SUCCESS"})
    result_summary: Optional[str] = Field(None, description="JSON string or summary of execution result")
    error_message: Optional[str] = Field(None, description="Error message if execution failed")


class SchedulerTaskDetailDTO(SchedulerTaskDTO):
    """Detailed task response including historical recent runs."""

    recent_runs: List[SchedulerTaskRunDTO] = Field(default_factory=list, description="Recent execution logs")


class SchedulerTaskTriggerResponse(BaseModel):
    """Response returned upon manually triggering an on-demand job run."""

    task_id: str = Field(..., json_schema_extra={"example": "failsafe_sync_check"})
    status: str = Field(..., json_schema_extra={"example": "SUCCESS"})
    started_at: datetime
    duration_ms: Optional[int] = Field(None, json_schema_extra={"example": 430})
    result: Optional[Any] = Field(None, description="Output returned by the executed use case")


class SchedulerRecoveryResponseDTO(BaseModel):
    """Response returned upon running a downtime recovery scan."""

    overdue_count: int = Field(..., description="Number of overdue tasks detected", json_schema_extra={"example": 1})
    recovered: List[str] = Field(default_factory=list, description="List of task IDs executed during catch-up")
    skipped: List[str] = Field(default_factory=list, description="List of task IDs skipped according to SKIP_TO_NEXT")
