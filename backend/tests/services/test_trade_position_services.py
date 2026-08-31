"""Comprehensive unit tests for TradeService and PositionManager."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange, TradingAccount, Instrument, Watchlist, Trade, Order, Execution, TradeEvent, TradeSummary, DailyRiskConfig
from src.presentation.api.schemas.master import ExchangeCreate, TradingAccountCreate, InstrumentCreate, WatchlistCreate, InstrumentLeverageBracketCreate
from src.presentation.api.schemas.trade import TradeCreate
from src.presentation.api.schemas.risk import DailyRiskConfigCreate
from src.presentation.api.schemas.order import OrderCreate
from src.domain.entities.signal import ParsedSignalDTO
from src.domain.entities.trade import OrderFillDTO
from src.domain.exceptions.trade import (
    TradeExecutionError,
    PairAlreadyActiveError,
    SymbolNotWhitelistedError,
)
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository
from src.infrastructure.persistence.repositories.trading_account_repository import TradingAccountRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.instrument_leverage_bracket_repository import InstrumentLeverageBracketRepository
from src.infrastructure.persistence.repositories.watchlist_repository import WatchlistRepository
from src.infrastructure.persistence.repositories.risk_profile_repository import RiskProfileRepository
from src.infrastructure.persistence.repositories.trade_repository import TradeRepository
from src.infrastructure.persistence.repositories.trade_risk_repository import TradeRiskRepository
from src.infrastructure.persistence.repositories.daily_risk_repository import DailyRiskRepository
from src.infrastructure.persistence.repositories.order_repository import OrderRepository
from src.infrastructure.persistence.repositories.execution_repository import ExecutionRepository
from src.infrastructure.persistence.repositories.trade_event_repository import TradeEventRepository
from src.infrastructure.persistence.repositories.trade_summary_repository import TradeSummaryRepository
from src.domain.services.risk_calculator import RiskCalculatorDomainService as RiskCalculatorService
from src.application.dto.trade_commands import ExecuteSignalCommand, CloseTradeCommand, UpdateStopLossCommand, SyncPositionsCommand
from src.application.use_cases.trades.execute_signal_use_case import ExecuteSignalUseCase
from src.application.use_cases.trades.close_trade_use_case import CloseTradeUseCase
from src.application.use_cases.trades.update_stop_loss_use_case import UpdateStopLossUseCase
from src.application.use_cases.trades.handle_order_fill_use_case import HandleOrderFillUseCase
from src.application.use_cases.trades.sync_positions_use_case import SyncPositionsUseCase


class MockExchangeGatewayAdapter:
    """Bridges legacy binance_client mock objects to Clean Architecture IExchangeGateway interface."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def fetch_balance(self) -> Dict[str, Any]:
        if hasattr(self._client, "fetch_balance"):
            res = self._client.fetch_balance()
            data = await res if hasattr(res, "__await__") else res
            if isinstance(data, dict):
                return data
        return {"free_margin": Decimal("10000.0"), "total_wallet_balance": Decimal("10000.0")}

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        if hasattr(self._client, "fetch_ticker_price"):
            res = self._client.fetch_ticker_price(symbol)
            p = await res if hasattr(res, "__await__") else res
            if p is not None and not isinstance(p, (AsyncMock, MagicMock)):
                return {"last": p, "last_price": p}
        if hasattr(self._client, "fetch_ticker"):
            res = self._client.fetch_ticker(symbol)
            data = await res if hasattr(res, "__await__") else res
            if isinstance(data, dict):
                return data
        return {"last": Decimal("60000.0"), "last_price": Decimal("60000.0")}

    async def set_leverage(self, symbol: str, leverage: int) -> Any:
        if hasattr(self._client, "set_leverage"):
            res = self._client.set_leverage(symbol, leverage)
            return await res if hasattr(res, "__await__") else res

    async def set_margin_mode(self, symbol: str, margin_mode: str) -> Any:
        if hasattr(self._client, "set_margin_mode"):
            res = self._client.set_margin_mode(symbol, margin_mode)
            return await res if hasattr(res, "__await__") else res


    async def create_order(
        self,
        symbol: str,
        side: Any,
        order_type: Any,
        qty: Decimal,
        price: Optional[Decimal] = None,
        client_order_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if hasattr(self._client, "create_order") and isinstance(self._client.create_order, AsyncMock):
            res = self._client.create_order(symbol=symbol, side=side, order_type=order_type, qty=qty, price=price, client_order_id=client_order_id, **kwargs)
            return await res if hasattr(res, "__await__") else res
        if hasattr(self._client, "create_entry_order") and isinstance(self._client.create_entry_order, (AsyncMock, MagicMock)):
            res = self._client.create_entry_order(symbol=symbol, side=str(side), order_type=str(order_type), qty=qty, price=price, client_order_id=client_order_id, **kwargs)
            ret = await res if hasattr(res, "__await__") else res

            if isinstance(ret, dict):
                ret.setdefault("status", "FILLED" if str(order_type).upper() == "MARKET" else "NEW")
                ret.setdefault("order_id", ret.get("id", "MOCK_ORDER_1"))
                ret.setdefault("exchange_order_id", ret.get("id", "MOCK_ORDER_1"))
                return ret
        return {
            "order_id": "MOCK_ORDER_1",
            "exchange_order_id": "MOCK_ORDER_1",
            "status": "FILLED" if str(order_type).upper() == "MARKET" else "NEW",
            "price": float(price or 0),
        }

    async def create_stop_loss_order(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        if hasattr(self._client, "create_stop_loss_order"):
            res = self._client.create_stop_loss_order(*args, **kwargs)
            ret = await res if hasattr(res, "__await__") else res
            if isinstance(ret, dict):
                ret.setdefault("id", "MOCK_SL_1")
                ret.setdefault("order_id", ret.get("id", "MOCK_SL_1"))
                return ret
        return {"id": "MOCK_SL_1", "order_id": "MOCK_SL_1", "status": "NEW"}

    async def create_take_profit_order(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        if hasattr(self._client, "create_take_profit_order"):
            res = self._client.create_take_profit_order(*args, **kwargs)
            ret = await res if hasattr(res, "__await__") else res
            if isinstance(ret, dict):
                ret.setdefault("id", "MOCK_TP_1")
                ret.setdefault("order_id", ret.get("id", "MOCK_TP_1"))
                return ret
        return {"id": "MOCK_TP_1", "order_id": "MOCK_TP_1", "status": "NEW"}

    async def cancel_order(self, symbol: str, order_id: str) -> Any:
        if hasattr(self._client, "cancel_order"):
            res = self._client.cancel_order(symbol=symbol, order_id=order_id)
            return await res if hasattr(res, "__await__") else res
        return {"status": "CANCELED"}

    async def cancel_all_orders(self, symbol: str) -> Any:
        if hasattr(self._client, "cancel_all_orders"):
            res = self._client.cancel_all_orders(symbol=symbol)
            return await res if hasattr(res, "__await__") else res
        return []

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 100) -> Any:
        if hasattr(self._client, "fetch_klines"):
            res = self._client.fetch_klines(symbol=symbol, interval=interval, limit=limit)
            return await res if hasattr(res, "__await__") else res
        return []

    async def has_price_reached_target(self, symbol: str, target_price: Decimal, *args: Any, **kwargs: Any) -> bool:
        if hasattr(self._client, "has_price_reached_target"):
            fn = getattr(self._client, "has_price_reached_target")
            if isinstance(fn, (AsyncMock, MagicMock)):
                try:
                    res = fn(symbol=symbol, target_price=target_price, *args, **kwargs) if not isinstance(fn, AsyncMock) else await fn(symbol=symbol, target_price=target_price, *args, **kwargs)
                    ret = await res if hasattr(res, "__await__") else res
                    if isinstance(ret, (AsyncMock, MagicMock)):
                        return False
                    return bool(ret)
                except Exception:
                    return False
        return False


    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)




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
        bracket_repo=None,
        exchange_gateway=None,
        risk_calculator=None,
        event_publisher=None,
        trade_summary_repo=None,
    ):
        self.instrument_repo = instrument_repo
        self.watchlist_repo = watchlist_repo
        self.trade_repo = trade_repo
        self.trade_risk_repo = trade_risk_repo
        self.daily_risk_repo = daily_risk_repo
        self.order_repo = order_repo
        self.trade_event_repo = trade_event_repo
        self.risk_profile_repo = risk_profile_repo
        if self.risk_profile_repo is None and hasattr(self.trade_repo, "session"):
            self.risk_profile_repo = RiskProfileRepository(self.trade_repo.session)
        self.bracket_repo = bracket_repo
        self.exchange_gateway = MockExchangeGatewayAdapter(exchange_gateway) if exchange_gateway is not None else None


        self.risk_calculator = risk_calculator
        self.event_publisher = event_publisher
        self.trade_summary_repo = trade_summary_repo
        if self.trade_summary_repo is None and hasattr(self.trade_repo, "session"):
            self.trade_summary_repo = TradeSummaryRepository(self.trade_repo.session)

        self._execute_uc = ExecuteSignalUseCase(
            instrument_repo=self.instrument_repo,
            watchlist_repo=self.watchlist_repo,
            trade_repo=self.trade_repo,
            trade_risk_repo=self.trade_risk_repo,
            daily_risk_repo=self.daily_risk_repo,
            order_repo=self.order_repo,
            trade_event_repo=self.trade_event_repo,
            risk_profile_repo=self.risk_profile_repo,
            bracket_repo=self.bracket_repo,
            exchange_gateway=self.exchange_gateway,
            risk_calculator=self.risk_calculator,
            event_publisher=self.event_publisher,
        )
        self._close_uc = CloseTradeUseCase(
            trade_repo=self.trade_repo,
            order_repo=self.order_repo,
            trade_event_repo=self.trade_event_repo,
            trade_summary_repo=self.trade_summary_repo,
            exchange_gateway=self.exchange_gateway,
            event_publisher=self.event_publisher,
        )
        self._update_sl_uc = UpdateStopLossUseCase(
            trade_repo=self.trade_repo,
            order_repo=self.order_repo,
            trade_event_repo=self.trade_event_repo,
            exchange_gateway=self.exchange_gateway,
            event_publisher=self.event_publisher,
        )

    async def execute_signal(self, signal: ParsedSignalDTO, account_id: int = 1, strategy_id: int = None, auto_tp_sl: bool = True):
        cmd = ExecuteSignalCommand(
            signal_dto=signal,
            account_id=account_id,
            strategy_id=strategy_id,
            auto_tp_sl=auto_tp_sl,
        )
        return await self._execute_uc.execute(cmd)

    async def close_trade_manually(self, trade_id: int, account_id: int = 1):
        cmd = CloseTradeCommand(trade_id=trade_id, reason="MANUAL_CLOSE", account_id=account_id)
        res = await self._close_uc.execute(cmd)
        if isinstance(res, dict) and res.get("status") == "CLOSED":
            return True
        return res


    async def close_trade(self, trade_id: int, reason: str = "MANUAL_CLOSE", account_id: int = 1):
        cmd = CloseTradeCommand(trade_id=trade_id, reason=reason, account_id=account_id)
        return await self._close_uc.execute(cmd)

    async def update_stop_loss(self, trade_id: int, new_sl_price: Decimal, reason: str = "MANUAL_ADJUST"):
        cmd = UpdateStopLossCommand(trade_id=trade_id, new_sl_price=new_sl_price, reason=reason)
        return await self._update_sl_uc.execute(cmd)


