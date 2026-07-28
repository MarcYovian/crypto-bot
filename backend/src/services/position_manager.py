"""Position lifecycle manager: SL-to-BEP, partial fills, trade closure, and summaries."""

import logging
from datetime import datetime
from typing import Optional
from src.repository.trade_repository import TradeRepository
from src.database.models import Trade, Order

logger = logging.getLogger(__name__)


class PositionManager:
    """Manages active position dynamics: SL-to-BEP promotion on TP1, trailing stop,
    and trade-summary generation on closure.

    This is the core state-machine that reacts to order-filled events dispatched
    by the WebSocket listener.
    """

    def __init__(self, trade_repo: TradeRepository, execution_engine=None):
        self.trade_repo = trade_repo
        self.execution_engine = execution_engine

    async def handle_order_fill(self, trade: Trade, filled_order: Order, fill_price: float, fill_qty: float) -> None:
        """React to an order-filled event from the WebSocket stream.

        Dispatches based on the order's purpose:

        - ``ENTRY`` → sets status to ``OPEN``; places SL/TP if entry was LIMIT.
        - ``TP1``   → sets status to ``PARTIAL``; moves SL to break-even.
        - ``TP2``   → sets status to ``PARTIAL``.
        - ``TP3`` / ``SL`` / ``BEP_SL`` / ``MANUAL_CLOSE`` → closes the trade
          and generates a performance summary.
        """
        purpose = filled_order.purpose
        logger.info(f"[PositionManager] Processing Fill for Trade #{trade.id} | Purpose: {purpose} | Price: {fill_price}")

        if purpose == "ENTRY":
            if trade.status == "WAITING_ENTRY":
                await self.trade_repo.update_trade_status(
                    trade_id=trade.id,
                    status="OPEN",
                    opened_at=datetime.now()
                )
                await self.trade_repo.log_event(trade.id, "ENTRY", f'{{"fill_price": {fill_price}, "qty": {fill_qty}}}')

                # For LIMIT orders the SL/TP are placed now (market orders
                # already had them placed by the execution engine).
                if filled_order.type == "LIMIT" and self.execution_engine:
                    try:
                        exit_side = 'sell' if trade.side == 'BUY' else 'buy'
                        # Pasang SL
                        sl_order = await self.execution_engine.exchange.create_order(
                            symbol=trade.symbol,
                            type='STOP_MARKET',
                            side=exit_side,
                            amount=trade.position_size,
                            params={'stopPrice': trade.sl_price, 'closePosition': True}
                        )
                        await self.trade_repo.create_order(
                            trade_id=trade.id,
                            purpose="SL",
                            order_type="STOP_MARKET",
                            side=exit_side.upper(),
                            qty=trade.position_size,
                            price=trade.sl_price,
                            binance_order_id=str(sl_order['id'])
                        )
                    except Exception as err:
                        logger.error(f"[Trade #{trade.id}] Error setting SL after LIMIT fill: {err}")

        elif purpose == "TP1":
            await self.trade_repo.update_trade_status(trade.id, "PARTIAL")
            await self.trade_repo.log_event(trade.id, "TP1", f'{{"fill_price": {fill_price}}}')
            await self._move_sl_to_bep(trade)

        elif purpose == "TP2":
            await self.trade_repo.update_trade_status(trade.id, "PARTIAL")
            await self.trade_repo.log_event(trade.id, "TP2", f'{{"fill_price": {fill_price}}}')
            if trade.tp1_price:
                await self._move_sl_to_tp1(trade)

        elif purpose in ["TP3", "SL", "BEP_SL", "TRAIL_SL", "MANUAL_CLOSE"]:
            close_reason = purpose
            await self.close_trade(trade, close_reason=close_reason, exit_price=fill_price)

    async def _move_sl_to_bep(self, trade: Trade) -> None:
        """Move the stop-loss to the entry price (break-even point).

        Cancels the existing SL on Binance and places a new ``STOP_MARKET``
        order at the entry price with ``reduceOnly``.
        """
        bep_price = trade.entry_price or trade.avg_entry_price
        logger.info(f"[Trade #{trade.id}] Moving SL to BEP @ {bep_price}")

        try:
            if self.execution_engine:
                exit_side = 'sell' if trade.side == 'BUY' else 'buy'
                
                # Pasang SL Baru di BEP
                new_sl_order = await self.execution_engine.exchange.create_order(
                    symbol=trade.symbol,
                    type='STOP_MARKET',
                    side=exit_side,
                    amount=trade.remaining_qty,
                    params={
                        'stopPrice': bep_price,
                        'reduceOnly': True
                    }
                )
                
                # Catat order BEP_SL baru di database
                await self.trade_repo.create_order(
                    trade_id=trade.id,
                    purpose="BEP_SL",
                    order_type="STOP_MARKET",
                    side="SELL" if trade.side == "BUY" else "BUY",
                    qty=trade.remaining_qty,
                    price=bep_price,
                    binance_order_id=str(new_sl_order['id'])
                )

            await self.trade_repo.log_event(
                trade.id, "SL_MOVED_TO_BEP", f'{{"bep_price": {bep_price}}}'
            )

        except Exception as e:
            logger.error(f"[Trade #{trade.id}] Failed to move SL to BEP: {str(e)}")

    async def _move_sl_to_tp1(self, trade: Trade) -> None:
        """Trailing Stop: Move the stop-loss to TP1 price when TP2 is hit."""
        if not trade.tp1_price:
            return

        tp1_price = trade.tp1_price
        logger.info(f"[Trade #{trade.id}] Trailing Stop: Moving SL to TP1 @ {tp1_price}")

        try:
            if self.execution_engine:
                exit_side = 'sell' if trade.side == 'BUY' else 'buy'

                # Batalkan SL/BEP_SL sebelumnya jika ada
                try:
                    await self.execution_engine.exchange.cancel_all_orders(trade.symbol)
                except Exception as err:
                    logger.debug(f"Cancel existing orders note [{trade.symbol}]: {err}")

                # Pasang SL Baru di harga TP1 (Trailing Step-up)
                new_sl_order = await self.execution_engine.exchange.create_order(
                    symbol=trade.symbol,
                    type='STOP_MARKET',
                    side=exit_side,
                    amount=trade.remaining_qty,
                    params={
                        'stopPrice': tp1_price,
                        'reduceOnly': True
                    }
                )

                await self.trade_repo.create_order(
                    trade_id=trade.id,
                    purpose="TRAIL_SL",
                    order_type="STOP_MARKET",
                    side="SELL" if trade.side == "BUY" else "BUY",
                    qty=trade.remaining_qty,
                    price=tp1_price,
                    binance_order_id=str(new_sl_order['id'])
                )

            await self.trade_repo.log_event(
                trade.id, "SL_MOVED_TO_TP1", f'{{"tp1_price": {tp1_price}}}'
            )

        except Exception as e:
            logger.error(f"[Trade #{trade.id}] Failed to move SL to TP1: {str(e)}")

    async def close_trade(self, trade: Trade, close_reason: str, exit_price: float) -> None:
        """Close a trade, cancel remaining orders, and persist the performance summary."""
        closed_at = datetime.now()
        await self.trade_repo.update_trade_status(trade.id, "CLOSED", closed_at=closed_at)
        await self.trade_repo.log_event(trade.id, close_reason, f'{{"exit_price": {exit_price}}}')

        # Cancel remaining orders on Binance (e.g. unfilled TP2/TP3 if stopped out)
        if self.execution_engine:
            try:
                await self.execution_engine.exchange.cancel_all_orders(trade.symbol)
            except Exception as e:
                logger.warning(f"[Trade #{trade.id}] Warning cancelling remaining orders: {e}")

        await self._generate_trade_summary(trade, close_reason, exit_price, closed_at)

    async def _generate_trade_summary(self, trade: Trade, close_reason: str, exit_price: float, closed_at: datetime) -> None:
        """Calculate and persist PnL, ROI, R:R, duration, funding fee, and win/loss for the closed trade."""
        entry_price = trade.entry_price or trade.avg_entry_price or 1.0
        
        # Hitung Gross PNL
        if trade.side == "BUY":
            gross_pnl = (exit_price - entry_price) * trade.position_size
        else:
            gross_pnl = (entry_price - exit_price) * trade.position_size

        # Perkiraan komisi Taker Binance (0.05%)
        total_commission = (entry_price + exit_price) * trade.position_size * 0.0005

        # Fetch actual funding history from Binance if execution engine available
        funding_fee = 0.0
        if self.execution_engine:
            try:
                opened_ms = int(trade.opened_at.timestamp() * 1000) if trade.opened_at else None
                funding_income = await self.execution_engine.exchange.fetch_funding_history(
                    symbol=trade.symbol,
                    since=opened_ms
                )
                for item in funding_income:
                    funding_fee += abs(float(item.get('amount') or 0.0))
            except Exception as err:
                logger.debug(f"[Trade #{trade.id}] Funding fee fetch note: {err}")

        net_pnl = gross_pnl - total_commission - funding_fee
        
        # Durasi
        opened_at = trade.opened_at or trade.created_at or closed_at
        duration = int((closed_at - opened_at).total_seconds())
        
        # ROI & Risk-Reward (RR)
        margin_used = (entry_price * trade.position_size) / trade.leverage
        roi = (net_pnl / margin_used) * 100 if margin_used > 0 else 0.0
        
        stop_dist = abs(entry_price - trade.sl_price)
        rr = (abs(exit_price - entry_price) / stop_dist) if stop_dist > 0 else 0.0
        
        win = 1 if net_pnl > 0 else 0

        await self.trade_repo.save_summary(
            trade_id=trade.id,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            commission=total_commission,
            funding=funding_fee,
            roi=roi,
            rr=rr,
            win=win,
            duration_seconds=duration,
            close_reason=close_reason,
            closed_at=closed_at
        )
        logger.info(f"[Trade #{trade.id}] Summary Saved! Net PNL: ${net_pnl:.2f} | Funding: ${funding_fee:.4f} | Win: {win} | Reason: {close_reason}")