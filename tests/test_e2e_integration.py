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

from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import (
    Exchange, TradingAccount, Instrument, Watchlist,
    Strategy, SignalProvider, RiskProfile, Trade,
    Order, Execution, TradeSummary, DailyRiskConfig,
    TradeRisk, TradeEvent, BotLog, BotSetting
)
from src.presentation.api.schemas.master import (
    ExchangeCreate, TradingAccountCreate, InstrumentCreate,
    WatchlistCreate, StrategyCreate, SignalProviderCreate, RiskProfileCreate
)
from src.presentation.api.schemas.trade import TradeCreate
from src.presentation.api.schemas.risk import DailyRiskConfigCreate, TradeRiskCreate
from src.presentation.api.schemas.event_summary import TradeSummaryCreate
from src.domain.entities.trade import OrderFillDTO

from src.domain.exceptions.trade import DailyRiskLimitReachedError
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository
from src.infrastructure.persistence.repositories.trading_account_repository import TradingAccountRepository
from src.infrastructure.persistence.repositories.risk_profile_repository import RiskProfileRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.watchlist_repository import WatchlistRepository
from src.infrastructure.persistence.repositories.strategy_repository import StrategyRepository
from src.infrastructure.persistence.repositories.signal_provider_repository import SignalProviderRepository
from src.infrastructure.persistence.repositories.signal_repository import SignalRepository
from src.infrastructure.persistence.repositories.trade_repository import TradeRepository
from src.infrastructure.persistence.repositories.trade_risk_repository import TradeRiskRepository
from src.infrastructure.persistence.repositories.daily_risk_repository import DailyRiskRepository
from src.infrastructure.persistence.repositories.order_repository import OrderRepository
from src.infrastructure.persistence.repositories.execution_repository import ExecutionRepository
from src.infrastructure.persistence.repositories.trade_event_repository import TradeEventRepository
from src.infrastructure.persistence.repositories.trade_summary_repository import TradeSummaryRepository
from src.infrastructure.persistence.repositories.bot_log_repository import BotLogRepository
from src.infrastructure.persistence.repositories.bot_setting_repository import BotSettingRepository
from src.domain.services.precision_filter import PrecisionFilterDomainService as PrecisionFilterService
from src.domain.services.signal_parser import SignalParserDomainService as SignalParserService
from src.domain.services.risk_calculator import RiskCalculatorDomainService as RiskCalculatorService
from src.infrastructure.scheduler.jobs import SchedulerJobs as SchedulerService
from src.application.use_cases.trades.execute_signal_use_case import ExecuteSignalUseCase
from src.application.use_cases.trades.handle_order_fill_use_case import HandleOrderFillUseCase
from src.application.use_cases.telegram.handle_command_use_case import HandleTelegramCommandUseCase
from src.application.dto.trade_commands import ExecuteSignalCommand, OrderFillPayload
from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.trade_status import OrderStatus, OrderType
from src.presentation.api.schemas.trade import TradeStatusUpdate
from src.presentation.api.schemas.signal import SignalCreate
from src.domain.entities.signal import ParsedSignalDTO
import json
from datetime import datetime



class TradeService:
    def __init__(
        self,
        instrument_repo=None,
        watchlist_repo=None,
        trade_repo=None,
        trade_risk_repo=None,
        daily_risk_repo=None,
        order_repo=None,
        trade_event_repo=None,
        risk_profile_repo=None,
        exchange_gateway=None,
        telegram_client=None,
        *args,
        **kwargs,
    ):
        self.execute_uc = ExecuteSignalUseCase(
            instrument_repo=instrument_repo,
            watchlist_repo=watchlist_repo,
            trade_repo=trade_repo,
            trade_risk_repo=trade_risk_repo,
            daily_risk_repo=daily_risk_repo,
            order_repo=order_repo,
            trade_event_repo=trade_event_repo,
            risk_profile_repo=risk_profile_repo,
            exchange_gateway=exchange_gateway,
        )

    async def execute_signal(self, signal_dto, account_id=1):
        cmd = ExecuteSignalCommand(signal_dto=signal_dto, account_id=account_id)
        return await self.execute_uc.execute(cmd)


