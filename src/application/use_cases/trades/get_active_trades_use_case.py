"""Use case for querying active trades with live unrealized PnL and Take Profit milestones."""

from typing import Dict, List, Optional
from src.domain.ports.repositories import ITradeRepository
from src.presentation.api.schemas.trade import ActiveTradeDTO, ActiveTradeTPLevelDTO


class GetActiveTradesUseCase:
    """Retrieves all active trades for an account and computes real-time PnL metrics."""

    def __init__(self, trade_repo: ITradeRepository) -> None:
        self.trade_repo = trade_repo

    async def execute(
        self, account_id: int = 1, live_prices: Optional[Dict[str, float]] = None
    ) -> List[ActiveTradeDTO]:
        """Fetch active positions and calculate unrealized PnL and TP status."""
        trades = await self.trade_repo.get_active_positions_with_relations(account_id)
        prices = live_prices or {}

        items: List[ActiveTradeDTO] = []
        for t in trades:
            symbol = t.instrument.symbol if getattr(t, "instrument", None) else "UNKNOWN"
            entry_price = float(t.entry_price) if t.entry_price else None
            sl_price = float(t.sl_price) if t.sl_price else None
            pos_size = float(t.position_size)
            rem_qty = float(t.remaining_qty)
            leverage = int(t.leverage) if t.leverage else 20

            current_price = prices.get(symbol, entry_price)

            unrealized_pnl = 0.0
            unrealized_pnl_percent = 0.0
            if t.status in ("OPEN", "PARTIAL") and entry_price and current_price and rem_qty > 0:
                if t.side.upper() == "BUY":
                    price_diff = current_price - entry_price
                else:
                    price_diff = entry_price - current_price
                unrealized_pnl = round(price_diff * rem_qty, 2)
                pos_margin = (entry_price * rem_qty) / leverage if leverage > 0 else 1.0
                unrealized_pnl_percent = round((unrealized_pnl / pos_margin) * 100, 2)

            hit_event_types = {e.event_type for e in getattr(t, "events", [])}
            tp_levels: List[ActiveTradeTPLevelDTO] = []
            if getattr(t, "tp1_price", None):
                tp_levels.append(
                    ActiveTradeTPLevelDTO(
                        level=1,
                        price=float(t.tp1_price),
                        is_hit="TP1_HIT" in hit_event_types,
                    )
                )
            if getattr(t, "tp2_price", None):
                tp_levels.append(
                    ActiveTradeTPLevelDTO(
                        level=2,
                        price=float(t.tp2_price),
                        is_hit="TP2_HIT" in hit_event_types,
                    )
                )
            if getattr(t, "tp3_price", None):
                tp_levels.append(
                    ActiveTradeTPLevelDTO(
                        level=3,
                        price=float(t.tp3_price),
                        is_hit="TP3_HIT" in hit_event_types,
                    )
                )

            items.append(
                ActiveTradeDTO(
                    trade_id=t.id,
                    symbol=symbol,
                    side=t.side.upper(),
                    status=t.status.upper(),
                    entry_price=entry_price,
                    current_price=current_price,
                    sl_price=sl_price,
                    position_size=pos_size,
                    remaining_qty=rem_qty,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_percent=unrealized_pnl_percent,
                    leverage=leverage,
                    margin_mode=t.margin_mode.upper(),
                    tp_levels=tp_levels,
                    opened_at=t.opened_at,
                )
            )

        return items
