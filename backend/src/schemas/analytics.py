"""Pydantic schemas and DTOs for analytics and dashboard performance metrics."""

from datetime import datetime
from pydantic import BaseModel, Field


class AnalyticsSummaryDTO(BaseModel):
    """High-level dashboard performance summary and risk budget metrics."""
    total_balance_usdt: float = Field(..., description="Total wallet balance in USDT")
    free_margin_usdt: float = Field(..., description="Available free margin in USDT")
    daily_realized_pnl: float = Field(..., description="Realized PnL for today in USDT")
    daily_pnl_percent: float = Field(..., description="Realized PnL percentage for today")
    daily_risk_budget: float = Field(..., description="Total daily risk limit (e.g. 6% / 3x SL) in USDT")
    remaining_risk_budget: float = Field(..., description="Remaining risk budget available today in USDT")
    win_rate: float = Field(..., description="Win rate percentage of closed trades (0-100)")
    total_trades_count: int = Field(..., description="Total number of closed trades")
    winning_trades_count: int = Field(..., description="Count of winning trades")
    losing_trades_count: int = Field(..., description="Count of losing trades")
    profit_factor: float = Field(..., description="Gross profit / Gross loss ratio")
    active_trades_count: int = Field(..., description="Number of currently active positions")


class EquityPointDTO(BaseModel):
    """Snapshot point for equity growth curve chart."""
    timestamp: datetime = Field(..., description="Snapshot timestamp")
    balance: float = Field(..., description="Total equity balance at snapshot")
    pnl: float = Field(..., description="Daily realized PnL at snapshot")