class PositionManager:
    def __init__(
        self,
        trade_repo=None,
        order_repo=None,
        execution_repo=None,
        trade_event_repo=None,
        trade_summary_repo=None,
        trade_risk_repo=None,
        daily_risk_repo=None,
        instrument_repo=None,
        exchange_gateway=None,
        event_publisher=None,
    ):
        self.trade_repo = trade_repo
        self.order_repo = order_repo
        self.execution_repo = execution_repo
        self.trade_event_repo = trade_event_repo
        self.trade_summary_repo = trade_summary_repo
        self.trade_risk_repo = trade_risk_repo
        self.instrument_repo = instrument_repo
        if self.instrument_repo is None and hasattr(self.trade_repo, "session"):
            self.instrument_repo = InstrumentRepository(self.trade_repo.session)
        if self.trade_risk_repo is None and hasattr(self.trade_repo, "session"):
            self.trade_risk_repo = TradeRiskRepository(self.trade_repo.session)
        self.daily_risk_repo = daily_risk_repo
        if self.daily_risk_repo is None and hasattr(self.trade_repo, "session"):
            self.daily_risk_repo = DailyRiskRepository(self.trade_repo.session)
        self.exchange_gateway = MockExchangeGatewayAdapter(exchange_gateway) if exchange_gateway is not None else None
        self.event_publisher = event_publisher






        self._fill_uc = HandleOrderFillUseCase(
            trade_repo=self.trade_repo,
            order_repo=self.order_repo,
            execution_repo=self.execution_repo,
            trade_event_repo=self.trade_event_repo,
            trade_risk_repo=self.trade_risk_repo,
            trade_summary_repo=self.trade_summary_repo,
            daily_risk_repo=self.daily_risk_repo,
            instrument_repo=self.instrument_repo,
            exchange_gateway=self.exchange_gateway,
            event_publisher=self.event_publisher,
        )
        self._sync_uc = SyncPositionsUseCase(
            trade_repo=self.trade_repo,
            instrument_repo=self.instrument_repo,
            exchange_gateway=self.exchange_gateway,
        )


    async def handle_order_fill(self, fill_event):
        return await self._fill_uc.execute(fill_event)

    async def sync_positions(self, account_id: int = 1):
        return await self._sync_uc.execute(SyncPositionsCommand(account_id=account_id))



TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_session():
    """Create a fresh in-memory SQLite database session for testing."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def setup_env(async_session: AsyncSession):
    """Seed test Exchange, Account, Instrument, and Watchlist."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    watch_repo = WatchlistRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    account = await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id,
        name="Main Account",
        environment="MAINNET",
        is_active=True,
    ))
    instrument = await inst_repo.create(InstrumentCreate(
        exchange_id=exchange.id,
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        tick_size=Decimal("0.10"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5.0"),
        price_precision=1,
        qty_precision=3,
        is_active=True,
    ))
    watchlist = await watch_repo.create(WatchlistCreate(
        account_id=account.id,
        instrument_id=instrument.id,
        is_enabled=True,
        max_leverage=20,
    ))

    return {
        "exchange": exchange,
        "account": account,
        "instrument": instrument,
        "watchlist": watchlist,
    }


@pytest.mark.asyncio
async def test_trade_service_execute_signal_full_success(async_session: AsyncSession, setup_env: dict):
    """Test full execution pipeline from ParsedSignalDTO to Trade and Order creation."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]

    # Mock Binance client
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.set_leverage = AsyncMock(return_value={"leverage": 20})
    mock_binance.set_margin_mode = AsyncMock(return_value={"margin_mode": "ISOLATED"})
    mock_binance.create_entry_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_entry_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_stop_loss_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_sl_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_take_profit_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_tp_{kwargs.get('client_order_id', '1')}"})

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        exchange_gateway=mock_binance,
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 62000, 64000, 66000",
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        entry_targets=[Decimal("60000")],
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("62000"), Decimal("64000"), Decimal("66000")],
        leverage=20,
    )

    res = await trade_service.execute_signal(signal, account_id=acc.id)

    assert res.is_success is True
    assert res.symbol == "BTCUSDT"
    assert res.position_size == Decimal("0.100")
    assert res.trade_id is not None

    # Verify orders in DB
    order_repo = OrderRepository(async_session)
    orders = await order_repo.get_orders_by_trade_id(res.trade_id)
    assert len(orders) == 5  # 1 Entry + 1 SL + 3 TPs

    purposes = {o.purpose for o in orders}
    assert "ENTRY" in purposes
    assert "SL" in purposes
    assert "TP1" in purposes
    assert "TP2" in purposes
    assert "TP3" in purposes


@pytest.mark.asyncio
async def test_trade_service_reject_unwhitelisted_symbol(async_session: AsyncSession, setup_env: dict):
    """Test rejecting signals for symbols not in active watchlist."""
    acc = setup_env["account"]

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
    )

    signal = ParsedSignalDTO(
        raw_text="BUY ETHUSDT Entry: 3000 SL: 2900 TP: 3200",
        symbol="ETHUSDT",  # Not seeded in setup
        side="BUY",
        entry_min=Decimal("3000"),
        entry_max=Decimal("3000"),
        sl_price=Decimal("2900"),
        tp_targets=[Decimal("3200")],
    )

    with pytest.raises(SymbolNotWhitelistedError):
        await trade_service.execute_signal(signal, account_id=acc.id)


@pytest.mark.asyncio
async def test_trade_service_reject_when_pair_already_active(async_session: AsyncSession, setup_env: dict):
    """Test preventing duplicate trades on the same symbol."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]

    trade_repo = TradeRepository(async_session)
    # Seed an open trade
    from src.presentation.api.schemas.trade import TradeCreate
    await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        sl_price=Decimal("58000"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1"),
    ))

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=trade_repo,
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 62000",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("62000")],
    )

    with pytest.raises(PairAlreadyActiveError):
        await trade_service.execute_signal(signal, account_id=acc.id)


@pytest.mark.asyncio
async def test_position_manager_handle_entry_fill_opens_trade(async_session: AsyncSession, setup_env: dict):
    """Test entry fill event updating trade status to OPEN."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)
    order_repo = OrderRepository(async_session)

    from src.presentation.api.schemas.trade import TradeCreate
    from src.presentation.api.schemas.order import OrderCreate

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="WAITING_ENTRY",
        sl_price=Decimal("58000"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1"),
    ))

    order = await order_repo.create(OrderCreate(
        trade_id=trade.id,
        side="BUY",
        order_type="LIMIT",
        purpose="ENTRY",
        price=Decimal("60000"),
        qty=Decimal("0.1"),
        status="NEW",
    ))

    pos_manager = PositionManager(
        trade_repo=trade_repo,
        order_repo=order_repo,
        execution_repo=ExecutionRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
    )

    fill_event = OrderFillDTO(
        order_id=order.id,
        trade_id=trade.id,
        symbol="BTCUSDT",
        side="BUY",
        purpose="ENTRY",
        fill_price=Decimal("60000.0"),
        fill_qty=Decimal("0.1"),
        fee=Decimal("1.50"),
    )

    await pos_manager.handle_order_fill(fill_event)

    updated_trade = await trade_repo.get(trade.id)
    assert updated_trade.status == "OPEN"
    assert updated_trade.entry_price == Decimal("60000.0")


@pytest.mark.asyncio
async def test_position_manager_handle_tp1_fill_moves_sl_to_bep(async_session: AsyncSession, setup_env: dict):
    """Test TP1 fill triggering Break-Even Protection (moving SL to entry price)."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)
    order_repo = OrderRepository(async_session)
    event_repo = TradeEventRepository(async_session)

    from src.presentation.api.schemas.trade import TradeCreate
    from src.presentation.api.schemas.order import OrderCreate

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.100"),
        remaining_qty=Decimal("0.100"),
    ))

    # Old SL order
    old_sl = await order_repo.create(OrderCreate(
        trade_id=trade.id,
        side="SELL",
        order_type="STOP_MARKET",
        purpose="SL",
        price=Decimal("58000.0"),
        qty=Decimal("0.100"),
        status="NEW",
    ))

    # TP1 order
    tp1_order = await order_repo.create(OrderCreate(
        trade_id=trade.id,
        side="SELL",
        order_type="LIMIT",
        purpose="TP1",
        price=Decimal("62000.0"),
        qty=Decimal("0.050"),
        status="NEW",
    ))

    pos_manager = PositionManager(
        trade_repo=trade_repo,
        order_repo=order_repo,
        execution_repo=ExecutionRepository(async_session),
        trade_event_repo=event_repo,
        trade_summary_repo=TradeSummaryRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
    )

    fill_tp1 = OrderFillDTO(
        order_id=tp1_order.id,
        trade_id=trade.id,
        symbol="BTCUSDT",
        side="SELL",
        purpose="TP1",
        fill_price=Decimal("62000.0"),
        fill_qty=Decimal("0.050"),
        fee=Decimal("0.75"),
        realized_pnl=Decimal("100.0"),
    )

    await pos_manager.handle_order_fill(fill_tp1)

    updated_trade = await trade_repo.get(trade.id)
    assert updated_trade.sl_price == Decimal("60000.0")  # SL moved to entry
    assert updated_trade.remaining_qty == Decimal("0.050")

    events = await event_repo.get_events_by_trade(trade.id)
    event_types = [e.event_type for e in events]
    assert "TP1_HIT" in event_types
    assert "SL_MOVED_TO_BEP" in event_types


