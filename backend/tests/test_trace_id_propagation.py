"""Tests for trace_id generation and propagation across signal and trade lifecycle."""

import pytest
import pytest_asyncio
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.database.connection import Base
from src.database.models import Exchange, TradingAccount, Instrument, Strategy, RiskProfile, Watchlist, DailyRiskConfig
from src.domain.entities.signal import ParsedSignalDTO
from src.services.signal_parser import SignalParserService
from src.services.trade_service import TradeService
from src.repository.instrument_repository import InstrumentRepository
from src.repository.watchlist_repository import WatchlistRepository
from src.repository.trade_repository import TradeRepository
from src.repository.trade_risk_repository import TradeRiskRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.order_repository import OrderRepository
from src.repository.trade_event_repository import TradeEventRepository
from src.repository.risk_profile_repository import RiskProfileRepository
from src.clients.binance_client import BinanceRestClient

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def test_parsed_signal_dto_has_unique_trace_id():
    """Test that ParsedSignalDTO generates unique trace IDs starting with 'sig-'."""
    parser = SignalParserService()
    raw = "BTCUSDT BUY\nENTRY: 50000\nSL: 49000\nTP1: 52000"
    dto1 = parser.parse(raw)
    dto2 = parser.parse(raw)

    assert dto1.trace_id.startswith("sig-")
    assert dto2.trace_id.startswith("sig-")
    assert dto1.trace_id != dto2.trace_id


@pytest.mark.asyncio
async def test_trace_id_propagates_to_trade_event_log(async_session: AsyncSession):
    """Test that trace_id from ParsedSignalDTO is logged into TradeEvent table."""
    exchange = Exchange(code="BINANCE", name="Binance Futures", status=True)
    async_session.add(exchange)
    await async_session.flush()

    account = TradingAccount(
        exchange_id=exchange.id, name="Test Account", account_type="FUTURES", environment="TESTNET", is_active=True
    )
    async_session.add(account)
    await async_session.flush()

    strategy = Strategy(name="Strategy 1", version="1.0.0", is_active=True)
    async_session.add(strategy)
    await async_session.flush()

    inst = Instrument(
        exchange_id=exchange.id, symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
        min_qty=Decimal("0.001"), step_size=Decimal("0.001"),
        tick_size=Decimal("0.10"), price_precision=2, qty_precision=3, min_notional=Decimal("5.0"), is_active=True
    )
    async_session.add(inst)
    await async_session.flush()

    wl = Watchlist(instrument_id=inst.id, enabled=True)
    async_session.add(wl)

    profile = RiskProfile(name="Default", risk_percent=Decimal("2.0"), max_daily_loss=Decimal("6.0"), max_open_trade=3, is_active=True)
    async_session.add(profile)
    await async_session.flush()

    daily_risk = DailyRiskConfig(
        account_id=account.id, risk_profile_id=profile.id, date=datetime.now().date(), balance=Decimal("1000.0"), risk_amount=Decimal("20.0")
    )
    async_session.add(daily_risk)
    await async_session.commit()

    mock_binance = AsyncMock(spec=BinanceRestClient)
    mock_binance.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("1000.0"), "free_margin": Decimal("1000.0")})
    mock_binance.fetch_ticker = AsyncMock(return_value={"last_price": Decimal("50000.0")})
    mock_binance.set_margin_mode = AsyncMock()
    mock_binance.set_leverage = AsyncMock()
    mock_binance.create_entry_order = AsyncMock(return_value={"id": "mkt-123"})
    mock_binance.create_stop_loss_order = AsyncMock(return_value={"id": "sl-123"})
    mock_binance.create_take_profit_order = AsyncMock(return_value={"id": "tp-123"})

    service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        binance_client=mock_binance,
    )

    signal_dto = ParsedSignalDTO(
        raw_text="BTCUSDT BUY",
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        entry_min=Decimal("50000.0"),
        entry_max=Decimal("50000.0"),
        sl_price=Decimal("49000.0"),
        tp_targets=[Decimal("52000.0")],
        confidence_score=0.9,
        is_valid=True,
    )

    result = await service.execute_signal(signal_dto=signal_dto, account_id=account.id)
    assert result.is_success is True

    events = await service.trade_event_repo.get_events_by_trade(result.trade_id)
    assert len(events) > 0
    assert "trace_id" in events[0].payload_json
    assert signal_dto.trace_id in events[0].payload_json
