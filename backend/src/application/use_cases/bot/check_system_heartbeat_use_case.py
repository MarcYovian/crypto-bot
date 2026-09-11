"""Use case for executing system-wide heartbeat health checks."""

from datetime import datetime
import json
import logging
from typing import Any, Dict, Optional

from src.domain.ports.gateways import IExchangeGateway
from src.domain.ports.repositories import IBotLogRepository, IBotSettingRepository

logger = logging.getLogger(__name__)


class CheckSystemHeartbeatUseCase:
    """Use case to audit database connectivity, exchange API liveness, and log system status."""

    def __init__(
        self,
        bot_setting_repo: IBotSettingRepository,
        bot_log_repo: IBotLogRepository,
        exchange_gateway: Optional[IExchangeGateway] = None,
    ) -> None:
        self.bot_setting_repo = bot_setting_repo
        self.bot_log_repo = bot_log_repo
        self.exchange_gateway = exchange_gateway

    async def execute(self) -> Dict[str, Any]:
        """Verify DB and Exchange responsiveness, log status, and return health status."""
        db_healthy = True
        exchange_healthy = True

        # 1. Check DB query liveness
        try:
            if hasattr(self.bot_setting_repo, "get_all_as_dict"):
                await self.bot_setting_repo.get_all_as_dict()
            elif hasattr(self.bot_setting_repo, "get_all"):
                await self.bot_setting_repo.get_all()
        except Exception as exc:
            logger.warning("Heartbeat DB check failed: %s", exc)
            db_healthy = False

        # 2. Check Exchange API liveness
        if self.exchange_gateway:
            try:
                if hasattr(self.exchange_gateway, "fetch_balance"):
                    await self.exchange_gateway.fetch_balance()
            except Exception as exc:
                logger.warning("Heartbeat Exchange check failed: %s", exc)
                exchange_healthy = False

        is_healthy = db_healthy and exchange_healthy
        level = "INFO" if is_healthy else "ERROR"

        context_dict = {
            "db_healthy": db_healthy,
            "exchange_healthy": exchange_healthy,
            "is_healthy": is_healthy,
        }

        # 3. Log heartbeat status to repository
        try:
            if hasattr(self.bot_log_repo, "create_log"):
                await self.bot_log_repo.create_log(
                    level=level,
                    module="SchedulerService",
                    message="Hourly Heartbeat Health Check",
                    context=context_dict,
                )
            elif hasattr(self.bot_log_repo, "create"):
                await self.bot_log_repo.create(
                    {
                        "level": level,
                        "module": "SchedulerService",
                        "message": "Hourly Heartbeat Health Check",
                        "context_json": json.dumps(context_dict),
                    }
                )
        except Exception as log_exc:
            logger.warning("Failed writing heartbeat log: %s", log_exc)

        return {
            **context_dict,
            "timestamp": datetime.now().isoformat(),
        }
