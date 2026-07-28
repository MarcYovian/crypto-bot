"""SQLAlchemy ORM models for the trading bot database schema."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Text, Integer, Float, DateTime, ForeignKey,
    CheckConstraint, Index, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.connection import Base


class BotSetting(Base):
    """Key-value store for persistent bot configuration.

    Attributes:
        key: Unique setting name.
        value: Setting value.
        description: Optional human-readable explanation.
        updated_at: Timestamp of last update.
    """

    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )


class DailyRiskConfig(Base):
    """Daily risk snapshot: account balance and per-trade risk budget.

    Attributes:
        date: Snapshot date (YYYY-MM-DD, primary key).
        balance: Total USDT balance at snapshot time.
        risk_percent: Percentage of balance allocated per trade.
        risk_amount: Pre-calculated risk amount (balance * risk_percent / 100).
        created_at: Record creation timestamp.
    """

    __tablename__ = "daily_risk_config"

    date: Mapped[str] = mapped_column(Text, primary_key=True)
    balance: Mapped[float] = mapped_column(Float, nullable=False)
    risk_percent: Mapped[float] = mapped_column(Float, nullable=False)
    risk_amount: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    trade_risks: Mapped[List["TradeRisk"]] = relationship(back_populates="daily_risk")


class TradingSignal(Base):
    """A trading signal parsed from a Telegram message.

    Tracks the full lifecycle from ``RECEIVED`` through ``EXECUTED`` or
    ``REJECTED``, with optional user confirmation for low-confidence signals.

    Attributes:
        id: Auto-increment primary key.
        telegram_message_id: Original Telegram message ID (dedup).
        source: Signal source (e.g. ``TELEGRAM``).
        symbol: Trading pair (e.g. ``BTCUSDT``).
        side: ``BUY`` (long) or ``SELL`` (short).
        entry_min / entry_max: Entry price range.
        sl_price: Stop-loss price.
        tp1_price / tp2_price / tp3_price: Take-profit levels.
        confidence: AI / human confidence score (0.0 – 1.0).
        status: Lifecycle status.
        confirmation_status: User confirmation state.
        created_at: Record creation timestamp.
    """

    __tablename__ = "trading_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)

    entry_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entry_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sl_price: Mapped[float] = mapped_column(Float, nullable=False)
    tp1_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tp2_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tp3_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="RECEIVED")
    confirmation_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="NOT_REQUIRED")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    trades: Mapped[List["Trade"]] = relationship(back_populates="signal")

    __table_args__ = (
        CheckConstraint("side IN ('BUY','SELL')", name="chk_signal_side"),
        CheckConstraint("status IN ('RECEIVED','EXECUTED','REJECTED','CANCELLED','EXPIRED')", name="chk_signal_status"),
        CheckConstraint("confirmation_status IN ('NOT_REQUIRED','PENDING','APPROVED','REJECTED')", name="chk_signal_confirm"),
        Index("idx_signal_status", "status"),
        Index("idx_signal_symbol", "symbol"),
    )


class Trade(Base):
    """A trade record representing a Binance Futures position.

    Tracks the position from ``WAITING_ENTRY`` through ``OPEN`` / ``PARTIAL``
    to ``CLOSED`` or ``CANCELLED``.

    Attributes:
        id: Auto-increment primary key.
        signal_id: FK to the originating signal.
        symbol: Trading pair.
        side: ``BUY`` or ``SELL``.
        status: Current lifecycle status.
        entry_price: Actual entry price (may be ``None`` until fill).
        avg_entry_price: Average fill price if multiple partial fills.
        sl_price: Stop-loss price.
        tp1_price / tp2_price / tp3_price: Take-profit prices.
        leverage: Position leverage.
        margin_mode: ``ISOLATED`` or ``CROSSED``.
        position_size: Order quantity.
        remaining_qty: Unfilled quantity.
        opened_at / closed_at: Timestamps for position lifecycle.
    """

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trading_signals.id", ondelete="SET NULL"), nullable=True)

    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="WAITING_ENTRY")

    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sl_price: Mapped[float] = mapped_column(Float, nullable=False)
    tp1_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tp2_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tp3_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    margin_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="ISOLATED")
    position_size: Mapped[float] = mapped_column(Float, nullable=False)
    remaining_qty: Mapped[float] = mapped_column(Float, nullable=False)

    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    signal: Mapped[Optional["TradingSignal"]] = relationship(back_populates="trades")
    trade_risk: Mapped[Optional["TradeRisk"]] = relationship(back_populates="trade", uselist=False, cascade="all, delete-orphan")
    orders: Mapped[List["Order"]] = relationship(back_populates="trade", cascade="all, delete-orphan")
    executions: Mapped[List["Execution"]] = relationship(back_populates="trade", cascade="all, delete-orphan")
    events: Mapped[List["TradeEvent"]] = relationship(back_populates="trade", cascade="all, delete-orphan")
    summary: Mapped[Optional["TradeSummary"]] = relationship(back_populates="trade", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("side IN ('BUY','SELL')", name="chk_trade_side"),
        CheckConstraint("status IN ('WAITING_ENTRY','OPEN','PARTIAL','CLOSED','CANCELLED')", name="chk_trade_status"),
        CheckConstraint("margin_mode IN ('ISOLATED','CROSSED')", name="chk_trade_margin"),
        Index("idx_trade_status", "status"),
        Index("idx_trade_symbol", "symbol"),
        Index("idx_trade_signal", "signal_id"),
    )


class TradeRisk(Base):
    """Risk-calculation detail linked to a trade.

    Attributes:
        trade_id: FK to the trade (PK).
        risk_date: FK to the daily risk config date.
        entry / stop: Formatted entry and stop-loss prices.
        stop_distance: Absolute stop distance.
        qty: Calculated position quantity.
        margin: Required margin in USDT.
        leverage: Leverage used.
    """

    __tablename__ = "trade_risk"

    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), primary_key=True)
    risk_date: Mapped[str] = mapped_column(ForeignKey("daily_risk_config.date"), nullable=False)

    entry: Mapped[float] = mapped_column(Float, nullable=False)
    stop: Mapped[float] = mapped_column(Float, nullable=False)
    stop_distance: Mapped[float] = mapped_column(Float, nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    margin: Mapped[float] = mapped_column(Float, nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    trade: Mapped["Trade"] = relationship(back_populates="trade_risk")
    daily_risk: Mapped["DailyRiskConfig"] = relationship(back_populates="trade_risks")

    __table_args__ = (
        Index("idx_trade_risk_date", "risk_date"),
    )


class Order(Base):
    """An order submitted to Binance for a trade.

    Attributes:
        id: Auto-increment primary key.
        trade_id: FK to the parent trade.
        binance_order_id: Binance-side order ID (unique).
        client_order_id: Client-generated order ID.
        purpose: Order role (ENTRY, TP1, SL, etc.).
        type: Order type (MARKET, LIMIT, STOP_MARKET, etc.).
        side: ``BUY`` or ``SELL``.
        price: Order price (``None`` for market orders).
        qty: Order quantity.
        filled_qty: Cumulatively filled quantity.
        status: Order status (NEW, FILLED, CANCELED, etc.).
    """

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), nullable=False)

    binance_order_id: Mapped[Optional[str]] = mapped_column(Text, unique=True, nullable=True)
    client_order_id: Mapped[Optional[str]] = mapped_column(Text, unique=True, nullable=True)

    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)

    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    filled_qty: Mapped[float] = mapped_column(Float, server_default="0")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="NEW")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    trade: Mapped["Trade"] = relationship(back_populates="orders")
    executions: Mapped[List["Execution"]] = relationship(back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("purpose IN ('ENTRY','TP1','TP2','TP3','SL','BEP_SL','TRAILING_SL','MANUAL_CLOSE')", name="chk_order_purpose"),
        CheckConstraint("type IN ('MARKET','LIMIT','STOP_MARKET','TAKE_PROFIT_MARKET','TRAILING_STOP_MARKET')", name="chk_order_type"),
        CheckConstraint("side IN ('BUY','SELL')", name="chk_order_side"),
        CheckConstraint("status IN ('NEW','PARTIALLY_FILLED','FILLED','CANCELED','EXPIRED','REJECTED')", name="chk_order_status"),
        Index("idx_orders_trade", "trade_id"),
        Index("idx_orders_status", "status"),
        Index("idx_orders_binance_id", "binance_order_id"),
        Index("idx_orders_purpose", "purpose"),
    )


class Execution(Base):
    """A filled execution (partial or full) from Binance.

    Attributes:
        id: Auto-increment primary key.
        order_id: FK to the parent order.
        trade_id: FK to the parent trade.
        price: Fill price.
        qty: Filled quantity (this execution).
        commission: Fee paid for this fill.
        commission_asset: Asset used for fee payment.
        realized_pnl: Realised PnL for this fill (if closing).
        executed_at: Fill timestamp.
    """

    __tablename__ = "executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), nullable=False)

    price: Mapped[float] = mapped_column(Float, nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    commission: Mapped[float] = mapped_column(Float, server_default="0")
    commission_asset: Mapped[str] = mapped_column(Text, server_default="USDT")
    realized_pnl: Mapped[float] = mapped_column(Float, server_default="0")
    executed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    order: Mapped["Order"] = relationship(back_populates="executions")
    trade: Mapped["Trade"] = relationship(back_populates="executions")

    __table_args__ = (
        Index("idx_executions_trade", "trade_id"),
    )


class TradeEvent(Base):
    """A lifecycle event logged for a trade.

    Attributes:
        id: Auto-increment primary key.
        trade_id: FK to the parent trade.
        event_type: Event category (ENTRY, TP1, SL, etc.).
        payload_json: Optional JSON payload with event details.
        created_at: Event timestamp.
    """

    __tablename__ = "trade_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), nullable=False)

    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    trade: Mapped["Trade"] = relationship(back_populates="events")

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('ENTRY','TP1','TP2','TP3','SL','SL_MOVED_TO_BEP','TRAILING_ENABLED','MANUAL_CLOSE','FORCE_CLOSE','FUNDING')",
            name="chk_event_type"
        ),
        Index("idx_trade_events_trade", "trade_id"),
    )


class TradeSummary(Base):
    """Performance summary computed when a trade is closed.

    Attributes:
        trade_id: FK to the trade (PK).
        gross_pnl: Gross profit / loss before fees.
        net_pnl: Profit / loss after commission and funding.
        commission: Total fees paid.
        funding: Total funding rate cost.
        roi: Return on margin (%).
        rr: Risk-reward ratio.
        win: 1 if net_pnl > 0, else 0.
        duration_seconds: Trade duration in seconds.
        close_reason: Why the trade closed (TP3, SL, MANUAL_CLOSE, etc.).
        closed_at: Close timestamp.
    """

    __tablename__ = "trade_summary"

    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), primary_key=True)
    gross_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    net_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    commission: Mapped[float] = mapped_column(Float, nullable=False)
    funding: Mapped[float] = mapped_column(Float, server_default="0")
    roi: Mapped[float] = mapped_column(Float, nullable=False)
    rr: Mapped[float] = mapped_column(Float, nullable=False)
    win: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    close_reason: Mapped[str] = mapped_column(Text, nullable=False)
    closed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    trade: Mapped["Trade"] = relationship(back_populates="summary")

    __table_args__ = (
        CheckConstraint("win IN (0,1)", name="chk_summary_win"),
    )


class Watchlist(Base):
    """Symbols the bot is allowed to trade.

    Attributes:
        symbol: Trading pair (PK).
        enabled: 1 = enabled, 0 = disabled.
        created_at: Record creation timestamp.
    """

    __tablename__ = "watchlist"

    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    __table_args__ = (
        CheckConstraint("enabled IN (0,1)", name="chk_watchlist_enabled"),
    )


class BotLog(Base):
    """Application log entry persisted to the database.

    Attributes:
        id: Auto-increment primary key.
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        message: Log message text.
        context_json: Optional structured context as JSON.
        created_at: Log timestamp.
    """

    __tablename__ = "bot_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    __table_args__ = (
        CheckConstraint("level IN ('DEBUG','INFO','WARNING','ERROR','CRITICAL')", name="chk_bot_log_level"),
        Index("idx_bot_logs_level", "level"),
    )