@pytest.mark.asyncio
async def test_position_manager_handle_tp2_fill_updates_trailing_sl(async_session: AsyncSession, setup_env: dict):
    """Test TP2 fill moving SL to TP1 level (Trailing Stop)."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)
    order_repo = OrderRepository(async_session)
    event_repo = TradeEventRepository(async_session)

    from src.presentation.api.schemas.trade import TradeCreate
    from src.presentation.api.schemas.order import OrderCreate

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="PARTIAL",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("60000.0"),
        leverage=20,
        position_size=Decimal("0.100"),
        remaining_qty=Decimal("0.050"),
    ))

    # TP1 order
    await order_repo.create(OrderCreate(
        trade_id=trade.id,
        side="SELL",
        order_type="LIMIT",
        purpose="TP1",
        price=Decimal("62000.0"),
        qty=Decimal("0.050"),
        status="FILLED",
    ))

    # TP2 order
    tp2_order = await order_repo.create(OrderCreate(
        trade_id=trade.id,
        side="SELL",
        order_type="LIMIT",
        purpose="TP2",
        price=Decimal("64000.0"),
        qty=Decimal("0.030"),
        status="NEW",
    ))

    pos_manager = PositionManager(
        trade_repo=trade_repo,
        order_repo=order_repo,
        execution_repo=ExecutionRepository(async_session),
        trade_event_repo=event_repo,
        trade_summary_repo=TradeSummaryRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
    )

    fill_tp2 = OrderFillDTO(
        order_id=tp2_order.id,
        trade_id=trade.id,
        symbol="BTCUSDT",
        side="SELL",
        purpose="TP2",
        fill_price=Decimal("64000.0"),
        fill_qty=Decimal("0.030"),
        fee=Decimal("0.50"),
        realized_pnl=Decimal("120.0"),
    )

    await pos_manager.handle_order_fill(fill_tp2)

    updated_trade = await trade_repo.get(trade.id)
    assert updated_trade.sl_price == Decimal("62000.0")  # SL moved to TP1
    assert updated_trade.remaining_qty == Decimal("0.020")


@pytest.mark.asyncio
async def test_position_manager_handle_sl_fill_finalizes_summary_loss(async_session: AsyncSession, setup_env: dict):
    """Test SL fill finalizing trade, generating TradeSummary with LOSS, and closing trade."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)
    order_repo = OrderRepository(async_session)
    exec_repo = ExecutionRepository(async_session)
    sum_repo = TradeSummaryRepository(async_session)

    from src.presentation.api.schemas.trade import TradeCreate
    from src.presentation.api.schemas.order import OrderCreate

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        initial_risk_usdt=Decimal("200.0"),
        position_size=Decimal("0.100"),
        remaining_qty=Decimal("0.100"),
        leverage=20,
    ))

    sl_order = await order_repo.create(OrderCreate(
        trade_id=trade.id,
        side="SELL",
        order_type="STOP_MARKET",
        purpose="SL",
        price=Decimal("58000.0"),
        qty=Decimal("0.100"),
        status="NEW",
    ))

    pos_manager = PositionManager(
        trade_repo=trade_repo,
        order_repo=order_repo,
        execution_repo=exec_repo,
        trade_event_repo=TradeEventRepository(async_session),
        trade_summary_repo=sum_repo,
        daily_risk_repo=DailyRiskRepository(async_session),
    )

    fill_sl = OrderFillDTO(
        order_id=sl_order.id,
        trade_id=trade.id,
        symbol="BTCUSDT",
        side="SELL",
        purpose="SL",
        fill_price=Decimal("58000.0"),
        fill_qty=Decimal("0.100"),
        fee=Decimal("2.0"),
        realized_pnl=Decimal("-200.0"),
    )

    await pos_manager.handle_order_fill(fill_sl)

    updated_trade = await trade_repo.get(trade.id)
    assert updated_trade.status == "CLOSED"

    summary = await sum_repo.get_by_trade_id(trade.id)
    assert summary is not None
    assert summary.result == "LOSS"
    assert summary.net_pnl == Decimal("-202.0")  # -200 PnL - 2 fee
    assert summary.close_reason == "SL_HIT"


@pytest.mark.asyncio
async def test_trade_service_close_trade_manually(async_session: AsyncSession, setup_env: dict):
    """Test manual closure of active trade via TradeService."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)

    from src.presentation.api.schemas.trade import TradeCreate
    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.100"),
        remaining_qty=Decimal("0.100"),
    ))

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=trade_repo,
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
    )

    closed = await trade_service.close_trade_manually(trade.id)
    assert closed is True

    updated_trade = await trade_repo.get(trade.id)
    assert updated_trade.status == "CLOSED"


@pytest.mark.asyncio
async def test_trade_service_dynamic_leverage_execution(async_session: AsyncSession, setup_env: dict):
    """Test trade execution end-to-end with dynamic leverage downscaling and bracket lookup."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]

    # Seed leverage brackets for BTCUSDT (Tier 1: Max 50x, Tier 2: Max 20x)
    bracket_repo = InstrumentLeverageBracketRepository(async_session)
    await bracket_repo.bulk_upsert_brackets(
        inst.id,
        [
            InstrumentLeverageBracketCreate(
                instrument_id=inst.id,
                bracket=1,
                initial_leverage=50,
                notional_floor=Decimal("0"),
                notional_cap=Decimal("50000"),
                maint_margin_ratio=Decimal("0.01"),
                cum=Decimal("0"),
            ),
            InstrumentLeverageBracketCreate(
                instrument_id=inst.id,
                bracket=2,
                initial_leverage=20,
                notional_floor=Decimal("50000"),
                notional_cap=Decimal("250000"),
                maint_margin_ratio=Decimal("0.025"),
                cum=Decimal("500"),
            ),
        ],
    )

    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.set_leverage = AsyncMock(return_value={"leverage": 18})
    mock_binance.set_margin_mode = AsyncMock(return_value={"margin_mode": "ISOLATED"})
    mock_binance.create_entry_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_entry_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_stop_loss_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_sl_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_take_profit_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_tp_{kwargs.get('client_order_id', '1')}"})

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        bracket_repo=bracket_repo,
        exchange_gateway=mock_binance,
    )

    # Signal asks for 75x leverage with SL 5% away (Entry 60000, SL 57000)
    # SL distance = 5%, MMR = 1% -> Total buffer = 6% -> Max Safe Leverage = 1 / 0.06 = 16x
    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 57000 TP: 63000",
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        entry_targets=[Decimal("60000")],
        sl_price=Decimal("57000"),
        tp_targets=[Decimal("63000")],
        leverage=75,
    )

    res = await trade_service.execute_signal(signal, account_id=acc.id)

    assert res.is_success is True
    assert res.symbol == "BTCUSDT"

    # Check trade recorded in DB with effective downscaled leverage (16x, NOT 75x)
    trade_repo = TradeRepository(async_session)
    saved_trade = await trade_repo.get(res.trade_id)
    assert saved_trade is not None
    assert saved_trade.leverage == 16

    # Verify Binance set_leverage was called with 16
    mock_binance.set_leverage.assert_called_with("BTCUSDT", 16)


