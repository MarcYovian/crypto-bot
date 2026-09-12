"""FastAPI Router for Scheduler and Cron Jobs management."""

from datetime import datetime
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.di.container import container
from src.infrastructure.persistence.models.scheduler_tasks import SchedulerTask
from src.infrastructure.persistence.models.users import User
from src.infrastructure.scheduler.scheduler_runner import SchedulerRunner
from src.infrastructure.scheduler.task_registry import (
    cron_to_human_interval,
    interval_to_cron,
)
from src.presentation.api.deps import (
    get_current_admin_user,
    get_current_user,
    get_db_session,
    get_scheduler_runner,
)
from src.presentation.api.schemas.scheduler import (
    IntervalUnit,
    MisfirePolicyEnum,
    SchedulerRecoveryResponseDTO,
    SchedulerTaskDTO,
    SchedulerTaskDetailDTO,
    SchedulerTaskRunDTO,
    SchedulerTaskTriggerResponse,
    SchedulerTaskUpdateDTO,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scheduler", tags=["Scheduler & Cron Jobs"])


def _to_task_dto(task: SchedulerTask) -> SchedulerTaskDTO:
    """Enrich a persistence SchedulerTask model with human-friendly interval and description."""
    interval_val, interval_unit_str, human_desc = cron_to_human_interval(task.cron_expr)
    unit_enum: Optional[IntervalUnit] = None
    if interval_unit_str:
        try:
            unit_enum = IntervalUnit(interval_unit_str)
        except Exception:
            unit_enum = None

    policy_val = (
        task.misfire_policy.value
        if hasattr(task.misfire_policy, "value")
        else str(task.misfire_policy)
    )

    return SchedulerTaskDTO(
        id=task.id,
        name=task.name,
        interval_value=interval_val,
        interval_unit=unit_enum,
        cron_human=human_desc,
        cron_expr=task.cron_expr,
        timezone=task.timezone,
        is_active=task.is_active,
        misfire_policy=MisfirePolicyEnum(policy_val),
        last_run_at=task.last_run_at,
        next_run_at=task.next_run_at,
        last_status=task.last_status,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


# =============================================================================
# 1. LIST TASKS
# =============================================================================
@router.get(
    "/tasks",
    response_model=List[SchedulerTaskDTO],
    summary="List all registered scheduler tasks",
    description="Returns all recurring background tasks with current schedules, active status, last execution status, next execution date, and misfire policy.",
)
async def list_scheduler_tasks(
    is_active: Optional[bool] = Query(None, description="Filter tasks by active status"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> List[SchedulerTaskDTO]:
    task_repo = container.get_scheduler_task_repo(session)
    tasks = await task_repo.get_all(is_active=is_active)
    return [_to_task_dto(t) for t in tasks]


# =============================================================================
# 2. GET TASK DETAIL
# =============================================================================
@router.get(
    "/tasks/{task_id}",
    response_model=SchedulerTaskDetailDTO,
    summary="Get scheduler task detail",
    description="Fetch detailed configuration and recent execution runs for a specific scheduled task by its unique identifier.",
)
async def get_scheduler_task_detail(
    task_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SchedulerTaskDetailDTO:
    task_repo = container.get_scheduler_task_repo(session)
    task = await task_repo.get(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scheduler task with id '{task_id}' not found.",
        )

    runs = await task_repo.get_recent_runs(task_id=task_id, limit=20)
    task_dto = _to_task_dto(task)

    run_dtos = [
        SchedulerTaskRunDTO(
            id=r.id,
            task_id=r.task_id,
            started_at=r.started_at,
            finished_at=r.finished_at,
            duration_ms=r.duration_ms,
            status=r.status,
            result_summary=r.result_summary,
            error_message=r.error_message,
        )
        for r in runs
    ]

    return SchedulerTaskDetailDTO(
        **task_dto.model_dump(),
        recent_runs=run_dtos,
    )


# =============================================================================
# 3. UPDATE / RESCHEDULE TASK
# =============================================================================
@router.patch(
    "/tasks/{task_id}",
    response_model=SchedulerTaskDTO,
    summary="Update task configuration, schedule, or active status",
    description="Dynamically update cron expression (rescheduling live in memory), toggle active/pause state, modify task name, or update misfire recovery policy.",
)
async def update_scheduler_task(
    task_id: str,
    payload: SchedulerTaskUpdateDTO,
    admin_user: User = Depends(get_current_admin_user),
    scheduler: SchedulerRunner = Depends(get_scheduler_runner),
    session: AsyncSession = Depends(get_db_session),
) -> SchedulerTaskDTO:
    # 1. Verify existence
    task_repo = container.get_scheduler_task_repo(session)
    task = await task_repo.get(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scheduler task with id '{task_id}' not found.",
        )

    # 2. Determine target cron expression
    target_cron: Optional[str] = None
    if payload.interval_value is not None and payload.interval_unit is not None:
        try:
            target_cron = interval_to_cron(payload.interval_value, payload.interval_unit)
        except ValueError as val_err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(val_err),
            )
    elif payload.cron_expr is not None:
        target_cron = payload.cron_expr

    # 3. Execute live update on SchedulerRunner
    try:
        updated_task = await scheduler.update_task(
            task_id=task_id,
            name=payload.name,
            cron_expr=target_cron,
            is_active=payload.is_active,
            misfire_policy=payload.misfire_policy,
            timezone_name=payload.timezone,
            session=session,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid cron expression or parameter: {err}",
        )
    except Exception as exc:
        logger.error("Failed updating scheduler task '%s': %s", task_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed updating task: {exc}",
        )

    return _to_task_dto(updated_task)


# =============================================================================
# 4. TRIGGER IMMEDIATE MANUAL RUN
# =============================================================================
@router.post(
    "/tasks/{task_id}/trigger",
    response_model=SchedulerTaskTriggerResponse,
    summary="Manually trigger immediate execution of a task",
    description="Execute a scheduled job immediately on-demand without waiting for its scheduled cron time, recording execution results in the database.",
)
async def trigger_scheduler_task(
    task_id: str,
    admin_user: User = Depends(get_current_admin_user),
    scheduler: SchedulerRunner = Depends(get_scheduler_runner),
    session: AsyncSession = Depends(get_db_session),
) -> SchedulerTaskTriggerResponse:
    task_repo = container.get_scheduler_task_repo(session)
    task = await task_repo.get(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scheduler task with id '{task_id}' not found.",
        )

    started_at = datetime.now()
    try:
        result = await scheduler.jobs.execute_job_by_id(task_id)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err),
        )
    except Exception as exc:
        logger.error("Error executing manual run for task '%s': %s", task_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Task execution failed: {exc}",
        )

    duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)

    return SchedulerTaskTriggerResponse(
        task_id=task_id,
        status="SUCCESS",
        started_at=started_at,
        duration_ms=duration_ms,
        result=result,
    )


# =============================================================================
# 5. GET EXECUTION RUN LOGS
# =============================================================================
@router.get(
    "/tasks/{task_id}/runs",
    response_model=List[SchedulerTaskRunDTO],
    summary="Get execution history logs for a task",
    description="Returns historical run audit logs including start time, completion time, duration, status (SUCCESS/FAILED), and result summary.",
)
async def get_scheduler_task_runs(
    task_id: str,
    limit: int = Query(20, ge=1, le=100, description="Maximum number of run records to retrieve"),
    run_status: Optional[str] = Query(None, alias="status", description="Filter run records by status (SUCCESS or FAILED)"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> List[SchedulerTaskRunDTO]:
    task_repo = container.get_scheduler_task_repo(session)
    task = await task_repo.get(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scheduler task with id '{task_id}' not found.",
        )

    runs = await task_repo.get_recent_runs(task_id=task_id, limit=limit)
    if run_status:
        runs = [r for r in runs if r.status.upper() == run_status.upper()]

    return [
        SchedulerTaskRunDTO(
            id=r.id,
            task_id=r.task_id,
            started_at=r.started_at,
            finished_at=r.finished_at,
            duration_ms=r.duration_ms,
            status=r.status,
            result_summary=r.result_summary,
            error_message=r.error_message,
        )
        for r in runs
    ]


# =============================================================================
# 6. TRIGGER DOWNTIME RECOVERY SCAN
# =============================================================================
@router.post(
    "/recovery",
    response_model=SchedulerRecoveryResponseDTO,
    summary="Trigger manual downtime recovery check",
    description="Scans database for overdue tasks that were missed during server downtime and executes or skips them according to their MisfirePolicy.",
)
async def trigger_scheduler_recovery(
    admin_user: User = Depends(get_current_admin_user),
    scheduler: SchedulerRunner = Depends(get_scheduler_runner),
) -> SchedulerRecoveryResponseDTO:
    try:
        report = await scheduler.run_startup_recovery()
        return SchedulerRecoveryResponseDTO(
            overdue_count=report.get("overdue_count", 0),
            recovered=report.get("recovered", []),
            skipped=report.get("skipped", []),
        )
    except Exception as exc:
        logger.error("Downtime recovery scan failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Downtime recovery failed: {exc}",
        )
