"""Use case for retrieving consolidated bot configuration and risk profile settings."""

from src.domain.ports.repositories import IBotSettingRepository, IRiskProfileRepository
from src.presentation.api.schemas.system import BotSettingsDTO


class GetSettingsUseCase:
    """Use case to fetch consolidated bot settings and risk profile configuration."""

    def __init__(
        self,
        bot_setting_repo: IBotSettingRepository,
        risk_profile_repo: IRiskProfileRepository,
    ) -> None:
        self.bot_setting_repo = bot_setting_repo
        self.risk_profile_repo = risk_profile_repo

    async def execute(self) -> BotSettingsDTO:
        """Fetch consolidated bot settings and risk profile configuration."""
        active_profile = await self.risk_profile_repo.get_active_profile()
        if not active_profile:
            risk_percent = 2.0
            max_daily_loss = 6.0
            max_open_trades = 3
        else:
            risk_percent = float(active_profile.risk_percent)
            max_daily_loss = float(active_profile.max_daily_loss)
            max_open_trades = active_profile.max_open_trade

        default_lev_str = await self.bot_setting_repo.get_value("default_leverage", default="20")
        conf_str = await self.bot_setting_repo.get_value("confidence_threshold", default="0.70")
        is_paused = await self.bot_setting_repo.get_bool("is_paused", default=False)

        return BotSettingsDTO(
            default_leverage=int(default_lev_str or "20"),
            confidence_threshold=float(conf_str or "0.70"),
            risk_percent_per_trade=risk_percent,
            max_daily_loss_percent=max_daily_loss,
            max_open_trades=max_open_trades,
            is_paused=is_paused,
        )
