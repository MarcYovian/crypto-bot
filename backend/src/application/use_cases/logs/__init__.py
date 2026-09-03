"""Logs Use Cases."""

from src.application.use_cases.logs.get_logs_use_case import GetLogsUseCase
from src.application.use_cases.logs.purge_old_logs_use_case import PurgeOldLogsUseCase

__all__ = [
    "GetLogsUseCase",
    "PurgeOldLogsUseCase",
]