@pytest.mark.asyncio
async def test_execute_signal_auto_provisions_default_profile_and_daily_snapshot(
    async_session: AsyncSession, setup_env: dict
):
    """Test that execute_signal auto-provisions DEFAULT RiskProfile and today's DailyRiskConfig if absent."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]

    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.set_leverage = AsyncMock(return_value={"leverage": 20})
    mock_binance.set_margin_mode = AsyncMock(return_value={"margin_mode": "ISOLATED"})
    mock_binance.create_entry_order = AsyncMock(return_value={"id": "bin_entry_1", "average": 60000.0})
    mock_binance.create_stop_loss_order = AsyncMock(return_value={"id": "bin_sl_1"})
    mock_binance.create_take_profit_order = AsyncMock(return_value={"id": "bin_tp_1"})

    rp_repo = RiskProfileRepository(async_session)
    daily_repo = DailyRiskRepository(async_session)
    trade_risk_repo = TradeRiskRepository(async_session)

    # Ensure no active risk profile or daily risk exists initially
    assert await rp_repo.get_active_profile() is None

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=trade_risk_repo,
        daily_risk_repo=daily_repo,
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        risk_profile_repo=rp_repo,
        exchange_gateway=mock_binance,
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 62000",
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("62000")],
        leverage=20,
    )

    res = await trade_service.execute_signal(signal, account_id=acc.id)
    assert res.is_success is True

    # 1. Verify that DEFAULT profile was automatically provisioned
    active_profile = await rp_repo.get_active_profile()
    assert active_profile is not None
    assert active_profile.name == "DEFAULT"
    assert active_profile.risk_percent == Decimal("2.0")
    assert active_profile.max_open_trade == 3

    # 2. Verify that today's DailyRiskConfig was automatically provisioned
    from datetime import datetime
    today = datetime.now().date()
    today_snapshot = await daily_repo.get_by_date(acc.id, today)
    assert today_snapshot is not None
    assert today_snapshot.balance == Decimal("10000.0")
    assert today_snapshot.risk_amount == Decimal("200.0")  # 2% of $10,000

    # 3. Verify that TradeRisk is linked to today's snapshot
    trade_risks = await trade_risk_repo.get_trade_risks_by_daily_config(today_snapshot.id)
    assert len(trade_risks) == 1
    assert trade_risks[0].trade_id == res.trade_id
    assert trade_risks[0].risk_amount == Decimal("200.0")


@pytest.mark.asyncio
async def test_execute_signal_uses_custom_risk_profile_risk_percent(
    async_session: AsyncSession, setup_env: dict
):
    """Test that execute_signal respects custom risk_percent (e.g. 1.0%) for position sizing."""
    acc = setup_env["account"]

    rp_repo = RiskProfileRepository(async_session)
    from src.presentation.api.schemas.master import RiskProfileCreate
    custom_profile = await rp_repo.create(
        RiskProfileCreate(
            name="CONSERVATIVE_1PCT",
            risk_percent=Decimal("1.0"),
            max_daily_loss=Decimal("3.0"),
            max_open_trade=2,
            is_active=True,
        )
    )

    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.set_leverage = AsyncMock(return_value={"leverage": 20})
    mock_binance.set_margin_mode = AsyncMock(return_value={"margin_mode": "ISOLATED"})
    mock_binance.create_entry_order = AsyncMock(return_value={"id": "bin_entry_2", "average": 60000.0})
    mock_binance.create_stop_loss_order = AsyncMock(return_value={"id": "bin_sl_2"})
    mock_binance.create_take_profit_order = AsyncMock(return_value={"id": "bin_tp_2"})

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        risk_profile_repo=rp_repo,
        exchange_gateway=mock_binance,
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 62000",
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("62000")],
        leverage=20,
    )

    # 1% of $10,000 = $100 risk. Stop distance = 2000. Sizing = 100 / 2000 = 0.05 BTC
    res = await trade_service.execute_signal(signal, account_id=acc.id)
    assert res.is_success is True
    assert res.position_size == Decimal("0.050")


@pytest.mark.asyncio
async def test_execute_signal_enforces_risk_profile_max_open_trade(
    async_session: AsyncSession, setup_env: dict
):
    """Test that execute_signal raises MaxRiskExceededError when open trade limit is reached."""
    from src.domain.exceptions.risk import MaxRiskExceededError
    from src.presentation.api.schemas.trade import TradeCreate

    acc = setup_env["account"]
    inst = setup_env["instrument"]
    ex = setup_env["exchange"]

    # 1. Create a second instrument so we can have 2 active trades on different pairs
    inst_repo = InstrumentRepository(async_session)
    watch_repo = WatchlistRepository(async_session)
    inst2 = await inst_repo.create(
        InstrumentCreate(
            exchange_id=ex.id,
            symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.01"),
            min_qty=Decimal("0.01"),
            min_notional=Decimal("5.0"),
            price_precision=2,
            qty_precision=2,
            is_active=True,
        )
    )
    await watch_repo.create(WatchlistCreate(instrument_id=inst2.id, symbol="ETHUSDT", is_enabled=True, note="Test"))

    # 2. Create RiskProfile with max_open_trade = 1
    rp_repo = RiskProfileRepository(async_session)
    from src.presentation.api.schemas.master import RiskProfileCreate
    profile = await rp_repo.create(
        RiskProfileCreate(
            name="SINGLE_TRADE_ONLY",
            risk_percent=Decimal("2.0"),
            max_daily_loss=Decimal("5.0"),
            max_open_trade=1,
            is_active=True,
        )
    )

    trade_repo = TradeRepository(async_session)
    # Seed 1 active trade on BTCUSDT
    await trade_repo.create(
        TradeCreate(
            account_id=acc.id,
            instrument_id=inst.id,
            side="BUY",
            status="OPEN",
            entry_price=Decimal("60000"),
            sl_price=Decimal("58000"),
            position_size=Decimal("0.1"),
            remaining_qty=Decimal("0.1"),
            leverage=20,
        )
    )

    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})

    trade_service = TradeService(
        instrument_repo=inst_repo,
        watchlist_repo=watch_repo,
        trade_repo=trade_repo,
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        risk_profile_repo=rp_repo,
        exchange_gateway=mock_binance,
    )

    # 3. Attempting to execute a new trade on ETHUSDT must fail with MaxRiskExceededError
    signal2 = ParsedSignalDTO(
        raw_text="BUY ETHUSDT Entry: 3000 SL: 2900 TP: 3200",
        symbol="ETHUSDT",
        side="BUY",
        order_type="MARKET",
        entry_min=Decimal("3000"),
        entry_max=Decimal("3000"),
        sl_price=Decimal("2900"),
        tp_targets=[Decimal("3200")],
        leverage=20,
    )

    with pytest.raises(MaxRiskExceededError) as exc_info:
        await trade_service.execute_signal(signal2, account_id=acc.id)

    assert "Batas maksimum open trade" in str(exc_info.value) or "Maximum open positions" in str(exc_info.value)


@pytest.mark.asyncio
async def test_execute_signal_dual_mode_market_within_tolerance(async_session: AsyncSession, setup_env: dict):
    """Test Dual-Mode choosing MARKET when unfavorable deviation is <= 0.2%."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]

    # Target: 60,000. Live price: 60,090 (+0.15% <= 0.2%)
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("60090.0"))
    mock_binance.set_leverage = AsyncMock(return_value={"leverage": 20})
    mock_binance.set_margin_mode = AsyncMock(return_value={"margin_mode": "ISOLATED"})
    mock_binance.create_entry_order = AsyncMock(return_value={"id": "bin_entry_market", "average": 60090.0})
    mock_binance.create_stop_loss_order = AsyncMock(return_value={"id": "bin_sl_1"})
    mock_binance.create_take_profit_order = AsyncMock(return_value={"id": "bin_tp_1"})

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        exchange_gateway=mock_binance,
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 63000",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("63000")],
        leverage=20,
    )

    res = await trade_service.execute_signal(signal, account_id=acc.id)

    assert res.is_success is True
    assert res.status == "OPEN"
    assert res.entry_price == Decimal("60090.0")
    # Verify create_entry_order was called with MARKET
    mock_binance.create_entry_order.assert_called_once()
    assert mock_binance.create_entry_order.call_args.kwargs["order_type"] == "MARKET"


