"""Comprehensive unit test suite for all Pydantic DTOs and Validation Schemas."""

from datetime import datetime, date
from decimal import Decimal
import pytest
from pydantic import ValidationError

from src.presentation.api.schemas import (
    # Common
    PaginatedResponse,
    # Master
    ExchangeCreate,
    ExchangeUpdate,
    ExchangeRead,
    TradingAccountCreate,
    TradingAccountUpdate,
    TradingAccountRead,
    TradingCredentialCreate,
    TradingCredentialUpdate,
    TradingCredentialRead,
    InstrumentCreate,
    InstrumentUpdate,
    InstrumentRead,
    StrategyCreate,
    StrategyRead,
    SignalProviderCreate,
    SignalProviderRead,
    RiskProfileCreate,
    RiskProfileRead,
    WatchlistCreate,
    WatchlistRead,
    # Signal
    ParsedSignalDTO,
    TradingSignalCreate,
    TradingSignalUpdate,
    TradingSignalRead,
    SignalConfirmationDTO,
    # Risk
    DailyRiskConfigCreate,
    DailyRiskConfigRead,
    TradeRiskCreate,
    TradeRiskRead,
    RiskCalculationResultDTO,
    # Trade
    TradeCreate,
    TradeUpdate,
    TradeStatusUpdate,
    TradeRead,
    TradeDetailRead,
    # Order & Execution
    OrderCreate,
    OrderStatusUpdate,
    OrderRead,
    ExecutionCreate,
    ExecutionRead,
    # Event & Summary
    TradeEventCreate,
    TradeEventRead,
    TradeSummaryCreate,
    TradeSummaryRead,
    PerformanceSummaryDTO,
    # System
    BotSettingCreate,
    BotSettingUpdate,
    BotSettingRead,
    BotLogCreate,
    BotLogRead,
)


# =====================================================================
# 1. MASTER SCHEMAS TESTS
# =====================================================================

def test_exchange_schemas():
    """Test Exchange validation, uppercase normalization, and reading."""
    ex_in = ExchangeCreate(code="  binance ", name="Binance Futures")
    assert ex_in.code == "BINANCE"
    assert ex_in.status is True

    ex_update = ExchangeUpdate(status=False)
    assert ex_update.status is False

    ex_read = ExchangeRead.model_validate({"id": 1, "code": "BYBIT", "name": "Bybit", "status": True})
    assert ex_read.id == 1
    assert ex_read.code == "BYBIT"


def test_trading_account_schemas():
    """Test TradingAccount environment validation (MAINNET / TESTNET)."""
    acc_valid = TradingAccountCreate(
        exchange_id=1,
        name="Main Account",
        environment="testnet"
    )
    assert acc_valid.environment == "TESTNET"

    # Invalid environment value
    with pytest.raises(ValidationError):
        TradingAccountCreate(
            exchange_id=1,
            name="Main Account",
            environment="STAGING"
        )


def test_trading_credential_masking():
    """Test that TradingCredentialRead safely masks API keys and hides secrets."""
    class MockCredentialORM:
        id = 1
        account_id = 1
        key_name = "Binance API Key"
        encrypted_api_key = "abcdef1234567890"
        encrypted_secret_key = "super_secret_key_should_never_leak"
        key_version = 1
        is_active = True
        created_at = datetime.now()
        updated_at = None

    cred_read = TradingCredentialRead.from_orm_model(MockCredentialORM())
    assert cred_read.masked_api_key == "abcd****7890"
    assert not hasattr(cred_read, "secret_key")
    assert not hasattr(cred_read, "encrypted_secret_key")

    # Test Credential Create
    cred_in = TradingCredentialCreate(
        account_id=1,
        key_name="Test Key",
        api_key="123456789012345",
        secret_key="secretkey1234567890"
    )
    assert cred_in.key_version == 1