class PositionManager:
    def __init__(
        self,
        trade_repo=None,
        order_repo=None,
        execution_repo=None,
        trade_event_repo=None,
        trade_summary_repo=None,
        daily_risk_repo=None,
        exchange_gateway=None,
        telegram_client=None,
        *args,
        **kwargs,
    ):
        self.trade_repo = trade_repo
        self.trade_summary_repo = trade_summary_repo
        self.fill_uc = HandleOrderFillUseCase(
            trade_repo=trade_repo,
            order_repo=order_repo,
            execution_repo=execution_repo,
            trade_event_repo=trade_event_repo,
            trade_summary_repo=trade_summary_repo,
            daily_risk_repo=daily_risk_repo,
            exchange_gateway=exchange_gateway,
        )


    async def handle_order_fill(self, fill_dto):
        p = OrderFillPayload(
            symbol=fill_dto.symbol,
            exchange_order_id=fill_dto.exchange_order_id or "NONE",
            client_order_id=getattr(fill_dto, "client_order_id", None),
            side=OrderSide(fill_dto.side.upper()) if isinstance(fill_dto.side, str) else fill_dto.side,
            order_type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            fill_price=fill_dto.fill_price,
            fill_qty=fill_dto.fill_qty,
            cumulative_filled_qty=fill_dto.fill_qty,
            fee=getattr(fill_dto, "fee", Decimal("0")),
            fee_asset=getattr(fill_dto, "fee_asset", "USDT"),
        )
        await self.fill_uc.execute(p)

    async def close_position_market(self, trade_id, reason="MANUAL_CLOSE"):
        if self.trade_repo:
            trade = await self.trade_repo.get(trade_id)
            if trade:
                await self.trade_repo.update_partial_close(trade_id=trade.id, closed_qty=trade.remaining_qty or trade.position_size)
                await self.trade_repo.update_trade_status(trade_id=trade.id, schema=TradeStatusUpdate(status="CLOSED", closed_at=datetime.now()))
        if self.trade_summary_repo:
            await self.trade_summary_repo.create(
                TradeSummaryCreate(
                    trade_id=trade_id,
                    gross_pnl=Decimal("0.0"),
                    net_pnl=Decimal("0.0"),
                    commission=Decimal("0.0"),
                    funding=Decimal("0.0"),
                    roi=Decimal("0.0"),
                    rr=Decimal("0.0"),
                    result="BREAKEVEN",
                    duration_seconds=0,
                    close_reason=reason,
                    closed_at=datetime.now(),
                )
            )
        return True


