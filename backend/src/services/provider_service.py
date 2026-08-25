"""Signal Provider business service for channel registration and performance leaderboard aggregation."""

import logging
from typing import List

from src.schemas.master import (
    SignalProviderDTO,
    SignalProviderCreateRequest,
    SignalProviderCreate,
    ProviderPerformanceDTO,
)
from src.repository.signal_provider_repository import SignalProviderRepository
from src.domain.exceptions.provider import (
    ProviderNotFoundError,
    DuplicateProviderError,
)

logger = logging.getLogger(__name__)


class ProviderService:
    """Service orchestrating signal source channels, deduplication, and financial performance analytics."""

    def __init__(self, provider_repo: SignalProviderRepository) -> None:
        self.provider_repo = provider_repo

    async def list_providers(self) -> List[SignalProviderDTO]:
        """Fetch all registered signal provider channels.

        Returns:
            List of SignalProviderDTO objects.
        """
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

    async def create_provider(self, payload: SignalProviderCreateRequest) -> SignalProviderDTO:
        """Register a new Telegram signal provider channel.

        Args:
            payload: Signal provider creation parameters.

        Returns:
            The created SignalProviderDTO.

        Raises:
            DuplicateProviderError: If a provider with the same name already exists.
        """
        clean_name = payload.name.strip()
        existing = await self.provider_repo.get_by_name(clean_name)
        if existing:
            raise DuplicateProviderError(
                f"Signal provider with name '{clean_name}' already exists."
            )

        create_schema = SignalProviderCreate(
            name=clean_name,
            type=payload.channel_id.strip() if payload.channel_id else "TELEGRAM",
            is_active=True,
        )
        new_provider = await self.provider_repo.create(create_schema)
        logger.info(f"Registered new signal provider '{new_provider.name}' (ID: {new_provider.id})")

        return SignalProviderDTO(
            id=new_provider.id,
            name=new_provider.name,
            channel_id=payload.channel_id.strip(),
            is_active=new_provider.is_active,
            confidence_weight=payload.confidence_weight,
        )

    async def get_provider_performance(self, provider_id: int) -> ProviderPerformanceDTO:
        """Compute aggregate performance statistics for a specific provider in a single SQL query.

        Args:
            provider_id: Primary key of the signal provider.

        Returns:
            ProviderPerformanceDTO with win rate, total signals, executed trades, and net PnL.

        Raises:
            ProviderNotFoundError: If provider ID is invalid or does not exist.
        """
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
