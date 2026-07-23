# models.py
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Text, Integer, Float, DateTime, ForeignKey, 
    CheckConstraint, Index, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.connection import Base


# 1. BOT SETTINGS
class BotSetting(Base):
    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )


# 2. DAILY RISK CONFIG
class DailyRiskConfig(Base):
    __tablename__ = "daily_risk_config"

    date: Mapped[str] = mapped_column(Text, primary_key=True)  # YYYY-MM-DD
    balance: Mapped[float] = mapped_column(Float, nullable=False)
    risk_percent: Mapped[float] = mapped_column(Float, nullable=False)
    risk_amount: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    # Relationships
    trade_risks: Mapped[List["TradeRisk"]] = relationship(back_populates="daily_risk")


# 3. TRADING SIGNALS
class TradingSignal(Base):
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

    # Relationships
    trades: Mapped[List["Trade"]] = relationship(back_populates="signal")

    __table_args__ = (
        CheckConstraint("side IN ('BUY','SELL')", name="chk_signal_side"),
        CheckConstraint("status IN ('RECEIVED','EXECUTED','REJECTED','CANCELLED','EXPIRED')", name="chk_signal_status"),
        CheckConstraint("confirmation_status IN ('NOT_REQUIRED','PENDING','APPROVED','REJECTED')", name="chk_signal_confirm"),
        Index("idx_signal_status", "status"),
        Index("idx_signal_symbol", "symbol"),
    )


# 4. TRADES
class Trade(Base):
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

    # Relationships
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


# 5. TRADE RISK
class TradeRisk(Base):
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

    # Relationships
    trade: Mapped["Trade"] = relationship(back_populates="trade_risk")
    daily_risk: Mapped["DailyRiskConfig"] = relationship(back_populates="trade_risks")

    __table_args__ = (
        Index("idx_trade_risk_date", "risk_date"),
    )


# 6. ORDERS
class Order(Base):
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

    # Relationships
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


# 7. EXECUTIONS
class Execution(Base):
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

    # Relationships
    order: Mapped["Order"] = relationship(back_populates="executions")
    trade: Mapped["Trade"] = relationship(back_populates="executions")

    __table_args__ = (
        Index("idx_executions_trade", "trade_id"),
    )


# 8. TRADE EVENTS
class TradeEvent(Base):
    __tablename__ = "trade_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), nullable=False)
    
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    # Relationships
    trade: Mapped["Trade"] = relationship(back_populates="events")

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('ENTRY','TP1','TP2','TP3','SL','SL_MOVED_TO_BEP','TRAILING_ENABLED','MANUAL_CLOSE','FORCE_CLOSE','FUNDING')",
            name="chk_event_type"
        ),
        Index("idx_trade_events_trade", "trade_id"),
    )


# 9. TRADE SUMMARY
class TradeSummary(Base):
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

    # Relationships
    trade: Mapped["Trade"] = relationship(back_populates="summary")

    __table_args__ = (
        CheckConstraint("win IN (0,1)", name="chk_summary_win"),
    )


# 10. WATCHLIST
class Watchlist(Base):
    __tablename__ = "watchlist"

    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    __table_args__ = (
        CheckConstraint("enabled IN (0,1)", name="chk_watchlist_enabled"),
    )


# 11. BOT LOGS
class BotLog(Base):
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