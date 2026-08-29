"""Use case for listing all registered signal providers."""

from typing import List
from src.domain.ports.repositories import ISignalProviderRepository
from src.presentation.api.schemas.master import SignalProviderDTO


class ListProvidersUseCase:
    """Use case to fetch all registered signal provider channels."""

    def __init__(self, provider_repo: ISignalProviderRepository) -> None:
        self.provider_repo = provider_repo

    async def execute(self) -> List[SignalProviderDTO]:
        """Fetch all registered signal provider channels."""
        providers = await self.provider_repo.get_all_providers()
        result: List[SignalProviderDTO] = []
        for p in providers:
            result.append(
                SignalProviderDTO(
                    id=p.id,
                    name=p.name,
                    channel_id=p.type,
                    is_active=p.is_active,
                    confidence_weight=1.0,
                )
            )
        return result
