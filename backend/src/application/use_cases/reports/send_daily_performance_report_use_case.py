"""Use case for generating and dispatching daily trading performance reports."""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

from src.domain.ports.gateways import INotificationGateway
from src.domain.ports.repositories import ITradeSummaryRepository

logger = logging.getLogger(__name__)


class SendDailyPerformanceReportUseCase:
    """Use case to aggregate daily closed trade metrics and notify admin via Telegram."""

    def __init__(
        self,
        trade_summary_repo: ITradeSummaryRepository,
        notification_gateway: Optional[INotificationGateway] = None,
    ) -> None:
        self.trade_summary_repo = trade_summary_repo
        self.notification_gateway = notification_gateway

    async def execute(
        self,
        account_id: int = 1,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Compute performance metrics for the period and send telegram notification.

        Args:
            account_id: Target trading account ID.
            start_date: Optional start datetime (defaults to 24h before end_date).
            end_date: Optional end datetime (defaults to now).

        Returns:
            Dict containing aggregated performance metrics.
        """
        period_end = end_date or datetime.now()
        period_start = start_date or (period_end - timedelta(days=1))

        perf = await self.trade_summary_repo.get_performance_summary(
            account_id=account_id,
            start_date=period_start,
            end_date=period_end,
        )

        total_trades = perf.get("total_trades", 0)
        wins = perf.get("winning_trades", 0)
        losses = perf.get("losing_trades", 0)
        total_pnl = perf.get("total_net_pnl", Decimal("0.0"))
        win_rate = perf.get("win_rate", Decimal("0.0"))

        if self.notification_gateway:
            try:
                pnl_icon = "🟢" if total_pnl >= Decimal("0") else "🔴"
                msg = (
                    f"📊 <b>DAILY TRADING RECAP REPORT</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"📈 Total Trades Selesai: <b>{total_trades}</b>\n"
                    f"🏆 Win: <b>{wins}</b> | 🛑 Loss: <b>{losses}</b>\n"
                    f"🎯 Win Rate: <b>{win_rate}%</b>\n"
                    f"{pnl_icon} Net Realized PnL: <b>${total_pnl:+,.2f} USDT</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━"
                )
                await self.notification_gateway.send_message(chat_id="ADMIN_CHANNEL", text=msg)
            except Exception as e:
                logger.error("Failed to send daily performance report via notification gateway: %s", e)

        return {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": float(win_rate),
            "net_pnl": float(total_pnl),
        }
