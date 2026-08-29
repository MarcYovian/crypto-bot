"""Use case for reconciling exchange open positions with internal database records."""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.application.dto.trade_commands import SyncPositionsCommand
from src.domain.ports.gateways import IExchangeGateway
from src.domain.ports.repositories import IInstrumentRepository, ITradeRepository
from src.presentation.api.schemas.trade import TradeStatusUpdate

logger = logging.getLogger(__name__)


class SyncPositionsUseCase:
    """Failsafe reconciliation job between Binance exchange live positions and database state."""

    def __init__(
        self,
        trade_repo: ITradeRepository,
        instrument_repo: IInstrumentRepository,
        exchange_gateway: Optional[IExchangeGateway] = None,
    ) -> None:
        self.trade_repo = trade_repo
        self.instrument_repo = instrument_repo
        self.exchange_gateway = exchange_gateway

    async def execute(self, cmd: SyncPositionsCommand) -> Dict[str, Any]:
        """Perform reconciliation audit."""
        if not self.exchange_gateway:
            return {"status": "SKIPPED", "reason": "No exchange gateway configured"}

        # 1. Fetch live open positions from exchange
        exchange_positions = await self.exchange_gateway.fetch_positions()
        live_pos_map = {}
        for pos in exchange_positions:
            contracts = Decimal(str(pos.get("contracts", 0)))
            if contracts > Decimal("0"):
                sym = pos.get("symbol")
                live_pos_map[sym] = pos

        # 2. Fetch database active trades
        db_trades = await self.trade_repo.get_all_active_trades(account_id=cmd.account_id)

        synced_count = 0
        desynced_count = 0
        details = []

        for trade in db_trades:
            sym = trade.instrument.symbol if trade.instrument else "UNKNOWN"
            if sym not in live_pos_map:
                logger.warning(
                    "Failsafe Sync: Trade #%s (%s) is active in DB but closed on Binance. Marking CLOSED.",
                    trade.id,
                    sym,
                )
                await self.trade_repo.update_trade_status(
                    trade_id=trade.id,
                    schema=TradeStatusUpdate(status="CLOSED"),
                )
                desynced_count += 1
                details.append({"trade_id": trade.id, "symbol": sym, "action": "MARKED_CLOSED"})
            else:
                synced_count += 1

        return {
            "status": "COMPLETED",
            "synced_trades": synced_count,
            "desynced_trades": desynced_count,
            "details": details,
        }
