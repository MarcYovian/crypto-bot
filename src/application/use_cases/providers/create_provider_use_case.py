"""Use case for registering a new signal provider channel."""

import logging
from src.domain.exceptions.provider import DuplicateProviderError
from src.domain.ports.repositories import ISignalProviderRepository
from src.presentation.api.schemas.master import (
    SignalProviderDTO,
    SignalProviderCreateRequest,
    SignalProviderCreate,
)

logger = logging.getLogger(__name__)


class CreateProviderUseCase:
    """Use case to register a new Telegram signal provider channel."""

    def __init__(self, provider_repo: ISignalProviderRepository) -> None:
        self.provider_repo = provider_repo

    async def execute(self, payload: SignalProviderCreateRequest) -> SignalProviderDTO:
        """Register a new Telegram signal provider channel."""
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