def test_instrument_schemas():
    """Test Instrument precision, positive step size, and uppercase symbol formatting."""
    inst_in = InstrumentCreate(
        exchange_id=1,
        symbol="  ethusdt ",
        base_asset="eth",
        quote_asset="usdt",
        tick_size=Decimal("0.01"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5.0"),
        price_precision=2,
        qty_precision=3
    )
    assert inst_in.symbol == "ETHUSDT"
    assert inst_in.base_asset == "ETH"
    assert inst_in.quote_asset == "USDT"

    # Invalid: non-positive tick size
    with pytest.raises(ValidationError):
        InstrumentCreate(
            exchange_id=1,
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            tick_size=Decimal("-0.01"),
            step_size=Decimal("0.001"),
            min_qty=Decimal("0.001"),
            min_notional=Decimal("5.0")
        )


def test_strategy_and_signal_provider_schemas():
    """Test Strategy and SignalProvider schema validation."""
    strat = StrategyCreate(name="SMC Liquidity Sweep", version="2.1.0")
    assert strat.version == "2.1.0"
    assert strat.is_active is True

    provider = SignalProviderCreate(name="VIP Crypto Calls", type="TELEGRAM")
    assert provider.name == "VIP Crypto Calls"


def test_risk_profile_schemas():
    """Test RiskProfile percentage validation constraints (0 < risk <= 10.0)."""
    rp = RiskProfileCreate(
        name="Moderate 2%",
        risk_percent=Decimal("2.0"),
        max_daily_loss=Decimal("6.0"),
        max_open_trade=3
    )
    assert rp.risk_percent == Decimal("2.0")

    # Invalid: risk percent exceeding safety ceiling (10%)
    with pytest.raises(ValidationError):
        RiskProfileCreate(
            name="Dangerously High",
            risk_percent=Decimal("25.0"),
            max_daily_loss=Decimal("50.0")
        )


def test_watchlist_schemas():
    """Test Watchlist create and nested instrument relation."""
    wl_in = WatchlistCreate(instrument_id=1, enabled=True)
    assert wl_in.instrument_id == 1

    wl_read = WatchlistRead.model_validate({
        "id": 1,
        "instrument_id": 1,
        "enabled": True,
        "instrument": {
            "id": 1,
            "exchange_id": 1,
            "symbol": "BTCUSDT",
            "base_asset": "BTC",
            "quote_asset": "USDT",
            "tick_size": Decimal("0.1"),
            "step_size": Decimal("0.001"),
            "min_qty": Decimal("0.001"),
            "min_notional": Decimal("5.0"),
            "price_precision": 1,
            "qty_precision": 3,
            "is_active": True
        }
    })
    assert wl_read.instrument.symbol == "BTCUSDT"


# =====================================================================
# 2. SIGNAL SCHEMAS TESTS
# =====================================================================

def test_parsed_signal_dto_validation():
    """Test ParsedSignalDTO domain validation rules."""
    # Valid BUY signal
    valid_buy = ParsedSignalDTO(
        symbol="btcusdt",
        side="buy",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60500"),
        sl_price=Decimal("59000"),
        tp_prices=[Decimal("61000"), Decimal("62000")],
        confidence=Decimal("0.85")
    )
    assert valid_buy.symbol == "BTCUSDT"
    assert valid_buy.side == "BUY"
    assert valid_buy.is_valid is True

    # Invalid: entry_min > entry_max
    with pytest.raises(ValidationError):
        ParsedSignalDTO(
            symbol="BTCUSDT",
            side="BUY",
            entry_min=Decimal("61000"),
            entry_max=Decimal("60000"),
            sl_price=Decimal("59000")
        )

    # Invalid: BUY signal with sl_price >= entry_min
    with pytest.raises(ValidationError):
        ParsedSignalDTO(
            symbol="BTCUSDT",
            side="BUY",
            entry_min=Decimal("60000"),
            entry_max=Decimal("60500"),
            sl_price=Decimal("60200")
        )

    # Invalid: SELL signal with sl_price <= entry_max
    with pytest.raises(ValidationError):
        ParsedSignalDTO(
            symbol="BTCUSDT",
            side="SELL",
            entry_min=Decimal("59500"),
            entry_max=Decimal("60000"),
            sl_price=Decimal("59800")
        )


def test_domain_parsed_signal_dto_from_dict_and_from_json():
    """Test domain ParsedSignalDTO.from_dict and from_json with strict Decimal conversions."""
    from src.domain.entities.signal import ParsedSignalDTO as DomainParsedSignalDTO

    raw_json = (
        '{"symbol": "WIFUSDT", "side": "BUY", "order_type": "MARKET", "entry_min": "0.2", '
        '"entry_max": "0.2", "entry_targets": ["0.2"], "sl_price": "0.1990", '
        '"tp_targets": ["0.21", "0.22", "0.23"], "leverage": 75, "timeframe": "1H", '
        '"pattern": "Ranging Channel", "notes": "Valid test pattern", "confidence_score": 0.78, '
        '"is_valid": true, "trace_id": "sig-d852aefe"}'
    )

    dto = DomainParsedSignalDTO.from_json(raw_json)
    assert dto.symbol == "WIFUSDT"
    assert dto.side == "BUY"
    assert dto.order_type == "MARKET"
    assert isinstance(dto.entry_min, Decimal)
    assert dto.entry_min == Decimal("0.2")
    assert isinstance(dto.sl_price, Decimal)
    assert dto.sl_price == Decimal("0.1990")
    assert isinstance(dto.tp_targets[0], Decimal)
    assert dto.tp_targets == [Decimal("0.21"), Decimal("0.22"), Decimal("0.23")]
    assert dto.leverage == 75
    assert dto.timeframe == "1H"
    assert dto.pattern == "Ranging Channel"
    assert dto.notes == "Valid test pattern"
    assert dto.confidence_score == 0.78
    assert dto.trace_id == "sig-d852aefe"
    assert dto.avg_entry_price == Decimal("0.2")

    # Test roundtrip serialization
    json_out = dto.to_json()
    dto_roundtrip = DomainParsedSignalDTO.from_json(json_out)
    assert dto_roundtrip.symbol == dto.symbol
    assert dto_roundtrip.sl_price == dto.sl_price
    assert dto_roundtrip.leverage == dto.leverage



def test_trading_signal_and_confirmation_schemas():
    """Test TradingSignalCreate and Telegram user confirmation DTO."""
    sig_in = TradingSignalCreate(
        provider_id=1,
        instrument_id=1,
        telegram_message_id=987654,
        side="BUY",
        sl_price=Decimal("59000"),
        tp1_price=Decimal("61000"),
        confidence=Decimal("0.65"),
        status="RECEIVED",
        confirmation_status="PENDING"
    )
    assert sig_in.telegram_message_id == 987654

    # Confirmation DTO (APPROVE / REJECT)
    conf = SignalConfirmationDTO(signal_id=1, action="APPROVE", user_id=12345678)
    assert conf.action == "APPROVE"

    with pytest.raises(ValidationError):
        SignalConfirmationDTO(signal_id=1, action="MAYBE", user_id=12345678)


# =====================================================================
# 3. RISK SCHEMAS TESTS
# =====================================================================

def test_daily_risk_config_schemas():
    """Test DailyRiskConfig snapshot schemas."""
    d_risk = DailyRiskConfigCreate(
        account_id=1,
        risk_profile_id=1,
        date=date(2026, 8, 14),
        balance=Decimal("10000.00"),
        risk_amount=Decimal("200.00")
    )
    assert d_risk.balance == Decimal("10000.00")
    assert d_risk.date == date(2026, 8, 14)


def test_trade_risk_and_calculation_dto():
    """Test RiskCalculationResultDTO and TradeRiskCreate."""
    calc_dto = RiskCalculationResultDTO(
        entry_price=Decimal("60000"),
        stop_loss_price=Decimal("59000"),
        stop_distance=Decimal("1000"),
        risk_amount=Decimal("200"),
        position_size=Decimal("0.2"),
        required_margin=Decimal("800"),
        leverage=15
    )
    assert calc_dto.position_size == Decimal("0.2")

    tr_in = TradeRiskCreate(
        trade_id=1,
        daily_risk_id=1,
        entry=calc_dto.entry_price,
        stop=calc_dto.stop_loss_price,
        stop_distance=calc_dto.stop_distance,
        qty=calc_dto.position_size,
        margin=calc_dto.required_margin,
        risk_amount=calc_dto.risk_amount,
        leverage=calc_dto.leverage
    )
    assert tr_in.trade_id == 1


# =====================================================================
# 4. TRADE SCHEMAS TESTS
# =====================================================================

def test_trade_and_nested_trade_detail_schemas():
    """Test TradeCreate, status transition, and nested TradeDetailRead schema."""
    trade_in = TradeCreate(
        instrument_id=1,
        side="BUY",
        sl_price=Decimal("59000"),
        position_size=Decimal("0.05"),
        remaining_qty=Decimal("0.05"),
        leverage=15
    )
    assert trade_in.leverage == 15
    assert trade_in.status == "WAITING_ENTRY"

    status_update = TradeStatusUpdate(status="OPEN", opened_at=datetime.now())
    assert status_update.status == "OPEN"

    # Test full nested TradeDetailRead
    detail_data = {
        "id": 101,
        "account_id": 1,
        "instrument_id": 1,
        "side": "BUY",
        "status": "CLOSED",
        "entry_price": Decimal("60000"),
        "sl_price": Decimal("59000"),
        "tp1_price": Decimal("61000"),
        "position_size": Decimal("0.05"),
        "remaining_qty": Decimal("0"),
        "leverage": 15,
        "margin_mode": "ISOLATED",
        "trade_risk": {
            "trade_id": 101,
            "daily_risk_id": 1,
            "entry": Decimal("60000"),
            "stop": Decimal("59000"),
            "stop_distance": Decimal("1000"),
            "qty": Decimal("0.05"),
            "margin": Decimal("200"),
            "risk_amount": Decimal("50"),
            "leverage": 15
        },
        "orders": [
            {
                "id": 1,
                "trade_id": 101,
                "purpose": "ENTRY",
                "order_type": "MARKET",
                "side": "BUY",
                "qty": Decimal("0.05"),
                "filled_qty": Decimal("0.05"),
                "status": "FILLED"
            }
        ],
        "executions": [
            {
                "id": 1,
                "order_id": 1,
                "trade_id": 101,
                "price": Decimal("60000"),
                "qty": Decimal("0.05"),
                "commission": Decimal("1.2"),
                "commission_asset": "USDT",
                "realized_pnl": Decimal("0")
            }
        ],
        "events": [
            {
                "id": 1,
                "trade_id": 101,
                "event_type": "TP1_HIT",
                "payload_json": '{"price": 61000}'
            }
        ],
        "summary": {
            "trade_id": 101,
            "gross_pnl": Decimal("50.0"),
            "net_pnl": Decimal("48.8"),
            "commission": Decimal("1.2"),
            "funding": Decimal("0"),
            "roi": Decimal("24.4"),
            "rr": Decimal("1.0"),
            "result": "WIN",
            "duration_seconds": 1800,
            "close_reason": "TP1",
            "closed_at": datetime.now()
        }
    }

    trade_detail = TradeDetailRead.model_validate(detail_data)
    assert trade_detail.id == 101
    assert trade_detail.trade_risk.risk_amount == Decimal("50")
    assert len(trade_detail.orders) == 1
    assert trade_detail.summary.result == "WIN"


# =====================================================================
# 5. ORDER & EXECUTION SCHEMAS TESTS
# =====================================================================

def test_order_and_execution_schemas():
    """Test OrderCreate, OrderStatusUpdate, and ExecutionCreate."""
    ord_in = OrderCreate(
        trade_id=1,
        purpose="ENTRY",
        order_type="LIMIT",
        side="BUY",
        price=Decimal("60000"),
        qty=Decimal("0.1")
    )
    assert ord_in.purpose == "ENTRY"
    assert ord_in.status == "NEW"

    ord_up = OrderStatusUpdate(
        exchange_order_id="binance_ord_9988",
        status="FILLED",
        filled_qty=Decimal("0.1")
    )
    assert ord_up.status == "FILLED"

    exec_in = ExecutionCreate(
        order_id=1,
        trade_id=1,
        price=Decimal("60000"),
        qty=Decimal("0.1"),
        commission=Decimal("0.024")
    )
    assert exec_in.commission_asset == "USDT"


# =====================================================================
# 6. EVENT, SUMMARY & PERFORMANCE TESTS
# =====================================================================

def test_trade_event_and_summary_schemas():
    """Test TradeEventCreate, TradeSummaryCreate, and PerformanceSummaryDTO."""
    ev_in = TradeEventCreate(trade_id=1, event_type="SL_MOVED_TO_BEP")
    assert ev_in.event_type == "SL_MOVED_TO_BEP"

    sum_in = TradeSummaryCreate(
        trade_id=1,
        gross_pnl=Decimal("120.00"),
        net_pnl=Decimal("118.50"),
        commission=Decimal("1.50"),
        roi=Decimal("59.25"),
        rr=Decimal("2.4"),
        result="WIN",
        duration_seconds=3600,
        close_reason="TP2",
        closed_at=datetime.now()
    )
    assert sum_in.result == "WIN"

    perf = PerformanceSummaryDTO(
        total_trades=10,
        winning_trades=7,
        losing_trades=3,
        winrate=Decimal("70.0"),
        total_net_pnl=Decimal("350.50")
    )
    assert perf.winrate == Decimal("70.0")
    assert perf.total_trades == 10


# =====================================================================
# 7. SYSTEM SETTING & LOG TESTS
# =====================================================================

def test_system_schemas():
    """Test BotSetting and BotLog schemas."""
    setting_in = BotSettingCreate(
        key="DEFAULT_LEVERAGE",
        category="TRADING",
        type="INT",
        value="15"
    )
    assert setting_in.value == "15"

    log_in = BotLogCreate(
        module="POSITION_MANAGER",
        level="WARNING",
        message="Trailing SL adjusted near liquidation boundary",
        context_json='{"symbol": "ETHUSDT"}'
    )
    assert log_in.level == "WARNING"

    # Invalid log level
    with pytest.raises(ValidationError):
        BotLogCreate(level="VERBOSE", message="Test")


# =====================================================================
# 8. COMMON GENERIC PAGINATION TEST
# =====================================================================

def test_paginated_response_generic():
    """Test generic PaginatedResponse container."""
    items = [
        TradeRead(
            id=1,
            instrument_id=1,
            side="BUY",
            sl_price=Decimal("59000"),
            position_size=Decimal("0.1"),
            remaining_qty=Decimal("0.1")
        )
    ]
    paginated = PaginatedResponse[TradeRead](
        items=items,
        total=1,
        page=1,
        page_size=10,
        total_pages=1
    )
    assert len(paginated.items) == 1
    assert paginated.items[0].id == 1