@pytest.mark.asyncio
async def test_execute_signal_dual_mode_market_favorable_price(async_session: AsyncSession, setup_env: dict):
    """Test Dual-Mode choosing MARKET when live price is cheaper than BUY entry."""
    acc = setup_env["account"]

    # Target: 60,000. Live price: 59,800 (-0.33% -> favorable discount)
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("59800.0"))
    mock_binance.set_leverage = AsyncMock(return_value={"leverage": 20})
    mock_binance.set_margin_mode = AsyncMock(return_value={"margin_mode": "ISOLATED"})
    mock_binance.create_entry_order = AsyncMock(return_value={"id": "bin_entry_disc", "average": 59800.0})
    mock_binance.create_stop_loss_order = AsyncMock(return_value={"id": "bin_sl_disc"})
    mock_binance.create_take_profit_order = AsyncMock(return_value={"id": "bin_tp_disc"})

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        exchange_gateway=mock_binance,
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 63000",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("63000")],
        leverage=20,
    )

    res = await trade_service.execute_signal(signal, account_id=acc.id)

    assert res.is_success is True
    assert res.status == "OPEN"
    assert res.entry_price == Decimal("59800.0")
    assert mock_binance.create_entry_order.call_args.kwargs["order_type"] == "MARKET"


@pytest.mark.asyncio
async def test_execute_signal_dual_mode_limit_pullback(async_session: AsyncSession, setup_env: dict):
    """Test Dual-Mode placing LIMIT order when deviation is 0.8% (> 0.2% and <= 2.0%)."""
    acc = setup_env["account"]

    # Target: 60,000. Live price: 60,480 (+0.80% > 0.2%)
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("60480.0"))
    mock_binance.set_leverage = AsyncMock(return_value={"leverage": 20})
    mock_binance.set_margin_mode = AsyncMock(return_value={"margin_mode": "ISOLATED"})
    mock_binance.create_entry_order = AsyncMock(return_value={"id": "bin_limit_order", "status": "NEW"})
    mock_binance.create_stop_loss_order = AsyncMock()
    mock_binance.create_take_profit_order = AsyncMock()

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        exchange_gateway=mock_binance,
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 63000",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("63000")],
        leverage=20,
    )

    res = await trade_service.execute_signal(signal, account_id=acc.id)

    assert res.is_success is True
    assert res.status == "WAITING_ENTRY"
    assert res.entry_price == Decimal("60000")
    # Verify LIMIT order parameters
    mock_binance.create_entry_order.assert_called_once()
    assert mock_binance.create_entry_order.call_args.kwargs["order_type"] == "LIMIT"
    assert mock_binance.create_entry_order.call_args.kwargs["price"] == Decimal("60000")

    # Verify SL and TP were NOT submitted yet on Binance (waiting for fill)
    mock_binance.create_stop_loss_order.assert_not_called()
    mock_binance.create_take_profit_order.assert_not_called()


@pytest.mark.asyncio
async def test_execute_signal_dual_mode_reject_runaway(async_session: AsyncSession, setup_env: dict):
    """Test Dual-Mode rejecting signal when price has run away (> 2.0%)."""
    acc = setup_env["account"]

    # Target: 60,000. Live price: 62,500 (+4.16% > 2.0%)
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("62500.0"))

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        exchange_gateway=mock_binance,
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 63000",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("63000")],
        leverage=20,
    )

    res = await trade_service.execute_signal(signal, account_id=acc.id)

    assert res.is_success is False
    assert res.status == "REJECTED"
    assert "Price has run away" in res.message


