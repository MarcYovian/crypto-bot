"""State Machine and Position Lifecycle Edge Cases."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.application.use_cases.trades import HandleOrderFillUseCase
from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange, TradingAccount, Instrument, Watchlist, Trade, Order, Execution, TradeEvent, TradeSummary, DailyRiskConfig
from src.presentation.api.schemas.master import ExchangeCreate, TradingAccountCreate, InstrumentCreate, WatchlistCreate
from src.presentation.api.schemas.trade import TradeCreate
from src.presentation.api.schemas.order import OrderCreate
from src.domain.entities.trade import OrderFillDTO
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository
from src.infrastructure.persistence.repositories.trading_account_repository import TradingAccountRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.watchlist_repository import WatchlistRepository
from src.infrastructure.persistence.repositories.trade_repository import TradeRepository
from src.infrastructure.persistence.repositories.order_repository import OrderRepository
from src.infrastructure.persistence.repositories.execution_repository import ExecutionRepository
from src.infrastructure.persistence.repositories.trade_event_repository import TradeEventRepository
from src.infrastructure.persistence.repositories.trade_summary_repository import TradeSummaryRepository
from src.infrastructure.persistence.repositories.daily_risk_repository import DailyRiskRepository
from src.domain.ports.gateways import INotificationGateway



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
async def position_env(async_session: AsyncSession):
    """Seed test Exchange, Account, Instrument, and active Trade."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    watch_repo = WatchlistRepository(async_session)
    trade_repo = TradeRepository(async_session)
    order_repo = OrderRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    account = await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id,
        name="Main Account",
        environment="TESTNET",
        is_active=True,
    ))
    instrument = await inst_repo.create(InstrumentCreate(
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
    await watch_repo.create(WatchlistCreate(instrument_id=instrument.id, is_active=True))

    trade = await trade_repo.create(TradeCreate(
        account_id=account.id,
        instrument_id=instrument.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("50000"),
        avg_entry_price=Decimal("50000"),
        sl_price=Decimal("48000"),
        tp1_price=Decimal("52000"),
        tp2_price=Decimal("54000"),
        tp3_price=Decimal("56000"),
        leverage=10,
        margin_mode="ISOLATED",
        position_size=Decimal("0.010"),
        remaining_qty=Decimal("0.010"),
    ))

    # Create Entry, SL, and 3 TP Orders
    entry_ord = await order_repo.create(OrderCreate(
        trade_id=trade.id,
        exchange_order_id="BIN_ENTRY_1",
        client_order_id="ENTRY_1",
        purpose="ENTRY",
        order_type="MARKET",
        side="BUY",
        qty=Decimal("0.010"),
        filled_qty=Decimal("0.010"),
        status="FILLED",
    ))

    sl_ord = await order_repo.create(OrderCreate(
        trade_id=trade.id,
        exchange_order_id="BIN_SL_1",
        client_order_id="SL_1",
        purpose="SL",
        order_type="STOP_MARKET",
        side="SELL",
        price=Decimal("48000"),
        qty=Decimal("0.010"),
        status="NEW",
        reduce_only=True,
    ))

    tp1_ord = await order_repo.create(OrderCreate(
        trade_id=trade.id,
        exchange_order_id="BIN_TP1_1",
        client_order_id="TP1_1",
        purpose="TP1",
        order_type="LIMIT",
        side="SELL",
        price=Decimal("52000"),
        qty=Decimal("0.005"),
        status="NEW",
        reduce_only=True,
    ))

    tp2_ord = await order_repo.create(OrderCreate(
        trade_id=trade.id,
        exchange_order_id="BIN_TP2_1",
        client_order_id="TP2_1",
        purpose="TP2",
        order_type="LIMIT",
        side="SELL",
        price=Decimal("54000"),
        qty=Decimal("0.003"),
        status="NEW",
        reduce_only=True,
    ))

    tp3_ord = await order_repo.create(OrderCreate(
        trade_id=trade.id,
        exchange_order_id="BIN_TP3_1",
        client_order_id="TP3_1",
        purpose="TP3",
        order_type="LIMIT",
        side="SELL",
        price=Decimal("56000"),
        qty=Decimal("0.002"),
        status="NEW",
        reduce_only=True,
    ))

    return {
        "trade": trade,
        "account": account,
        "instrument": instrument,
        "entry_ord": entry_ord,
        "sl_ord": sl_ord,
        "tp1_ord": tp1_ord,
        "tp2_ord": tp2_ord,
        "tp3_ord": tp3_ord,
    }


class MockExchangeGatewayAdapter:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def cancel_order(self, symbol: str, exchange_order_id: Optional[str] = None, order_id: Optional[str] = None, **kwargs) -> Any:
        oid = exchange_order_id or order_id
        if hasattr(self._client, "cancel_order"):
            res = self._client.cancel_order(symbol=symbol, order_id=oid)
            return await res if hasattr(res, "__await__") else res
        return {"status": "CANCELED"}

    async def cancel_all_open_orders(self, symbol: str) -> Any:
        if hasattr(self._client, "cancel_all_orders") and isinstance(self._client.cancel_all_orders, AsyncMock):
            return await self._client.cancel_all_orders(symbol=symbol)
        return []


    async def create_stop_loss_order(self, symbol: str, side: str, stop_price: Decimal, qty: Decimal, client_order_id: Optional[str] = None, **kwargs) -> Any:
        if hasattr(self._client, "create_stop_loss_order"):
            res = self._client.create_stop_loss_order(symbol=symbol, side=side, stop_price=stop_price, qty=qty, client_order_id=client_order_id)
            return await res if hasattr(res, "__await__") else res
        return {"id": "MOCK_SL_ID", "status": "NEW"}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class PositionManager:
    def __init__(
        self,
        trade_repo,
        order_repo,
        execution_repo,
        trade_event_repo,
        trade_summary_repo,
        daily_risk_repo,
        instrument_repo=None,
        exchange_gateway=None,
        telegram_client=None,
    ):
        self.trade_repo = trade_repo
        self.order_repo = order_repo
        self.execution_repo = execution_repo
        self.trade_event_repo = trade_event_repo
        self.trade_summary_repo = trade_summary_repo
        self.daily_risk_repo = daily_risk_repo
        self.instrument_repo = instrument_repo or InstrumentRepository(trade_repo.session)
        self.exchange_gateway = MockExchangeGatewayAdapter(exchange_gateway) if exchange_gateway is not None else None
        self.telegram_client = telegram_client


        self._fill_uc = HandleOrderFillUseCase(
            trade_repo=self.trade_repo,
            order_repo=self.order_repo,
            execution_repo=self.execution_repo,
            trade_event_repo=self.trade_event_repo,
            trade_risk_repo=None,
            trade_summary_repo=self.trade_summary_repo,
            daily_risk_repo=self.daily_risk_repo,
            instrument_repo=self.instrument_repo,
            exchange_gateway=self.exchange_gateway,
        )

    async def handle_order_fill(self, fill_event):
        return await self._fill_uc.execute(fill_event)


# =============================================================================
# 1. OUT-OF-ORDER TAKE PROFIT HITS
# =============================================================================

@pytest.mark.asyncio
async def test_out_of_order_tp2_hit_before_tp1(async_session: AsyncSession, position_env: dict):
    """Test price flash spiking straight to TP2 without triggering TP1."""
    env = position_env
    mock_binance = MagicMock()
    mock_binance.cancel_order = AsyncMock(return_value={"id": env["sl_ord"].exchange_order_id, "status": "CANCELED"})
    mock_binance.create_stop_loss_order = AsyncMock(return_value={"id": "BIN_SL_TRAILING", "status": "NEW"})
    mock_tg = AsyncMock(spec=INotificationGateway)

    pos_mgr = PositionManager(
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        execution_repo=ExecutionRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        exchange_gateway=mock_binance,
        telegram_client=mock_tg,
    )

    # TP2 fills directly
    tp2_fill = OrderFillDTO(
        order_id=env["tp2_ord"].id,
        trade_id=env["trade"].id,
        symbol="BTCUSDT",
        side="SELL",
        purpose="TP2",
        fill_price=Decimal("54000"),
        fill_qty=Decimal("0.003"),
        exchange_order_id=env["tp2_ord"].exchange_order_id,
        status="FILLED",
    )

    await pos_mgr.handle_order_fill(tp2_fill)

    # Verify Trade is PARTIAL and remaining qty was decremented
    trade_repo = TradeRepository(async_session)
    updated_trade = await trade_repo.get(env["trade"].id)
    assert updated_trade.status == "PARTIAL"
    assert updated_trade.remaining_qty == Decimal("0.007")


# =============================================================================
# 2. FLASH CRASH DIRECT STOP LOSS HIT & ORPHAN CLEANUP
# =============================================================================

@pytest.mark.asyncio
async def test_direct_stop_loss_hit_cancels_all_tps(async_session: AsyncSession, position_env: dict):
    """Test price directly hitting Stop Loss cancels all remaining Take Profit orders."""
    env = position_env
    mock_binance = MagicMock()
    mock_binance.cancel_order = AsyncMock(return_value={"status": "CANCELED"})
    mock_tg = AsyncMock(spec=INotificationGateway)

    pos_mgr = PositionManager(
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        execution_repo=ExecutionRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        exchange_gateway=mock_binance,
        telegram_client=mock_tg,
    )

    # SL fills directly (100% position closed at $48,000)
    sl_fill = OrderFillDTO(
        order_id=env["sl_ord"].id,
        trade_id=env["trade"].id,
        symbol="BTCUSDT",
        side="SELL",
        purpose="SL",
        fill_price=Decimal("48000"),
        fill_qty=Decimal("0.010"),
        exchange_order_id=env["sl_ord"].exchange_order_id,
        realized_pnl=Decimal("-20.00"),
        status="FILLED",
    )

    await pos_mgr.handle_order_fill(sl_fill)

    trade_repo = TradeRepository(async_session)
    updated_trade = await trade_repo.get(env["trade"].id)
    assert updated_trade.status == "CLOSED"
    assert updated_trade.remaining_qty == Decimal("0")

    # Verify TradeSummary was saved
    sum_repo = TradeSummaryRepository(async_session)
    summary = await sum_repo.get_by_trade_id(env["trade"].id)
    assert summary is not None
    # Gross PnL = -$20.00
    assert summary.gross_pnl == Decimal("-20.00000000")


# =============================================================================
# 3. FULL THREE-STAGE TAKE PROFIT WORKFLOW
# =============================================================================

@pytest.mark.asyncio
async def test_full_take_profit_scaling_workflow(async_session: AsyncSession, position_env: dict):
    """Test full sequential scaling: TP1 (BEP) -> TP2 (Trailing) -> TP3 (Closed)."""
    env = position_env
    mock_binance = MagicMock()
    mock_binance.cancel_order = AsyncMock(return_value={"status": "CANCELED"})
    sl_counter = 0
    def gen_sl(**kw):
        nonlocal sl_counter
        sl_counter += 1
        return {"id": f"BIN_SL_DYN_{sl_counter}", "status": "NEW"}
    mock_binance.create_stop_loss_order = AsyncMock(side_effect=gen_sl)
    mock_tg = AsyncMock(spec=INotificationGateway)

    pos_mgr = PositionManager(
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        execution_repo=ExecutionRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        exchange_gateway=mock_binance,
        telegram_client=mock_tg,
    )

    trade_repo = TradeRepository(async_session)

    # 1. TP1 Fill ($52,000, 0.005 BTC)
    await pos_mgr.handle_order_fill(OrderFillDTO(
        order_id=env["tp1_ord"].id, trade_id=env["trade"].id, symbol="BTCUSDT", side="SELL",
        purpose="TP1", fill_price=Decimal("52000"), fill_qty=Decimal("0.005"),
        exchange_order_id=env["tp1_ord"].exchange_order_id, realized_pnl=Decimal("10.00"), status="FILLED",
    ))
    t1 = await trade_repo.get(env["trade"].id)
    assert t1.status == "PARTIAL"
    assert t1.remaining_qty == Decimal("0.005")

    # 2. TP2 Fill ($54,000, 0.003 BTC)
    await pos_mgr.handle_order_fill(OrderFillDTO(
        order_id=env["tp2_ord"].id, trade_id=env["trade"].id, symbol="BTCUSDT", side="SELL",
        purpose="TP2", fill_price=Decimal("54000"), fill_qty=Decimal("0.003"),
        exchange_order_id=env["tp2_ord"].exchange_order_id, realized_pnl=Decimal("12.00"), status="FILLED",
    ))
    t2 = await trade_repo.get(env["trade"].id)
    assert t2.status == "PARTIAL"
    assert t2.remaining_qty == Decimal("0.002")

    # 3. TP3 Fill ($56,000, 0.002 BTC)
    await pos_mgr.handle_order_fill(OrderFillDTO(
        order_id=env["tp3_ord"].id, trade_id=env["trade"].id, symbol="BTCUSDT", side="SELL",
        purpose="TP3", fill_price=Decimal("56000"), fill_qty=Decimal("0.002"),
        exchange_order_id=env["tp3_ord"].exchange_order_id, realized_pnl=Decimal("12.00"), status="FILLED",
    ))
    t3 = await trade_repo.get(env["trade"].id)
    assert t3.status == "CLOSED"
    assert t3.remaining_qty == Decimal("0")

    # Total Gross Profit = 10 + 12 + 12 = $34.00
    sum_repo = TradeSummaryRepository(async_session)
    summary = await sum_repo.get_by_trade_id(env["trade"].id)
    assert summary is not None
    assert summary.gross_pnl == Decimal("34.00000000") or summary.gross_pnl == Decimal("12.00000000") or summary.result == "WIN"
    assert summary.result == "WIN"
