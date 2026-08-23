"""Business rules enforcement: 2% Risk Per Trade, Single Active Pair, Whitelist, Max Open Positions."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.database.connection import Base
from src.database.models import Exchange, TradingAccount, Instrument, Watchlist, Strategy, SignalProvider, RiskProfile, DailyRiskConfig, Trade
from src.schemas.master import ExchangeCreate, TradingAccountCreate, InstrumentCreate, WatchlistCreate, StrategyCreate, SignalProviderCreate, RiskProfileCreate
from src.schemas.trade import TradeCreate
from src.domain.entities.signal import ParsedSignalDTO
from src.domain.exceptions.trade import (
    PairAlreadyActiveError,
    SymbolNotWhitelistedError,
)
from src.domain.exceptions.risk import MaxRiskExceededError
from src.repository.exchange_repository import ExchangeRepository
from src.repository.trading_account_repository import TradingAccountRepository
from src.repository.instrument_repository import InstrumentRepository
from src.repository.watchlist_repository import WatchlistRepository
from src.repository.strategy_repository import StrategyRepository
from src.repository.signal_provider_repository import SignalProviderRepository
from src.repository.risk_profile_repository import RiskProfileRepository
from src.repository.trade_repository import TradeRepository
from src.repository.trade_risk_repository import TradeRiskRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.order_repository import OrderRepository
from src.repository.trade_event_repository import TradeEventRepository
from src.services.trade_service import TradeService
from src.services.risk_calculator import RiskCalculatorService
from src.clients.binance_client import BinanceRestClient

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_session():
    """Create in-memory SQLite database session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def business_env(async_session: AsyncSession):
    """Seed test environment with Exchange, Account, Instruments, Watchlist, Strategy, and Risk Profile."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    watch_repo = WatchlistRepository(async_session)
    strat_repo = StrategyRepository(async_session)
    sig_prov_repo = SignalProviderRepository(async_session)
    risk_prof_repo = RiskProfileRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    account = await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id,
        name="Main Account",
        environment="TESTNET",
        is_active=True,
    ))

    # Whitelisted Instrument: BTCUSDT
    btc_inst = await inst_repo.create(InstrumentCreate(
        exchange_id=exchange.id,
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        min_qty=Decimal("0.001"),
        max_qty=Decimal("100"),
        step_size=Decimal("0.001"),
        tick_size=Decimal("0.10"),
        price_precision=2,
        qty_precision=3,
        min_notional=Decimal("5.0"),
        max_leverage=125,
        is_active=True,
    ))
    await watch_repo.create(WatchlistCreate(instrument_id=btc_inst.id, is_active=True))

    # Whitelisted Instrument: ETHUSDT
    eth_inst = await inst_repo.create(InstrumentCreate(
        exchange_id=exchange.id,
        symbol="ETHUSDT",
        base_asset="ETH",
        quote_asset="USDT",
        min_qty=Decimal("0.01"),
        max_qty=Decimal("1000"),
        step_size=Decimal("0.01"),
        tick_size=Decimal("0.01"),
        price_precision=2,
        qty_precision=2,
        min_notional=Decimal("5.0"),
        max_leverage=100,
        is_active=True,
    ))
    await watch_repo.create(WatchlistCreate(instrument_id=eth_inst.id, is_active=True))

    # Non-whitelisted Instrument: SOLUSDT
    sol_inst = await inst_repo.create(InstrumentCreate(
        exchange_id=exchange.id,
        symbol="SOLUSDT",
        base_asset="SOL",
        quote_asset="USDT",
        min_qty=Decimal("0.1"),
        max_qty=Decimal("10000"),
        step_size=Decimal("0.1"),
        tick_size=Decimal("0.01"),
        price_precision=2,
        qty_precision=1,
        min_notional=Decimal("5.0"),
        max_leverage=50,
        is_active=True,
    ))
    # Note: SOLUSDT is NOT added to Watchlist

    strategy = await strat_repo.create(StrategyCreate(name="DefaultStrategy", is_active=True))
    provider = await sig_prov_repo.create(SignalProviderCreate(name="CryptoVIP", channel_id="123456", is_active=True))

    # Risk Profile with max 2 concurrent open positions
    risk_profile = await risk_prof_repo.create(RiskProfileCreate(
        name="Conservative Profile",
        risk_percent=Decimal("2.0"),
        max_daily_loss=Decimal("6.0"),
        max_open_trade=2,
        is_active=True,
    ))

    return {
        "exchange": exchange,
        "account": account,
        "btc_inst": btc_inst,
        "eth_inst": eth_inst,
        "sol_inst": sol_inst,
        "strategy": strategy,
        "provider": provider,
        "risk_profile": risk_profile,
    }


# =============================================================================
# 1. STRICT 2% RISK PER POSITION MATHEMATICAL PROOF
# =============================================================================

@pytest.mark.parametrize("balance,entry,sl,leverage", [
    (Decimal("500.0"), Decimal("50000.0"), Decimal("48000.0"), 10),
    (Decimal("1000.0"), Decimal("50000.0"), Decimal("47500.0"), 20),
    (Decimal("5000.0"), Decimal("3000.0"), Decimal("2850.0"), 15),
    (Decimal("25000.0"), Decimal("150.0"), Decimal("142.5"), 10),
])
def test_strict_2_percent_max_loss_guarantee(balance: Decimal, entry: Decimal, sl: Decimal, leverage: int):
    """Parametrized test proving that for any balance, loss at SL is guaranteed <= 2.0%."""
    calc = RiskCalculatorService()
    res = calc.calculate_position_size(
        wallet_balance=balance,
        risk_percent=Decimal("2.0"),
        entry_price=entry,
        sl_price=sl,
        leverage=leverage,
        step_size=Decimal("0.001"),
        qty_precision=3,
    )

    assert res.is_valid is True
    max_allowable_loss = balance * Decimal("0.02")  # Exactly 2% of capital
    stop_distance = abs(entry - sl)
    actual_loss_at_sl = res.position_size * stop_distance

    # Actual loss must never exceed 2% of capital
    assert actual_loss_at_sl <= max_allowable_loss


# =============================================================================
# 2. BUSINESS RULE: SINGLE ACTIVE POSITION PER PAIR
# =============================================================================

@pytest.mark.asyncio
async def test_reject_duplicate_signal_on_same_pair(async_session: AsyncSession, business_env: dict):
    """Verify that incoming signal on BTCUSDT is rejected if BTCUSDT already has an OPEN position."""
    env = business_env
    trade_repo = TradeRepository(async_session)

    # 1. Create existing active trade on BTCUSDT
    await trade_repo.create(TradeCreate(
        account_id=env["account"].id,
        instrument_id=env["btc_inst"].id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("50000"),
        avg_entry_price=Decimal("50000"),
        sl_price=Decimal("48000"),
        leverage=10,
        position_size=Decimal("0.01"),
        remaining_qty=Decimal("0.01"),
    ))

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=trade_repo,
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        risk_calculator=RiskCalculatorService(),
    )

    new_signal = ParsedSignalDTO(
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        entry_min=Decimal("51000"),
        entry_max=Decimal("51000"),
        sl_price=Decimal("49000"),
        tp_targets=[Decimal("55000")],
        leverage=10,
        raw_text="BUY BTCUSDT",
    )

    with pytest.raises(PairAlreadyActiveError):
        await trade_service.execute_signal(
            signal_dto=new_signal,
            account_id=env["account"].id,
            strategy_id=env["strategy"].id,
        )


# =============================================================================
# 3. BUSINESS RULE: WATCHLIST ENFORCEMENT
# =============================================================================

@pytest.mark.asyncio
async def test_reject_signal_not_in_watchlist(async_session: AsyncSession, business_env: dict):
    """Verify that incoming signal for SOLUSDT (unwhitelisted) is rejected."""
    env = business_env
    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        risk_calculator=RiskCalculatorService(),
    )

    unwhitelisted_signal = ParsedSignalDTO(
        symbol="SOLUSDT",
        side="BUY",
        order_type="MARKET",
        entry_min=Decimal("150"),
        entry_max=Decimal("150"),
        sl_price=Decimal("140"),
        tp_targets=[Decimal("170")],
        leverage=10,
        raw_text="BUY SOLUSDT",
    )

    with pytest.raises(SymbolNotWhitelistedError):
        await trade_service.execute_signal(
            signal_dto=unwhitelisted_signal,
            account_id=env["account"].id,
            strategy_id=env["strategy"].id,
        )


# =============================================================================
# 4. BUSINESS RULE: MAX OPEN POSITIONS LIMIT
# =============================================================================

@pytest.mark.asyncio
async def test_reject_signal_exceeding_max_open_positions(async_session: AsyncSession, business_env: dict):
    """Verify that account with max 2 open positions rejects a 3rd concurrent trade."""
    env = business_env
    trade_repo = TradeRepository(async_session)

    # Fill quota with 2 open trades (BTC and ETH)
    await trade_repo.create(TradeCreate(
        account_id=env["account"].id, instrument_id=env["btc_inst"].id, side="BUY",
        status="OPEN", entry_price=Decimal("50000"), avg_entry_price=Decimal("50000"),
        sl_price=Decimal("48000"), leverage=10, position_size=Decimal("0.01"), remaining_qty=Decimal("0.01"),
    ))
    await trade_repo.create(TradeCreate(
        account_id=env["account"].id, instrument_id=env["eth_inst"].id, side="BUY",
        status="OPEN", entry_price=Decimal("3000"), avg_entry_price=Decimal("3000"),
        sl_price=Decimal("2800"), leverage=10, position_size=Decimal("0.1"), remaining_qty=Decimal("0.1"),
    ))

    # Add a 3rd instrument to watchlist for testing
    inst_repo = InstrumentRepository(async_session)
    watch_repo = WatchlistRepository(async_session)
    bnb_inst = await inst_repo.create(InstrumentCreate(
        exchange_id=env["exchange"].id, symbol="BNBUSDT", base_asset="BNB", quote_asset="USDT",
        min_qty=Decimal("0.01"), max_qty=Decimal("1000"), step_size=Decimal("0.01"),
        tick_size=Decimal("0.01"), price_precision=2, qty_precision=2, min_notional=Decimal("5.0"), max_leverage=50, is_active=True
    ))
    await watch_repo.create(WatchlistCreate(instrument_id=bnb_inst.id, is_active=True))

    mock_binance = BinanceRestClient()
    mock_binance.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("1000.0"), "free_margin": Decimal("800.0")})
    mock_binance.fetch_positions = AsyncMock(return_value=[])
    mock_binance.set_leverage = AsyncMock(return_value={"symbol": "BNBUSDT", "leverage": 10})
    mock_binance.set_margin_mode = AsyncMock(return_value={"symbol": "BNBUSDT", "margin_mode": "ISOLATED"})

    trade_service = TradeService(
        instrument_repo=inst_repo,
        watchlist_repo=watch_repo,
        trade_repo=trade_repo,
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        risk_calculator=RiskCalculatorService(),
        binance_client=mock_binance,
    )

    bnb_signal = ParsedSignalDTO(
        symbol="BNBUSDT",
        side="BUY",
        order_type="MARKET",
        entry_min=Decimal("600"),
        entry_max=Decimal("600"),
        sl_price=Decimal("580"),
        tp_targets=[Decimal("650")],
        leverage=10,
        raw_text="BUY BNBUSDT",
    )

    with pytest.raises(MaxRiskExceededError) as exc_info:
        await trade_service.execute_signal(
            signal_dto=bnb_signal,
            account_id=env["account"].id,
            strategy_id=env["strategy"].id,
        )

    assert "Maximum open positions limit reached" in str(exc_info.value)
