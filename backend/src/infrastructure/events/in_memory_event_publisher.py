"""In-memory async domain event publisher implementing IDomainEventPublisher."""

import asyncio
import inspect
import logging
from typing import Any, Awaitable, Callable, Dict, List, Sequence, Type

from src.domain.events.base import DomainEvent
from src.domain.ports.event_publisher import IDomainEventPublisher

logger = logging.getLogger(__name__)

EventHandler = Callable[[DomainEvent], Awaitable[None]]


class InMemoryDomainEventPublisher(IDomainEventPublisher):
    """Asynchronous in-memory event bus for decoupling domain events from external side effects."""

    def __init__(self) -> None:
        self._handlers: Dict[Type[DomainEvent], List[EventHandler]] = {}
        self._global_handlers: List[EventHandler] = []
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: Type[DomainEvent], handler: EventHandler) -> None:
        """Register an async handler function for a specific DomainEvent type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)
            logger.debug("Subscribed %s to %s", getattr(handler, "__name__", str(handler)), event_type.__name__)

    def subscribe_all(self, handler: EventHandler) -> None:
        """Register a global handler that receives all domain events (useful for logging/auditing)."""
        if handler not in self._global_handlers:
            self._global_handlers.append(handler)

    def unsubscribe(self, event_type: Type[DomainEvent], handler: EventHandler) -> None:
        """Unregister an event handler."""
        if event_type in self._handlers and handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    async def publish(self, event: DomainEvent) -> None:
        """Dispatch a single domain event to all registered listeners asynchronously."""
        evt_type = type(event)
        handlers = list(self._handlers.get(evt_type, [])) + list(self._global_handlers)

        if not handlers:
            logger.debug("No handlers registered for event %s", event.event_name)
            return

        tasks = []
        for handler in handlers:
            tasks.append(self._safely_execute_handler(handler, event))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def publish_all(self, events: Sequence[DomainEvent]) -> None:
        """Dispatch a batch of domain events in sequential order."""
        for event in events:
            await self.publish(event)

    async def _safely_execute_handler(self, handler: EventHandler, event: DomainEvent) -> None:
        """Execute a single handler with exception shielding so one handler failure doesn't break others."""
        handler_name = getattr(handler, "__name__", str(handler))
        try:
            res = handler(event)
            if inspect.isawaitable(res):
                await res
        except Exception as exc:
            logger.exception("Error executing event handler '%s' for event %s: %s", handler_name, event.event_name, exc)

    def clear(self) -> None:
        """Remove all subscribers (useful for test teardown)."""
        self._handlers.clear()
        self._global_handlers.clear()
