"""Use case for reconciling exchange open positions with internal database records."""

from datetime import datetime
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.application.dto.trade_commands import SyncPositionsCommand
from src.domain.ports.gateways import IExchangeGateway
from src.domain.ports.event_publisher import IDomainEventPublisher
from src.domain.ports.repositories import (
    IInstrumentRepository,
    ITradeRepository,
    IOrderRepository,
    IExecutionRepository,
    ITradeSummaryRepository,
)
from src.domain.events.trade_events import TradeClosedEvent
from src.domain.value_objects.side import OrderSide
from src.presentation.api.schemas.trade import TradeStatusUpdate
from src.presentation.api.schemas.event_summary import TradeSummaryCreate
from src.presentation.api.schemas.order import ExecutionCreate

logger = logging.getLogger(__name__)


class SyncPositionsUseCase:
    """Failsafe self-healing reconciliation job between Binance exchange live positions and database state."""

    def __init__(
        self,
        trade_repo: ITradeRepository,
        instrument_repo: IInstrumentRepository,
        exchange_gateway: Optional[IExchangeGateway] = None,
        order_repo: Optional[IOrderRepository] = None,
        execution_repo: Optional[IExecutionRepository] = None,
        trade_summary_repo: Optional[ITradeSummaryRepository] = None,
        event_publisher: Optional[IDomainEventPublisher] = None,
    ) -> None:
        self.trade_repo = trade_repo
        self.instrument_repo = instrument_repo
        self.exchange_gateway = exchange_gateway
        self.order_repo = order_repo
        self.execution_repo = execution_repo
        self.trade_summary_repo = trade_summary_repo
        self.event_publisher = event_publisher

    async def execute(self, cmd: SyncPositionsCommand) -> Dict[str, Any]:
        """Perform reconciliation audit and self-heal any desynced positions."""
        if not self.exchange_gateway:
            return {"status": "SKIPPED", "reason": "No exchange gateway configured"}

        # 1. Fetch live open positions from exchange
        try:
            exchange_positions = await self.exchange_gateway.fetch_positions()
        except Exception as exc:
            logger.warning("Failsafe Sync: Failed fetching exchange positions: %s", exc)
            return {"status": "FAILED", "reason": str(exc)}

        live_pos_map = {}
        for pos in exchange_positions:
            contracts = Decimal(str(pos.get("contracts", 0)))
            if contracts > Decimal("0"):
                sym = pos.get("symbol")
                if sym:
                    clean_sym = sym.replace("/", "").replace(":USDT", "").upper()
                    live_pos_map[clean_sym] = pos

        # 2. Fetch database active trades (with preloaded instruments)
        db_trades = (
            await self.trade_repo.get_active_trades_with_instrument(account_id=cmd.account_id)
            if hasattr(self.trade_repo, "get_active_trades_with_instrument")
            else await self.trade_repo.get_all_active_trades(account_id=cmd.account_id)
        )

        synced_count = 0
        desynced_count = 0
        details = []

        for trade in db_trades:
            sym = trade.instrument.symbol if trade.instrument else (getattr(trade, "symbol", "") or "UNKNOWN")
            clean_sym = sym.replace("/", "").replace(":USDT", "").upper()

            if clean_sym not in live_pos_map:
                logger.warning(
                    "Failsafe Sync: Trade #%s (%s) is active in DB but closed on Binance. Initiating Self-Healing closure...",
                    trade.id,
                    clean_sym,
                )

                # Fetch real execution history from Binance to obtain exact exit fill, PnL, commission
                exit_price = trade.sl_price or trade.entry_price or Decimal("0")
                exit_qty = trade.remaining_qty or trade.position_size or Decimal("0")
                fee = Decimal("0.0")
                realized_pnl = Decimal("0.0")
                close_reason = "STOP_LOSS_HIT"

                if hasattr(self.exchange_gateway, "fetch_my_trades"):
                    try:
                        recent_trades = await self.exchange_gateway.fetch_my_trades(clean_sym, limit=5)
                        if recent_trades:
                            last_t = recent_trades[-1]
                            avg_p = last_t.get("price")
                            if avg_p:
                                exit_price = Decimal(str(avg_p))
                            amt = last_t.get("amount")
                            if amt:
                                exit_qty = Decimal(str(amt))
                            f_dict = last_t.get("fee") or {}
                            if isinstance(f_dict, dict):
                                fee = Decimal(str(f_dict.get("cost") or 0.0))

                            mult = Decimal("1") if trade.side.upper() in ("BUY", "LONG") else Decimal("-1")
                            entry_p = trade.entry_price or exit_price
                            realized_pnl = (exit_price - entry_p) * exit_qty * mult

                            # Classify close reason
                            if trade.sl_price and (
                                (mult == 1 and exit_price <= trade.sl_price * Decimal("1.005"))
                                or (mult == -1 and exit_price >= trade.sl_price * Decimal("0.995"))
                            ):
                                close_reason = "STOP_LOSS_HIT"
                            elif trade.tp1_price and (
                                (mult == 1 and exit_price >= trade.tp1_price * Decimal("0.995"))
                                or (mult == -1 and exit_price <= trade.tp1_price * Decimal("1.005"))
                            ):
                                close_reason = "TAKE_PROFIT_ALL"
                            else:
                                close_reason = "STOP_LOSS_HIT" if realized_pnl <= 0 else "TAKE_PROFIT_ALL"
                    except Exception as trade_fetch_exc:
                        logger.debug("Could not fetch trade history for self-healing: %s", trade_fetch_exc)

                # Record execution in DB
                if self.execution_repo:
                    try:
                        await self.execution_repo.create(
                            ExecutionCreate(
                                trade_id=trade.id,
                                order_id=None,
                                price=exit_price,
                                qty=exit_qty,
                                commission=fee,
                                commission_asset="USDT",
                                realized_pnl=realized_pnl,
                                executed_at=datetime.now(),
                            )
                        )
                    except Exception as e_exc:
                        logger.debug("Failed saving execution in self-healing sync: %s", e_exc)

                # Update Trade Status to CLOSED
                await self.trade_repo.update_partial_close(
                    trade_id=trade.id,
                    closed_qty=exit_qty,
                )
                await self.trade_repo.update_trade_status(
                    trade_id=trade.id,
                    schema=TradeStatusUpdate(status="CLOSED"),
                )

                # Clean up open orders
                if self.order_repo:
                    try:
                        await self.order_repo.cancel_all_open_orders_for_trade(trade.id)
                    except Exception:
                        pass
                if hasattr(self.exchange_gateway, "cancel_all_open_orders"):
                    try:
                        await self.exchange_gateway.cancel_all_open_orders(clean_sym)
                    except Exception:
                        pass

                # Record TradeSummary
                if self.trade_summary_repo:
                    try:
                        existing_sum = await self.trade_summary_repo.get(trade.id)
                        net_pnl = realized_pnl - fee
                        sum_payload = TradeSummaryCreate(
                            trade_id=trade.id,
                            gross_pnl=realized_pnl,
                            net_pnl=net_pnl,
                            commission=fee,
                            funding=Decimal("0.0"),
                            roi=Decimal("0.0"),
                            rr=Decimal("0.0"),
                            result="WIN" if net_pnl > Decimal("0") else ("LOSS" if net_pnl < Decimal("0") else "BREAKEVEN"),
                            duration_seconds=0,
                            close_reason=close_reason,
                            closed_at=datetime.now(),
                        )
                        if existing_sum:
                            await self.trade_summary_repo.update(existing_sum, sum_payload)
                        else:
                            await self.trade_summary_repo.create(sum_payload)
                    except Exception as sum_exc:
                        logger.debug("Failed recording trade summary in self-healing sync: %s", sum_exc)

                # Publish TradeClosedEvent to trigger Telegram summary report
                if self.event_publisher:
                    try:
                        await self.event_publisher.publish(
                            TradeClosedEvent(
                                trade_id=trade.id,
                                account_id=trade.account_id,
                                symbol=clean_sym,
                                side=OrderSide.from_str(trade.side, default=OrderSide.BUY),
                                exit_price=exit_price,
                                total_realized_pnl=realized_pnl - fee,
                                close_reason=close_reason,
                                closed_qty=exit_qty,
                            )
                        )
                    except Exception as pub_exc:
                        logger.error("Failed publishing TradeClosedEvent on self-healing sync: %s", pub_exc)

                desynced_count += 1
                details.append({
                    "trade_id": trade.id,
                    "symbol": clean_sym,
                    "action": "SELF_HEALED_CLOSED",
                    "pnl": float(realized_pnl - fee),
                    "reason": close_reason,
                })
            else:
                synced_count += 1

        return {
            "status": "COMPLETED",
            "synced_trades": synced_count,
            "desynced_trades": desynced_count,
            "details": details,
        }
