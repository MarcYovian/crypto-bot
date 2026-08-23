"""End-to-End (E2E) Integration Tests for the Crypto Trading Bot.

Tests the full trading lifecycle across all Clean Architecture layers:
Database -> Repositories -> External Clients -> Domain Services -> Scheduler & Telegram.
"""

from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.database.connection import Base
from src.database.models import (
    Exchange, TradingAccount, Instrument, Watchlist,
    Strategy, SignalProvider, RiskProfile, Trade,
    Order, Execution, TradeSummary, DailyRiskConfig,
    TradeRisk, TradeEvent, BotLog, BotSetting
)
from src.schemas.master import (
    ExchangeCreate, TradingAccountCreate, InstrumentCreate,
    WatchlistCreate, StrategyCreate, SignalProviderCreate, RiskProfileCreate
)
from src.schemas.trade import TradeCreate
from src.schemas.risk import DailyRiskConfigCreate, TradeRiskCreate
from src.domain.entities.trade import OrderFillDTO
from src.domain.exceptions.trade import DailyRiskLimitReachedError
from src.repository.exchange_repository import ExchangeRepository
from src.repository.trading_account_repository import TradingAccountRepository
from src.repository.risk_profile_repository import RiskProfileRepository
from src.repository.instrument_repository import InstrumentRepository
from src.repository.watchlist_repository import WatchlistRepository
from src.repository.strategy_repository import StrategyRepository
from src.repository.signal_provider_repository import SignalProviderRepository
from src.repository.signal_repository import SignalRepository
from src.repository.trade_repository import TradeRepository
from src.repository.trade_risk_repository import TradeRiskRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.order_repository import OrderRepository
from src.repository.execution_repository import ExecutionRepository
from src.repository.trade_event_repository import TradeEventRepository
from src.repository.trade_summary_repository import TradeSummaryRepository
from src.repository.bot_log_repository import BotLogRepository
from src.repository.bot_setting_repository import BotSettingRepository
from src.services.precision_filter import PrecisionFilterService
from src.services.signal_parser import SignalParserService
from src.services.risk_calculator import RiskCalculatorService
from src.services.trade_service import TradeService
from src.services.position_manager import PositionManager
from src.services.scheduler_service import SchedulerService
from src.services.telegram_service import TelegramService

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def e2e_session():
    """Create an isolated in-memory SQLite database session for E2E integration tests."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def seed_data(e2e_session: AsyncSession):
    """Seed base master data for E2E testing."""
    ex_repo = ExchangeRepository(e2e_session)
    acc_repo = TradingAccountRepository(e2e_session)
    inst_repo = InstrumentRepository(e2e_session)
    watch_repo = WatchlistRepository(e2e_session)
    strat_repo = StrategyRepository(e2e_session)
    prov_repo = SignalProviderRepository(e2e_session)
    risk_repo = RiskProfileRepository(e2e_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance Futures", status=True))
    account = await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id,
        name="Main Futures Account",
        environment="MAINNET",
        is_active=True,
    ))
    btc_inst = await inst_repo.create(InstrumentCreate(
        exchange_id=exchange.id,
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        tick_size=Decimal("0.1"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5.0"),
        price_precision=1,
        qty_precision=3,
        is_active=True,
    ))
    eth_inst = await inst_repo.create(InstrumentCreate(
        exchange_id=exchange.id,
        symbol="ETHUSDT",
        base_asset="ETH",
        quote_asset="USDT",
        tick_size=Decimal("0.01"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5.0"),
        price_precision=2,
        qty_precision=3,
        is_active=True,
    ))
    btc_watch = await watch_repo.create(WatchlistCreate(
        account_id=account.id,
        instrument_id=btc_inst.id,
        is_enabled=True,
        max_leverage=20,
    ))
    eth_watch = await watch_repo.create(WatchlistCreate(
        account_id=account.id,
        instrument_id=eth_inst.id,
        is_enabled=True,
        max_leverage=20,
    ))
    strategy = await strat_repo.create(StrategyCreate(name="Breakout Strategy", is_active=True))
    provider = await prov_repo.create(SignalProviderCreate(name="Alpha Signals VIP", type="TELEGRAM_CHANNEL", is_active=True))
    risk_profile = await risk_repo.create(RiskProfileCreate(name="Default 2.0% Risk", is_active=True))

    return {
        "exchange": exchange,
        "account": account,
        "instrument": btc_inst,
        "eth_instrument": eth_inst,
        "watchlist": btc_watch,
        "eth_watchlist": eth_watch,
        "strategy": strategy,
        "provider": provider,
        "risk_profile": risk_profile,
    }


@pytest.mark.asyncio
async def test_e2e_full_trade_lifecycle_win(e2e_session: AsyncSession, seed_data: dict):
    """End-to-End Test: Full winning trade lifecycle from Signal -> Multi-TP Fill -> BEP & Trailing -> Final Closure & Report."""
    acc = seed_data["account"]
    inst = seed_data["instrument"]

    # 1. Mock Binance and Telegram Clients
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={
        "total_wallet_balance": Decimal("10000.0"),
        "free_margin": Decimal("10000.0"),
        "unrealized_pnl": Decimal("0.0"),
    })
    mock_binance.set_leverage = AsyncMock(return_value={"leverage": 20})
    mock_binance.set_margin_mode = AsyncMock(return_value={"margin_mode": "ISOLATED"})
    mock_binance.create_entry_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_entry_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_stop_loss_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_sl_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_take_profit_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_tp_{kwargs.get('client_order_id', '1')}"})
    mock_binance.cancel_order = AsyncMock(return_value=True)
    mock_binance.cancel_all_orders = AsyncMock(return_value=True)

    mock_telegram = MagicMock()
    mock_telegram.send_message = AsyncMock()
    mock_telegram.send_signal_confirmation = AsyncMock()
    mock_telegram.send_trade_alert = AsyncMock()
    mock_telegram.edit_message_text = AsyncMock()

    # 2. Instantiate all repositories
    inst_repo = InstrumentRepository(e2e_session)
    watch_repo = WatchlistRepository(e2e_session)
    trade_repo = TradeRepository(e2e_session)
    trade_risk_repo = TradeRiskRepository(e2e_session)
    daily_risk_repo = DailyRiskRepository(e2e_session)
    order_repo = OrderRepository(e2e_session)
    exec_repo = ExecutionRepository(e2e_session)
    trade_event_repo = TradeEventRepository(e2e_session)
    trade_sum_repo = TradeSummaryRepository(e2e_session)
    bot_log_repo = BotLogRepository(e2e_session)
    bot_setting_repo = BotSettingRepository(e2e_session)
    signal_repo = SignalRepository(e2e_session)
    risk_prof_repo = RiskProfileRepository(e2e_session)
    acc_repo = TradingAccountRepository(e2e_session)

    # 3. Instantiate Domain Services
    precision_service = PrecisionFilterService()
    signal_parser = SignalParserService()
    risk_calculator = RiskCalculatorService()
    
    trade_service = TradeService(
        instrument_repo=inst_repo,
        watchlist_repo=watch_repo,
        trade_repo=trade_repo,
        trade_risk_repo=trade_risk_repo,
        daily_risk_repo=daily_risk_repo,
        order_repo=order_repo,
        trade_event_repo=trade_event_repo,
        risk_calculator=risk_calculator,
        binance_client=mock_binance,
        telegram_client=mock_telegram,
    )

    position_manager = PositionManager(
        trade_repo=trade_repo,
        order_repo=order_repo,
        execution_repo=exec_repo,
        trade_event_repo=trade_event_repo,
        trade_summary_repo=trade_sum_repo,
        daily_risk_repo=daily_risk_repo,
        binance_client=mock_binance,
        telegram_client=mock_telegram,
    )

    scheduler = SchedulerService(
        daily_risk_repo=daily_risk_repo,
        trading_account_repo=acc_repo,
        risk_profile_repo=risk_prof_repo,
        trade_repo=trade_repo,
        order_repo=order_repo,
        instrument_repo=inst_repo,
        trade_summary_repo=trade_sum_repo,
        trade_event_repo=trade_event_repo,
        bot_log_repo=bot_log_repo,
        bot_setting_repo=bot_setting_repo,
        position_manager=position_manager,
        binance_client=mock_binance,
        telegram_client=mock_telegram,
    )

    tg_service = TelegramService(
        signal_parser=signal_parser,
        risk_calculator=risk_calculator,
        trade_service=trade_service,
        signal_repo=signal_repo,
        trade_repo=trade_repo,
        order_repo=order_repo,
        daily_risk_repo=daily_risk_repo,
        trade_summary_repo=trade_sum_repo,
        watchlist_repo=watch_repo,
        instrument_repo=inst_repo,
        risk_profile_repo=risk_prof_repo,
        bot_log_repo=bot_log_repo,
        bot_setting_repo=bot_setting_repo,
        position_manager=position_manager,
        binance_client=mock_binance,
        telegram_client=mock_telegram,
    )

    # -------------------------------------------------------------------------
    # STAGE 1: 00:00 WIB Daily Risk Snapshot
    # -------------------------------------------------------------------------
    snapshot = await scheduler.run_daily_risk_snapshot_job(account_id=acc.id)
    assert snapshot is not None
    assert snapshot.balance == Decimal("10000.0")
    assert snapshot.risk_amount == Decimal("200.0")  # 2% of $10,000

    # -------------------------------------------------------------------------
    # STAGE 2: Incoming Signal Message via Telegram
    # -------------------------------------------------------------------------
    raw_signal_text = (
        "⚡ VIP SIGNAL ⚡\n"
        "Pair: BTC/USDT (LONG)\n"
        "Leverage: 20x\n"
        "Entry: 60000\n"
        "Targets: 62000, 64000, 66000\n"
        "Stop Loss: 58000"
    )

    sig_res = await tg_service.handle_incoming_signal_message(raw_signal_text)
    assert sig_res["status"] == "PENDING_CONFIRMATION"
    signal_id = sig_res["signal_id"]

    # -------------------------------------------------------------------------
    # STAGE 3: Admin Approves Signal via Inline Button
    # -------------------------------------------------------------------------
    cb_res = await tg_service.handle_callback_query(f"APPROVE_{signal_id}", message_id=555)
    assert cb_res["status"] == "APPROVED"
    trade_id = cb_res["trade_id"]

    # Verify initial trade record in DB
    trade = await trade_repo.get(trade_id)
    assert trade.status == "WAITING_ENTRY"
    assert trade.position_size == Decimal("0.100")  # $200 risk / (60000 - 58000) = 0.100 BTC
    assert trade.remaining_qty == Decimal("0.100")

    # Verify orders created: 1 Entry + 1 SL + 3 TPs = 5 orders
    orders = await order_repo.get_orders_by_trade_id(trade_id)
    assert len(orders) == 5

    # -------------------------------------------------------------------------
    # STAGE 4: WebSocket Receives Entry Order Fill
    # -------------------------------------------------------------------------
    entry_order = next(o for o in orders if o.purpose == "ENTRY")
    await position_manager.handle_order_fill(
        OrderFillDTO(
            order_id=entry_order.id,
            exchange_order_id=entry_order.exchange_order_id,
            trade_id=trade_id,
            symbol="BTCUSDT",
            side="BUY",
            purpose="ENTRY",
            fill_price=Decimal("60000.0"),
            fill_qty=Decimal("0.100"),
            fee=Decimal("1.20"),
            realized_pnl=Decimal("0.0"),
        )
    )

    trade = await trade_repo.get(trade_id)
    assert trade.status == "OPEN"
    assert trade.entry_price == Decimal("60000.0")

    # -------------------------------------------------------------------------
    # STAGE 5: WebSocket Receives TP1 Fill (50% = 0.050 BTC at 62,000) -> Move SL to BEP
    # -------------------------------------------------------------------------
    tp1_order = next(o for o in orders if o.purpose == "TP1")
    await position_manager.handle_order_fill(
        OrderFillDTO(
            order_id=tp1_order.id,
            exchange_order_id=tp1_order.exchange_order_id,
            trade_id=trade_id,
            symbol="BTCUSDT",
            side="SELL",
            purpose="TP1",
            fill_price=Decimal("62000.0"),
            fill_qty=Decimal("0.050"),
            fee=Decimal("0.62"),
            realized_pnl=Decimal("100.0"),
        )
    )

    trade = await trade_repo.get(trade_id)
    assert trade.status == "PARTIAL"
    assert trade.remaining_qty == Decimal("0.050")
    assert trade.sl_price == Decimal("60000.0")  # SL shifted to Break-Even (entry price)

    # -------------------------------------------------------------------------
    # STAGE 6: WebSocket Receives TP2 Fill (25% = 0.025 BTC at 64,000) -> Shift SL to Trailing (TP1 price)
    # -------------------------------------------------------------------------
    tp2_order = next(o for o in orders if o.purpose == "TP2")
    await position_manager.handle_order_fill(
        OrderFillDTO(
            order_id=tp2_order.id,
            exchange_order_id=tp2_order.exchange_order_id,
            trade_id=trade_id,
            symbol="BTCUSDT",
            side="SELL",
            purpose="TP2",
            fill_price=Decimal("64000.0"),
            fill_qty=Decimal("0.025"),
            fee=Decimal("0.32"),
            realized_pnl=Decimal("100.0"),
        )
    )

    trade = await trade_repo.get(trade_id)
    assert trade.status == "PARTIAL"
    assert trade.remaining_qty == Decimal("0.025")
    assert trade.sl_price == Decimal("62000.0")  # SL shifted to Trailing (TP1 price)

    # -------------------------------------------------------------------------
    # STAGE 7: WebSocket Receives TP3 Fill (25% = 0.025 BTC at 66,000) -> Finalize Trade WIN
    # -------------------------------------------------------------------------
    tp3_order = next(o for o in orders if o.purpose == "TP3")
    await position_manager.handle_order_fill(
        OrderFillDTO(
            order_id=tp3_order.id,
            exchange_order_id=tp3_order.exchange_order_id,
            trade_id=trade_id,
            symbol="BTCUSDT",
            side="SELL",
            purpose="TP3",
            fill_price=Decimal("66000.0"),
            fill_qty=Decimal("0.025"),
            fee=Decimal("0.33"),
            realized_pnl=Decimal("150.0"),
        )
    )

    trade = await trade_repo.get(trade_id)
    assert trade.status == "CLOSED"
    assert trade.remaining_qty == Decimal("0.0")

    # Verify TradeSummary record
    summary = await trade_sum_repo.get_by_trade_id(trade_id)
    assert summary is not None
    assert summary.result == "WIN"
    assert summary.gross_pnl == Decimal("350.0")
    assert summary.commission == Decimal("2.47")
    assert summary.net_pnl == Decimal("347.53")

    # -------------------------------------------------------------------------
    # STAGE 8: Daily Performance Recap Check via Telegram & Scheduler
    # -------------------------------------------------------------------------
    recap = await scheduler.run_daily_performance_report_job(account_id=acc.id)
    assert recap["total_trades"] == 1
    assert recap["wins"] == 1
    assert recap["win_rate"] == 100.0
    assert recap["net_pnl"] == 347.53

    # Check Telegram /summary response
    summary_resp = await tg_service.handle_command("/summary")
    assert "Win Rate: <b>100.0%</b>" in summary_resp
    assert "347.53 USDT" in summary_resp


@pytest.mark.asyncio
async def test_e2e_trade_lifecycle_stop_loss_hit(e2e_session: AsyncSession, seed_data: dict):
    """End-to-End Test: Trade opens and hits Stop Loss before reaching TP1."""
    acc = seed_data["account"]

    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("10000.0"), "free_margin": Decimal("10000.0")})
    mock_binance.set_leverage = AsyncMock(return_value={"leverage": 20})
    mock_binance.set_margin_mode = AsyncMock(return_value={"margin_mode": "ISOLATED"})
    mock_binance.create_entry_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_entry_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_stop_loss_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_sl_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_take_profit_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_tp_{kwargs.get('client_order_id', '1')}"})
    mock_binance.cancel_order = AsyncMock(return_value=True)

    trade_repo = TradeRepository(e2e_session)
    order_repo = OrderRepository(e2e_session)
    exec_repo = ExecutionRepository(e2e_session)
    trade_event_repo = TradeEventRepository(e2e_session)
    trade_sum_repo = TradeSummaryRepository(e2e_session)
    daily_risk_repo = DailyRiskRepository(e2e_session)
    inst_repo = InstrumentRepository(e2e_session)
    watch_repo = WatchlistRepository(e2e_session)
    trade_risk_repo = TradeRiskRepository(e2e_session)
    risk_prof_repo = RiskProfileRepository(e2e_session)
    acc_repo = TradingAccountRepository(e2e_session)

    precision_service = PrecisionFilterService()
    signal_parser = SignalParserService()
    risk_calculator = RiskCalculatorService()

    trade_service = TradeService(
        instrument_repo=inst_repo,
        watchlist_repo=watch_repo,
        trade_repo=trade_repo,
        trade_risk_repo=trade_risk_repo,
        daily_risk_repo=daily_risk_repo,
        order_repo=order_repo,
        trade_event_repo=trade_event_repo,
        risk_calculator=risk_calculator,
        binance_client=mock_binance,
    )

    position_manager = PositionManager(
        trade_repo=trade_repo,
        order_repo=order_repo,
        execution_repo=exec_repo,
        trade_event_repo=trade_event_repo,
        trade_summary_repo=trade_sum_repo,
        daily_risk_repo=daily_risk_repo,
        binance_client=mock_binance,
    )

    # 1. Snapshot
    scheduler = SchedulerService(
        daily_risk_repo=daily_risk_repo,
        trading_account_repo=acc_repo,
        risk_profile_repo=risk_prof_repo,
        trade_repo=trade_repo,
        order_repo=order_repo,
        instrument_repo=inst_repo,
        trade_summary_repo=trade_sum_repo,
        trade_event_repo=trade_event_repo,
        bot_log_repo=BotLogRepository(e2e_session),
        bot_setting_repo=BotSettingRepository(e2e_session),
        binance_client=mock_binance,
    )
    await scheduler.run_daily_risk_snapshot_job(account_id=acc.id)

    # 2. Execute trade
    parsed = signal_parser.parse("BUY BTCUSDT Entry: 60000 SL: 58000 TP: 64000 Leverage: 20")
    exec_res = await trade_service.execute_signal(parsed, account_id=acc.id)
    trade_id = exec_res.trade_id

    # 3. Entry fill
    orders = await order_repo.get_orders_by_trade_id(trade_id)
    entry_o = next(o for o in orders if o.purpose == "ENTRY")
    await position_manager.handle_order_fill(
        OrderFillDTO(
            order_id=entry_o.id,
            exchange_order_id=entry_o.exchange_order_id,
            trade_id=trade_id,
            symbol="BTCUSDT",
            side="BUY",
            purpose="ENTRY",
            fill_price=Decimal("60000.0"),
            fill_qty=Decimal("0.100"),
            fee=Decimal("1.20"),
            realized_pnl=Decimal("0.0"),
        )
    )

    # 4. SL fill (Price dumped to 58,000)
    sl_o = next(o for o in orders if o.purpose == "SL")
    await position_manager.handle_order_fill(
        OrderFillDTO(
            order_id=sl_o.id,
            exchange_order_id=sl_o.exchange_order_id,
            trade_id=trade_id,
            symbol="BTCUSDT",
            side="SELL",
            purpose="SL",
            fill_price=Decimal("58000.0"),
            fill_qty=Decimal("0.100"),
            fee=Decimal("1.16"),
            realized_pnl=Decimal("-200.0"),
        )
    )

    trade = await trade_repo.get(trade_id)
    assert trade.status == "CLOSED"

    summary = await trade_sum_repo.get_by_trade_id(trade_id)
    assert summary is not None
    assert summary.result == "LOSS"
    assert summary.gross_pnl == Decimal("-200.0")
    assert summary.net_pnl == Decimal("-202.36")


@pytest.mark.asyncio
async def test_e2e_circuit_breaker_lockout(e2e_session: AsyncSession, seed_data: dict):
    """End-to-End Test: Circuit breaker locks out new trades when daily loss limit is reached."""
    acc = seed_data["account"]
    eth_inst = seed_data["eth_instrument"]

    trade_repo = TradeRepository(e2e_session)
    order_repo = OrderRepository(e2e_session)
    daily_risk_repo = DailyRiskRepository(e2e_session)
    inst_repo = InstrumentRepository(e2e_session)
    watch_repo = WatchlistRepository(e2e_session)
    trade_risk_repo = TradeRiskRepository(e2e_session)
    trade_event_repo = TradeEventRepository(e2e_session)

    # Create daily snapshot with $200 risk budget
    snapshot = await daily_risk_repo.get_or_create_daily_snapshot(
        DailyRiskConfigCreate(
            account_id=acc.id,
            risk_profile_id=seed_data["risk_profile"].id,
            date=datetime.now().date(),
            balance=Decimal("10000.0"),
            risk_amount=Decimal("200.0"),
        )
    )

    # Add an active trade on ETHUSDT that already uses $200 of risk budget
    t = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=eth_inst.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("3000.0"),
        sl_price=Decimal("2900.0"),
        leverage=20,
        position_size=Decimal("2.0"),
        remaining_qty=Decimal("2.0"),
    ))

    await trade_risk_repo.create(TradeRiskCreate(
        trade_id=t.id,
        daily_risk_id=snapshot.id,
        entry=Decimal("3000.0"),
        stop=Decimal("2900.0"),
        stop_distance=Decimal("100.0"),
        qty=Decimal("2.0"),
        margin=Decimal("300.0"),
        risk_amount=Decimal("200.0"),
        leverage=20,
    ))

    precision_service = PrecisionFilterService()
    signal_parser = SignalParserService()
    risk_calculator = RiskCalculatorService()

    trade_service = TradeService(
        instrument_repo=inst_repo,
        watchlist_repo=watch_repo,
        trade_repo=trade_repo,
        trade_risk_repo=trade_risk_repo,
        daily_risk_repo=daily_risk_repo,
        order_repo=order_repo,
        trade_event_repo=trade_event_repo,
        risk_calculator=risk_calculator,
    )

    # Attempting to execute a new trade on BTCUSDT must raise DailyRiskLimitReachedError
    parsed = signal_parser.parse("BUY BTCUSDT Entry: 60000 SL: 58000 TP: 64000 Leverage: 20")
    with pytest.raises(DailyRiskLimitReachedError) as exc_info:
        await trade_service.execute_signal(parsed, account_id=acc.id)

    assert "Daily risk limit breached" in str(exc_info.value)
