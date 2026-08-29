"""Unit tests for ApplicationContainer DI and lifecycle."""

import pytest
from src.infrastructure.di.container import ApplicationContainer, container, get_container
from src.infrastructure.gateways.binance import BinanceExchangeAdapter
from src.infrastructure.gateways.telegram import TelegramNotificationAdapter
from src.infrastructure.events import InMemoryDomainEventPublisher


def test_container_singleton_instances():
    app_c = get_container()
    assert isinstance(app_c, ApplicationContainer)
    assert isinstance(app_c.exchange_gateway, BinanceExchangeAdapter)
    assert isinstance(app_c.notification_gateway, TelegramNotificationAdapter)
    assert isinstance(app_c.event_publisher, InMemoryDomainEventPublisher)


@pytest.mark.asyncio
async def test_container_session_scope():
    app_c = ApplicationContainer()
    async with app_c.session_scope() as session:
        trade_repo = app_c.get_trade_repo(session)
        assert trade_repo is not None
        assert trade_repo.session == session
