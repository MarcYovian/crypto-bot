"""Use case for computing aggregate financial performance statistics for a signal provider."""

from src.domain.exceptions.provider import ProviderNotFoundError
from src.domain.ports.repositories import ISignalProviderRepository
from src.presentation.api.schemas.master import ProviderPerformanceDTO


class GetProviderPerformanceUseCase:
    """Use case to compute aggregate performance statistics for a specific provider."""

    def __init__(self, provider_repo: ISignalProviderRepository) -> None:
        self.provider_repo = provider_repo

    async def execute(self, provider_id: int) -> ProviderPerformanceDTO:
        """Compute aggregate performance statistics for a specific provider."""
        provider = await self.provider_repo.get(provider_id)
        if not provider:
            raise ProviderNotFoundError(f"Signal provider with ID {provider_id} not found.")

        summary = await self.provider_repo.get_provider_performance_summary(provider_id)

        return ProviderPerformanceDTO(
            provider_id=provider.id,
            provider_name=provider.name,
            total_signals=summary["total_signals"],
            executed_trades=summary["executed_trades"],
            win_rate=summary["win_rate"],
            total_net_pnl_usdt=summary["total_net_pnl_usdt"],
        )
