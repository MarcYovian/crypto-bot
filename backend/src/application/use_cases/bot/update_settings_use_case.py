"""Use case for validating and updating bot settings and risk profile configuration."""

from decimal import Decimal
from typing import Optional, Any

from src.domain.exceptions.system import InvalidSettingsValueError
from src.domain.ports.repositories import IBotSettingRepository, IRiskProfileRepository
from src.infrastructure.persistence.models.risk_profiles import RiskProfile

from src.presentation.api.schemas.system import (
    BotSettingsDTO,
    BotSettingsUpdateRequest,
    BotSettingCreate,
    BotSettingUpdate,
)
from src.utils.cache import in_memory_cache
from src.application.use_cases.bot.get_settings_use_case import GetSettingsUseCase


class UpdateSettingsUseCase:
    """Use case to validate and apply modifications to bot configurations and risk profiles."""

    def __init__(
        self,
        bot_setting_repo: IBotSettingRepository,
        risk_profile_repo: IRiskProfileRepository,
        cache: Optional[Any] = None,
    ) -> None:
        self.bot_setting_repo = bot_setting_repo
        self.risk_profile_repo = risk_profile_repo
        self.cache = cache or in_memory_cache
        self.get_settings_use_case = GetSettingsUseCase(bot_setting_repo, risk_profile_repo)

    async def execute(self, payload: BotSettingsUpdateRequest) -> BotSettingsDTO:
        """Validate and apply modifications to bot configurations and risk profiles."""
        if payload.default_leverage is not None and not (1 <= payload.default_leverage <= 125):
            raise InvalidSettingsValueError("Default leverage must be between 1 and 125.")
        if payload.confidence_threshold is not None and not (0.1 <= payload.confidence_threshold <= 1.0):
            raise InvalidSettingsValueError("Confidence threshold must be between 0.1 and 1.0.")
        if payload.risk_percent_per_trade is not None and not (0.1 <= payload.risk_percent_per_trade <= 10.0):
            raise InvalidSettingsValueError("Risk percent per trade must be between 0.1% and 10.0%.")
        if payload.max_daily_loss_percent is not None and not (1.0 <= payload.max_daily_loss_percent <= 20.0):
            raise InvalidSettingsValueError("Max daily loss percent must be between 1.0% and 20.0%.")
        if payload.max_open_trades is not None and not (1 <= payload.max_open_trades <= 10):
            raise InvalidSettingsValueError("Max open trades must be between 1 and 10.")

        # Update bot_settings
        if payload.default_leverage is not None:
            s = await self.bot_setting_repo.get_by_key("default_leverage")
            if not s:
                await self.bot_setting_repo.create(
                    BotSettingCreate(key="default_leverage", value=str(payload.default_leverage), category="TRADING", type="INT")
                )
            else:
                await self.bot_setting_repo.update(s, BotSettingUpdate(value=str(payload.default_leverage)))

        if payload.confidence_threshold is not None:
            s = await self.bot_setting_repo.get_by_key("confidence_threshold")
            if not s:
                await self.bot_setting_repo.create(
                    BotSettingCreate(key="confidence_threshold", value=str(payload.confidence_threshold), category="TRADING", type="FLOAT")
                )
            else:
                await self.bot_setting_repo.update(s, BotSettingUpdate(value=str(payload.confidence_threshold)))

        # Update risk_profiles
        active_profile = await self.risk_profile_repo.get_active_profile()
        if not active_profile:
            active_profile = RiskProfile(
                name="ACTIVE_PROFILE",
                risk_percent=Decimal(str(payload.risk_percent_per_trade or 2.0)),
                max_daily_loss=Decimal(str(payload.max_daily_loss_percent or 6.0)),
                max_open_trade=payload.max_open_trades or 3,
                is_active=True,
            )
            if hasattr(self.risk_profile_repo, "session") and self.risk_profile_repo.session:
                self.risk_profile_repo.session.add(active_profile)
                await self.risk_profile_repo.session.commit()
                await self.risk_profile_repo.session.refresh(active_profile)
        else:
            if payload.risk_percent_per_trade is not None:
                active_profile.risk_percent = Decimal(str(payload.risk_percent_per_trade))
            if payload.max_daily_loss_percent is not None:
                active_profile.max_daily_loss = Decimal(str(payload.max_daily_loss_percent))
            if payload.max_open_trades is not None:
                active_profile.max_open_trade = payload.max_open_trades
            if hasattr(self.risk_profile_repo, "session") and self.risk_profile_repo.session:
                self.risk_profile_repo.session.add(active_profile)
                await self.risk_profile_repo.session.commit()

        if self.cache:
            await self.cache.invalidate("settings")

        return await self.get_settings_use_case.execute()
