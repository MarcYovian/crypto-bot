"""Use case for querying deep nested trade details with risk, orders, executions, events, and summary."""

from src.domain.exceptions.trade import TradeNotFoundError
from src.domain.ports.repositories import ITradeRepository
from src.presentation.api.schemas.trade import (
    TradeDetailDTO,
    TradeEventDetailDTO,
    TradeExecutionDetailDTO,
    TradeOrderDetailDTO,
    TradeRiskDetailDTO,
    TradeSummaryDetailDTO,
)


class GetTradeDetailUseCase:
    """Fetches full trade details including all child relationships."""

    def __init__(self, trade_repo: ITradeRepository) -> None:
        self.trade_repo = trade_repo

    async def execute(self, trade_id: int) -> TradeDetailDTO:
        """Fetch deep nested trade details or raise TradeNotFoundError."""
        trade = await self.trade_repo.get_detail(trade_id)
        if not trade:
            raise TradeNotFoundError(f"Trade with ID {trade_id} was not found.", trade_id=trade_id)

        symbol = trade.instrument.symbol if getattr(trade, "instrument", None) else "UNKNOWN"

        risk_dto = None
        if getattr(trade, "trade_risk", None):
            risk_dto = TradeRiskDetailDTO(
                risk_amount_usdt=float(trade.trade_risk.risk_amount),
                stop_distance=float(trade.trade_risk.stop_distance),
                required_margin=float(trade.trade_risk.margin),
            )

        orders_dto = [
            TradeOrderDetailDTO(
                id=o.id,
                exchange_order_id=o.exchange_order_id,
                purpose=o.purpose,
                order_type=o.order_type,
                side=o.side,
                price=float(o.price) if o.price else None,
                qty=float(o.qty),
                status=o.status,
            )
            for o in getattr(trade, "orders", [])
        ]

        execs_dto = [
            TradeExecutionDetailDTO(
                price=float(e.price),
                qty=float(e.qty),
                commission=float(e.commission),
                realized_pnl=float(e.realized_pnl),
                executed_at=e.executed_at,
            )
            for e in getattr(trade, "executions", [])
        ]

        events_dto = [
            TradeEventDetailDTO(
                event_type=ev.event_type,
                payload=ev.payload_json,
                created_at=ev.created_at,
            )
            for ev in getattr(trade, "events", [])
        ]

        summary_dto = None
        if getattr(trade, "summary", None):
            summary_dto = TradeSummaryDetailDTO(
                gross_pnl=float(trade.summary.gross_pnl),
                net_pnl=float(trade.summary.net_pnl),
                commission=float(trade.summary.commission),
                roi=float(trade.summary.roi),
                result=trade.summary.result,
            )

        return TradeDetailDTO(
            trade_id=trade.id,
            symbol=symbol,
            side=trade.side.upper(),
            status=trade.status.upper(),
            entry_price=float(trade.entry_price) if trade.entry_price else None,
            sl_price=float(trade.sl_price) if trade.sl_price else None,
            position_size=float(trade.position_size),
            leverage=int(trade.leverage) if trade.leverage else 20,
            risk_details=risk_dto,
            orders=orders_dto,
            executions=execs_dto,
            events=events_dto,
            summary=summary_dto,
        )
