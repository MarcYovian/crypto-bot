"""Use case for capturing daily risk snapshot and resetting risk budgets at midnight."""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from pytz import timezone

from src.domain.ports.gateways import IExchangeGateway, INotificationGateway
from src.domain.ports.repositories import (
    IBotSettingRepository,
    IDailyRiskRepository,
    IRiskProfileRepository,
)
from src.presentation.api.schemas.risk import DailyRiskConfigCreate

logger = logging.getLogger(__name__)
WIB_TZ = timezone("Asia/Jakarta")


class DailyRiskSnapshotUseCase:
    """Computes daily loss limits at midnight, creates risk snapshot, and auto-resets circuit breaker."""

    def __init__(
        self,
        daily_risk_repo: IDailyRiskRepository,
        risk_profile_repo: IRiskProfileRepository,
        bot_setting_repo: Optional[IBotSettingRepository] = None,
        exchange_gateway: Optional[IExchangeGateway] = None,
        notification_gateway: Optional[INotificationGateway] = None,
    ) -> None:
        self.daily_risk_repo = daily_risk_repo
        self.risk_profile_repo = risk_profile_repo
        self.bot_setting_repo = bot_setting_repo
        self.exchange_gateway = exchange_gateway
        self.notification_gateway = notification_gateway

    async def execute(
        self,
        account_id: int = 1,
        snapshot_date: Optional[date] = None,
    ) -> Any:
        """Execute midnight risk budget computation and snapshot recording."""
        target_date = snapshot_date or datetime.now(WIB_TZ).date()

        # 1. Fetch balance from exchange gateway
        balance = Decimal("10000.0")
        if self.exchange_gateway:
            try:
                bal_data = await self.exchange_gateway.fetch_balance()
                balance = (
                    bal_data.get("total_wallet_balance")
                    or bal_data.get("free_margin")
                    or bal_data.get("total_balance_usdt")
                    or Decimal("10000.0")
                )
            except Exception as e:
                logger.error("Failed to fetch balance from exchange during snapshot: %s", e)

        # 2. Get active risk profile or create default
        profile = None
        was_profile_created = False
        if self.risk_profile_repo:
            profile = await self.risk_profile_repo.get_active_profile()
            if not profile:
                profile = await self.risk_profile_repo.get_or_create_default_profile()
                was_profile_created = True

        profile_id = profile.id if profile else 1
        loss_limit_pct = (
            profile.risk_percent if profile and profile.risk_percent else Decimal("2.0")
        )
        profile_name = profile.name if profile else "DEFAULT"

        # 3. Calculate max daily loss budget in USDT (strictly 2% or profile risk percent)
        daily_risk_budget = balance * (loss_limit_pct / Decimal("100"))

        # 4. Save idempotent snapshot
        snapshot = await self.daily_risk_repo.get_or_create_daily_snapshot(
            DailyRiskConfigCreate(
                account_id=account_id,
                risk_profile_id=profile_id,
                date=target_date,
                balance=balance,
                risk_amount=daily_risk_budget,
            )
        )

        # 5. Reset Circuit Breaker and Auto-Unpause for the new day
        if self.bot_setting_repo:
            try:
                await self.bot_setting_repo.set_value("is_paused", "false")
                await self.bot_setting_repo.set_value("trading_status", "ACTIVE")
            except Exception as e:
                logger.warning("Failed to reset circuit breaker pause setting: %s", e)

        # 6. Broadcast notification
        if self.notification_gateway:
            try:
                if was_profile_created:
                    max_open = getattr(profile, "max_open_trade", 3) if profile else 3
                    create_msg = (
                        f"⚠️ <b>PEMBERITAHUAN PROFIL RISIKO</b>\n\n"
                        f"Profil risiko aktif tidak ditemukan di sistem. Sistem secara otomatis membuat dan mengaktifkan profil default baru:\n"
                        f"• <b>Nama Profil:</b> <code>{profile_name}</code>\n"
                        f"• <b>Risiko per Trade:</b> <code>{loss_limit_pct}%</code>\n"
                        f"• <b>Batas Maks Open Trade:</b> <code>{max_open}</code>\n\n"
                        f"👉 <i>Anda dapat menyesuaikan parameter ini sewaktu-waktu pada konfigurasi profil risiko.</i>"
                    )
                    await self.notification_gateway.send_message(chat_id="ADMIN_CHANNEL", text=create_msg)

                msg = (
                    f"🌅 <b>DAILY RISK SNAPSHOT (00:00 WIB)</b>\n"
                    f"📅 Tanggal: <code>{target_date.isoformat()}</code>\n"
                    f"💰 Saldo Modal Awal: <b>${balance:,.2f} USDT</b>\n"
                    f"🛡️ Profil Risiko: <b>{profile_name}</b> ({loss_limit_pct}%)\n"
                    f"🎯 Anggaran Risiko Harian: <b>${daily_risk_budget:,.2f} USDT</b>\n"
                    f"✅ Circuit Breaker: <b>ACTIVE & READY</b>"
                )
                await self.notification_gateway.send_message(chat_id="ADMIN_CHANNEL", text=msg)
            except Exception as e:
                logger.error("Failed to send snapshot alert to notification gateway: %s", e)

        return snapshot
