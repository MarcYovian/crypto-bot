"""Infrastructure Layer - Database, Gateways, External Clients, and DI Container."""

__all__ = [
    "ApplicationContainer",
    "container",
    "get_container",
    "BinanceExchangeAdapter",
    "BinanceConnector",
    "TelegramNotificationAdapter",
    "TelegramConnector",
    "InMemoryDomainEventPublisher",
]


def __getattr__(name: str):
    if name in ("ApplicationContainer", "container", "get_container"):
        from src.infrastructure.di.container import ApplicationContainer, container, get_container
        return {"ApplicationContainer": ApplicationContainer, "container": container, "get_container": get_container}[name]
    if name in ("BinanceExchangeAdapter", "BinanceConnector"):
        from src.infrastructure.gateways.binance import BinanceExchangeAdapter, BinanceConnector
        return {"BinanceExchangeAdapter": BinanceExchangeAdapter, "BinanceConnector": BinanceConnector}[name]
    if name in ("TelegramNotificationAdapter", "TelegramConnector"):
        from src.infrastructure.gateways.telegram import TelegramNotificationAdapter, TelegramConnector
        return {"TelegramNotificationAdapter": TelegramNotificationAdapter, "TelegramConnector": TelegramConnector}[name]
    if name == "InMemoryDomainEventPublisher":
        from src.infrastructure.events import InMemoryDomainEventPublisher
        return InMemoryDomainEventPublisher
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