@pytest.mark.asyncio
async def test_position_manager_limit_entry_fill_places_bracket_orders(async_session: AsyncSession, setup_env: dict):
    """Test PositionManager reactively placing SL and TPs when an existing LIMIT entry order fills."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)
    order_repo = OrderRepository(async_session)
    daily_risk_repo = DailyRiskRepository(async_session)

    # 1. Create a RiskProfile and DailyRiskConfig
    from src.infrastructure.persistence.repositories.risk_profile_repository import RiskProfileRepository
    from src.presentation.api.schemas.master import RiskProfileCreate
    from src.presentation.api.schemas.risk import DailyRiskConfigCreate
    rp_repo = RiskProfileRepository(async_session)
    prof = await rp_repo.create(RiskProfileCreate(
        account_id=acc.id,
        name="DEFAULT",
        risk_percent=Decimal("2.0"),
        max_open_positions=3,
        max_daily_loss_pct=Decimal("5.0"),
        is_active=True,
    ))

    await daily_risk_repo.create(DailyRiskConfigCreate(
        account_id=acc.id,
        risk_profile_id=prof.id,
        date=datetime.now().date(),
        balance=Decimal("10000.0"),
        risk_amount=Decimal("200.0"),
    ))

    # 2. Seed a WAITING_ENTRY Trade from a LIMIT order
    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="WAITING_ENTRY",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        tp1_price=Decimal("63000.0"),
        tp2_price=Decimal("66000.0"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1"),
    ))

    entry_order = await order_repo.create(OrderCreate(
        trade_id=trade.id,
        side="BUY",
        order_type="LIMIT",
        purpose="ENTRY",
        price=Decimal("60000.0"),
        qty=Decimal("0.1"),
        status="NEW",
    ))

    # 3. Mock Binance client to verify reactive bracket placement
    mock_binance = MagicMock()
    mock_binance.create_stop_loss_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_sl_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_take_profit_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_tp_{kwargs.get('client_order_id', '1')}"})

    pos_manager = PositionManager(
        trade_repo=trade_repo,
        order_repo=order_repo,
        execution_repo=ExecutionRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        daily_risk_repo=daily_risk_repo,
        exchange_gateway=mock_binance,
    )

    fill_event = OrderFillDTO(
        order_id=entry_order.id,
        trade_id=trade.id,
        symbol="BTCUSDT",
        side="BUY",
        purpose="ENTRY",
        fill_price=Decimal("60000.0"),
        fill_qty=Decimal("0.1"),
        fee=Decimal("1.20"),
    )

    await pos_manager.handle_order_fill(fill_event)

    # 4. Verify Trade transitioned to OPEN
    updated_trade = await trade_repo.get(trade.id)
    assert updated_trade.status == "OPEN"
    assert updated_trade.entry_price == Decimal("60000.0")

    # 5. Verify SL and TPs were called on Binance
    mock_binance.create_stop_loss_order.assert_called_once()
    assert mock_binance.create_take_profit_order.call_count == 2  # TP1 and TP2

    # 6. Verify orders saved in DB
    orders = await order_repo.get_orders_by_trade_id(trade.id)
    purposes = {o.purpose for o in orders}
    assert "ENTRY" in purposes
    assert "SL" in purposes
    assert "TP1" in purposes
    assert "TP2" in purposes


@pytest.mark.asyncio
async def test_trade_service_sl_failsafe_emergency_close(async_session: AsyncSession, setup_env: dict):
    """Test that if SL placement fails 3 times on an opened position, Emergency Panic Close is triggered."""
    acc = setup_env["account"]

    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("60000.0"))
    mock_binance.set_leverage = AsyncMock(return_value={"leverage": 20})
    mock_binance.set_margin_mode = AsyncMock(return_value={"margin_mode": "ISOLATED"})
    mock_binance.create_entry_order = AsyncMock(side_effect=[
        {"id": "bin_entry_filled", "average": 60000.0},  # First call: Entry order
        {"id": "bin_panic_close", "average": 59990.0},   # Second call: Emergency Close
    ])
    # SL order fails persistently
    mock_binance.create_stop_loss_order = AsyncMock(side_effect=Exception("Binance 503 Service Unavailable"))

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        exchange_gateway=mock_binance,
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 63000",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("63000")],
        leverage=20,
    )

    with pytest.raises(TradeExecutionError) as exc_info:
        await trade_service.execute_signal(signal, account_id=acc.id)

    assert "Position was emergency-closed" in str(exc_info.value)
    # Verify emergency close order was submitted
    assert mock_binance.create_entry_order.call_count == 2
    assert mock_binance.create_entry_order.call_args_list[1].kwargs["reduce_only"] is True


@pytest.mark.asyncio
async def test_execute_signal_reject_if_current_price_above_tp1(async_session: AsyncSession, setup_env: dict):
    """Skenario 1 (BUY): Reject signal if current market price is already at or above TP1."""
    acc = setup_env["account"]

    # Signal: Entry 60,000, SL 58,000, TP1 62,000.
    # Current Live Price: 62,100 (>= TP1 62,000)
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("62100.0"))

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        exchange_gateway=mock_binance,
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 62000",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("62000")],
        leverage=20,
    )

    res = await trade_service.execute_signal(signal, account_id=acc.id)

    assert res.is_success is False
    assert res.status == "REJECTED"
    assert "sudah melewati target TP1" in res.message or "62000" in res.message


@pytest.mark.asyncio
async def test_execute_signal_reject_if_current_price_below_tp1_for_sell(async_session: AsyncSession, setup_env: dict):
    """Skenario 1 (SELL): Reject signal if current market price is already at or below TP1."""
    acc = setup_env["account"]

    # Signal: Entry 60,000, SL 62,000, TP1 58,000.
    # Current Live Price: 57,900 (<= TP1 58,000)
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("57900.0"))

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        exchange_gateway=mock_binance,
    )

    signal = ParsedSignalDTO(
        raw_text="SELL BTCUSDT Entry: 60000 SL: 62000 TP: 58000",
        symbol="BTCUSDT",
        side="SELL",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        sl_price=Decimal("62000"),
        tp_targets=[Decimal("58000")],
        leverage=20,
    )

    res = await trade_service.execute_signal(signal, account_id=acc.id)

    assert res.is_success is False
    assert res.status == "REJECTED"
    assert "sudah melewati target TP1" in res.message or "58000" in res.message


@pytest.mark.asyncio
async def test_execute_signal_reject_if_historical_kline_touched_tp1(async_session: AsyncSession, setup_env: dict):
    """Skenario 2: Reject signal if live price pulled back to entry zone, but historical kline already hit TP1."""
    acc = setup_env["account"]

    # Signal: Entry 60,000, SL 58,000, TP1 62,000.
    # Current Live Price: 60,050 (+0.08% deviation, looks valid for MARKET entry)
    # BUT price previously surged to 62,100 in klines
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("60050.0"))
    mock_binance.has_price_reached_target = AsyncMock(return_value=True)

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        exchange_gateway=mock_binance,
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 62000",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("62000")],
        leverage=20,
    )

    res = await trade_service.execute_signal(signal, account_id=acc.id)

    assert res.is_success is False
    assert res.status == "REJECTED"
    assert "pernah menyentuh target TP1" in res.message or "62000" in res.message
    mock_binance.has_price_reached_target.assert_called_once()


@pytest.mark.asyncio
async def test_binance_client_has_price_reached_target_logic():
    """Verify BinanceExchangeAdapter.has_price_reached_target with mocked fetch_ohlcv data."""
    from src.infrastructure.gateways.binance import BinanceConnector, BinanceExchangeAdapter

    connector = BinanceConnector()
    adapter = BinanceExchangeAdapter(connector=connector)
    # Mock CCXT fetch_ohlcv returning 3 candles: [timestamp, open, high, low, close, volume]
    mock_candles = [
        [1700000000000, 59900.0, 60100.0, 59800.0, 60000.0, 10.0],
        [1700000060000, 60000.0, 62150.0, 59950.0, 61500.0, 25.0],  # High reached 62,150 >= 62,000
        [1700000120000, 61500.0, 61600.0, 60020.0, 60050.0, 15.0],  # Pulled back to 60,050
    ]
    connector.execute_rest = AsyncMock(return_value=mock_candles)

    # 1. BUY TP test: Target 62,000 should return True (high reached 62,150 >= 62,000)
    hit_buy_tp = await adapter.has_price_reached_target(
        symbol="BTC/USDT",
        target_price=Decimal("62000.0"),
        side="BUY",
        is_sl=False,
    )
    assert hit_buy_tp is True

    # 2. BUY TP test: Target 63,000 should return False (max high was 62,150)
    miss_buy_tp = await adapter.has_price_reached_target(
        symbol="BTC/USDT",
        target_price=Decimal("63000.0"),
        side="BUY",
        is_sl=False,
    )
    assert miss_buy_tp is False

    # 3. BUY SL test: SL 59,850 should return True (min low reached 59,800 <= 59,850)
    hit_buy_sl = await adapter.has_price_reached_target(
        symbol="BTC/USDT",
        target_price=Decimal("59850.0"),
        side="BUY",
        is_sl=True,
    )
    assert hit_buy_sl is True

    # 4. BUY SL test: SL 59,500 should return False (min low was 59,800 > 59,500)
    miss_buy_sl = await adapter.has_price_reached_target(
        symbol="BTC/USDT",
        target_price=Decimal("59500.0"),
        side="BUY",
        is_sl=True,
    )
    assert miss_buy_sl is False

    # 5. SELL TP test: Target 59,850 should return True (low reached 59,800 <= 59,850)
    hit_sell_tp = await adapter.has_price_reached_target(
        symbol="BTC/USDT",
        target_price=Decimal("59850.0"),
        side="SELL",
        is_sl=False,
    )
    assert hit_sell_tp is True

    # 6. SELL TP test: Target 59,500 should return False (min low was 59,800)
    miss_sell_tp = await adapter.has_price_reached_target(
        symbol="BTC/USDT",
        target_price=Decimal("59500.0"),
        side="SELL",
        is_sl=False,
    )
    assert miss_sell_tp is False

    # 7. SELL SL test: SL 62,000 should return True (max high reached 62,150 >= 62,000)
    hit_sell_sl = await adapter.has_price_reached_target(
        symbol="BTC/USDT",
        target_price=Decimal("62000.0"),
        side="SELL",
        is_sl=True,
    )
    assert hit_sell_sl is True

    # 8. SELL SL test: SL 63,000 should return False (max high was 62,150 < 63,000)
    miss_sell_sl = await adapter.has_price_reached_target(
        symbol="BTC/USDT",
        target_price=Decimal("63000.0"),
        side="SELL",
        is_sl=True,
    )
    assert miss_sell_sl is False

    await adapter.close()



@pytest.mark.asyncio
async def test_execute_signal_reject_if_current_price_breached_sl_buy(async_session: AsyncSession, setup_env: dict):
    """Reject BUY signal if current market price has fallen below Stop Loss."""
    acc = setup_env["account"]

    # BUY Signal: Entry 60,000, SL 58,000, TP1 62,000.
    # Current Live Price: 57,800 (<= SL 58,000)
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("57800.0"))

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        exchange_gateway=mock_binance,
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 62000",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("62000")],
        leverage=20,
    )

    res = await trade_service.execute_signal(signal, account_id=acc.id)

    assert res.is_success is False
    assert res.status == "REJECTED"
    assert "sudah menembus Stop Loss" in res.message or "58000" in res.message


@pytest.mark.asyncio
async def test_execute_signal_reject_if_current_price_breached_sl_sell(async_session: AsyncSession, setup_env: dict):
    """Reject SELL signal if current market price has risen above Stop Loss."""
    acc = setup_env["account"]

    # SELL Signal: Entry 60,000, SL 62,000, TP1 58,000.
    # Current Live Price: 62,300 (>= SL 62,000)
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("62300.0"))

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        exchange_gateway=mock_binance,
    )

    signal = ParsedSignalDTO(
        raw_text="SELL BTCUSDT Entry: 60000 SL: 62000 TP: 58000",
        symbol="BTCUSDT",
        side="SELL",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        sl_price=Decimal("62000"),
        tp_targets=[Decimal("58000")],
        leverage=20,
    )

    res = await trade_service.execute_signal(signal, account_id=acc.id)

    assert res.is_success is False
    assert res.status == "REJECTED"
    assert "sudah menembus Stop Loss" in res.message or "62000" in res.message


@pytest.mark.asyncio
async def test_execute_signal_reject_if_historical_kline_breached_sl(async_session: AsyncSession, setup_env: dict):
    """Reject signal if live price pulled back to entry zone, but historical kline breached SL."""
    acc = setup_env["account"]

    # BUY Signal: Entry 60,000, SL 58,000, TP1 62,000.
    # Current Live Price: 60,020 (looks valid for entry), but SL was touched in klines
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("60020.0"))
    # Mock has_price_reached_target: False for TP1 check, True for SL check
    mock_binance.has_price_reached_target = AsyncMock(side_effect=[False, True])

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        exchange_gateway=mock_binance,
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 62000",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("62000")],
        leverage=20,
    )

    res = await trade_service.execute_signal(signal, account_id=acc.id)

    assert res.is_success is False
    assert res.status == "REJECTED"
    assert "pernah menembus Stop Loss" in res.message or "58000" in res.message


@pytest.mark.asyncio
async def test_execute_signal_rejects_when_risk_exceeds_remaining_budget(async_session: AsyncSession, setup_env: dict):
    """Test that execution is rejected with DailyRiskLimitReachedError if trade risk exceeds remaining budget."""
    acc = setup_env["account"]

    # Wallet: 10,000 USDT. Standard 2% risk = 200 USDT.
    # Set remaining_budget = 50 USDT in daily_risk_repo.
    daily_risk_repo = DailyRiskRepository(async_session)
    today = datetime.now().date()
    daily_snapshot = await daily_risk_repo.get_or_create_daily_snapshot(
        DailyRiskConfigCreate(
            account_id=acc.id,
            risk_profile_id=1,
            date=today,
            balance=Decimal("10000.0"),
            risk_amount=Decimal("200.0"),
            daily_risk_amount=Decimal("500.0"),
        )
    )

    # Mock get_remaining_risk_budget to return only 50 USDT
    daily_risk_repo.get_remaining_risk_budget = AsyncMock(return_value=Decimal("50.0"))

    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("60000.0"))
    mock_binance.has_price_reached_target = AsyncMock(return_value=False)
    mock_binance.set_leverage = AsyncMock(return_value={"leverage": 20})
    mock_binance.set_margin_mode = AsyncMock(return_value={"margin_mode": "ISOLATED"})
    mock_binance.create_entry_order = AsyncMock(return_value={"id": "bin_entry_1", "average": 60000.0})
    mock_binance.create_stop_loss_order = AsyncMock(return_value={"id": "bin_sl_1"})
    mock_binance.create_take_profit_order = AsyncMock(return_value={"id": "bin_tp_1"})

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=daily_risk_repo,
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        exchange_gateway=mock_binance,
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 62000",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("62000")],
        leverage=20,
    )

    from src.domain.exceptions.trade import DailyRiskLimitReachedError
    import pytest
    with pytest.raises(DailyRiskLimitReachedError):
        await trade_service.execute_signal(signal, account_id=acc.id)