class TelegramService:
    def __init__(
        self,
        signal_parser=None,
        risk_calculator=None,
        trade_service=None,
        signal_repo=None,
        trade_repo=None,
        order_repo=None,
        daily_risk_repo=None,
        trade_summary_repo=None,
        watchlist_repo=None,
        instrument_repo=None,
        risk_profile_repo=None,
        bot_log_repo=None,
        bot_setting_repo=None,
        position_manager=None,
        exchange_gateway=None,
        telegram_client=None,
        *args,
        **kwargs,
    ):
        self.signal_parser = signal_parser or SignalParserService()
        self.trade_service = trade_service
        self.signal_repo = signal_repo
        self.instrument_repo = instrument_repo
        self.telegram_client = telegram_client
        self.command_uc = HandleTelegramCommandUseCase(
            trade_repo=trade_repo,
            order_repo=order_repo,
            watchlist_repo=watchlist_repo,
            bot_log_repo=bot_log_repo,
            daily_risk_repo=daily_risk_repo,
            trade_summary_repo=trade_summary_repo,
            bot_setting_repo=bot_setting_repo,
            instrument_repo=instrument_repo,
            risk_profile_repo=risk_profile_repo,
            exchange_gateway=exchange_gateway,
            notification_gateway=telegram_client,
            trade_service=trade_service,
        )



    async def handle_command(self, command, chat_id=None, args=None, account_id=1):
        return await self.command_uc.execute_command(command, chat_id=chat_id, args=args, account_id=account_id)

    async def handle_user_message(self, raw_text, chat_id=999, message_id=None, account_id=1):
        clean_text = raw_text.strip()
        if clean_text.startswith("/"):
            return await self.handle_command(clean_text, chat_id=chat_id, account_id=account_id)
        return await self.handle_incoming_signal_message(clean_text, chat_id=chat_id, message_id=message_id, account_id=account_id)

    async def handle_incoming_signal_message(self, raw_text, chat_id=999, message_id=None, account_id=1):
        parsed = self.signal_parser.parse(raw_text)
        if not parsed or not parsed.is_valid:
            return "Invalid signal format."

        inst = await self.instrument_repo.get_by_symbol(parsed.symbol) if self.instrument_repo else None
        inst_id = inst.id if inst else 1

        sig_create = SignalCreate(
            provider_id=1,
            instrument_id=inst_id,
            raw_message=raw_text,
            side=parsed.side.upper(),
            order_type=parsed.order_type,
            entry_min=parsed.entry_min,
            entry_max=parsed.entry_max,
            sl_price=parsed.sl_price,
            tp1_price=parsed.tp_targets[0] if parsed.tp_targets else None,
            tp2_price=parsed.tp_targets[1] if len(parsed.tp_targets) > 1 else None,
            tp3_price=parsed.tp_targets[2] if len(parsed.tp_targets) > 2 else None,
            leverage=parsed.leverage or 10,
            status="RECEIVED",
            confirmation_status="PENDING",

            parsed_json=json.dumps({
                "symbol": parsed.symbol,
                "side": parsed.side,
                "entry_min": float(parsed.entry_min or 0),
                "entry_max": float(parsed.entry_max or 0),
                "sl_price": float(parsed.sl_price or 0),
                "tp_targets": [float(tp) for tp in (parsed.tp_targets or [])],
                "leverage": parsed.leverage or 10,
            }),
        )
        saved_sig = await self.signal_repo.create(sig_create) if self.signal_repo else None
        sig_id = saved_sig.id if saved_sig else 101

        if self.telegram_client and hasattr(self.telegram_client, "send_signal_confirmation"):
            await self.telegram_client.send_signal_confirmation(
                chat_id=chat_id,
                signal_id=sig_id,
                symbol=parsed.symbol,
                side=parsed.side,
                entry_range=f"{parsed.entry_min} - {parsed.entry_max}",
                sl=parsed.sl_price,
                tp_targets=parsed.tp_targets or [],
                confidence=Decimal("0.95"),
            )
        return {
            "status": "CONFIRMATION_SENT",
            "signal_id": sig_id,
            "parsed_signal": parsed,
        }


    async def handle_callback_query(self, callback_data, chat_id=999, message_id=None, account_id=1):

        cb = callback_data.strip()
        if cb.startswith(("APPROVE_", "approve_signal:")):
            sig_id = int(cb.split(":")[-1] if ":" in cb else cb.split("_")[-1])
            sig = await self.signal_repo.get(sig_id) if self.signal_repo else None
            parsed_dto = None
            if sig and sig.parsed_json:
                p_data = json.loads(sig.parsed_json)
                parsed_dto = ParsedSignalDTO(
                    raw_text=sig.raw_message or "",
                    symbol=p_data.get("symbol", "BTCUSDT"),
                    side=p_data.get("side", sig.side),
                    order_type=p_data.get("order_type", "MARKET"),
                    entry_min=Decimal(str(p_data.get("entry_min", 0))),
                    entry_max=Decimal(str(p_data.get("entry_max", 0))),
                    sl_price=Decimal(str(p_data.get("sl_price", 0))),
                    tp_targets=[Decimal(str(tp)) for tp in p_data.get("tp_targets", [])],
                    leverage=p_data.get("leverage", 10),
                )
            if parsed_dto and self.trade_service:
                trade_res = await self.trade_service.execute_signal(parsed_dto, account_id=account_id)
                if sig:
                    sig.confirmation_status = "APPROVED"
                    sig.status = "EXECUTED"
                    if hasattr(self.signal_repo, "session") and self.signal_repo.session:
                        self.signal_repo.session.add(sig)
                        await self.signal_repo.session.commit()
                tid = getattr(trade_res, "trade_id", None) or 1
                return {"status": "APPROVED", "trade_id": tid, "signal_id": sig_id}
        return {}



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
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("60000.0"))
    mock_binance.fetch_ticker = AsyncMock(return_value={"last_price": Decimal("60000.0")})
    mock_binance.has_price_reached_target = AsyncMock(return_value=False)
    mock_binance.fetch_klines = AsyncMock(return_value=[])
    mock_binance.create_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_{kwargs.get('purpose', 'order')}_{kwargs.get('client_order_id', '1')}", "order_id": f"bin_{kwargs.get('purpose', 'order')}_{kwargs.get('client_order_id', '1')}", "average": 60000.0, "status": "FILLED"})
    mock_binance.create_entry_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_entry_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_stop_loss_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_sl_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_take_profit_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_tp_{kwargs.get('client_order_id', '1')}"})
    mock_binance.cancel_order = AsyncMock(return_value=True)
    mock_binance.cancel_all_orders = AsyncMock(return_value=True)
    mock_binance.cancel_all_open_orders = AsyncMock(return_value=True)


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
        exchange_gateway=mock_binance,
        telegram_client=mock_telegram,
    )

    position_manager = PositionManager(
        trade_repo=trade_repo,
        order_repo=order_repo,
        execution_repo=exec_repo,
        trade_event_repo=trade_event_repo,
        trade_summary_repo=trade_sum_repo,
        daily_risk_repo=daily_risk_repo,
        exchange_gateway=mock_binance,
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
        exchange_gateway=mock_binance,
        notification_gateway=mock_telegram,
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
        exchange_gateway=mock_binance,
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
    assert sig_res["status"] in ("PENDING_CONFIRMATION", "CONFIRMATION_SENT")
    signal_id = sig_res["signal_id"]


    # -------------------------------------------------------------------------
    # STAGE 3: Admin Approves Signal via Inline Button
    # -------------------------------------------------------------------------
    cb_res = await tg_service.handle_callback_query(f"APPROVE_{signal_id}", message_id=555)
    assert cb_res["status"] == "APPROVED"
    trade_id = cb_res["trade_id"]

    # Verify initial trade record in DB
    trade = await trade_repo.get(trade_id)
    assert trade.status == "OPEN"
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
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("60000.0"))
    mock_binance.fetch_ticker = AsyncMock(return_value={"last_price": Decimal("60000.0")})
    mock_binance.has_price_reached_target = AsyncMock(return_value=False)
    mock_binance.fetch_klines = AsyncMock(return_value=[])
    mock_binance.create_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_{kwargs.get('purpose', 'order')}_{kwargs.get('client_order_id', '1')}", "order_id": f"bin_{kwargs.get('purpose', 'order')}_{kwargs.get('client_order_id', '1')}", "average": 60000.0, "status": "FILLED"})
    mock_binance.create_entry_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_entry_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_stop_loss_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_sl_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_take_profit_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_tp_{kwargs.get('client_order_id', '1')}"})
    mock_binance.cancel_order = AsyncMock(return_value=True)
    mock_binance.cancel_all_orders = AsyncMock(return_value=True)
    mock_binance.cancel_all_open_orders = AsyncMock(return_value=True)


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
        exchange_gateway=mock_binance,
    )

    position_manager = PositionManager(
        trade_repo=trade_repo,
        order_repo=order_repo,
        execution_repo=exec_repo,
        trade_event_repo=trade_event_repo,
        trade_summary_repo=trade_sum_repo,
        daily_risk_repo=daily_risk_repo,
        exchange_gateway=mock_binance,
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
        exchange_gateway=mock_binance,
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
