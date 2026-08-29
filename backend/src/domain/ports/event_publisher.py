"""Abstract port for dispatching Domain Events."""

from abc import ABC, abstractmethod
from typing import List, Sequence
from src.domain.events.base import DomainEvent


class IDomainEventPublisher(ABC):
    """Abstract Port for publishing Domain Events to registered subscribers / handlers."""

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """Publish a single domain event."""
        ...

    @abstractmethod
    async def publish_all(self, events: Sequence[DomainEvent]) -> None:
        """Publish a batch of domain events in sequential order."""
        ...
