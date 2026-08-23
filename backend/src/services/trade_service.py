"""Trade orchestration and execution service."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Any, Dict

logger = logging.getLogger(__name__)
from src.domain.entities.signal import ParsedSignalDTO
from src.domain.entities.trade import TradeExecutionResultDTO
from src.domain.exceptions.trade import (
    TradeExecutionError,
    TradeNotFoundError,
    PairAlreadyActiveError,
    SymbolNotWhitelistedError,
    DailyRiskLimitReachedError,
)
from src.domain.exceptions.risk import MaxRiskExceededError
from src.schemas.trade import TradeCreate
from src.schemas.risk import TradeRiskCreate
from src.schemas.order import OrderCreate
from src.repository.instrument_repository import InstrumentRepository
from src.repository.instrument_leverage_bracket_repository import InstrumentLeverageBracketRepository
from src.repository.watchlist_repository import WatchlistRepository
from src.repository.risk_profile_repository import RiskProfileRepository
from src.repository.trade_repository import TradeRepository
from src.repository.trade_risk_repository import TradeRiskRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.order_repository import OrderRepository
from src.repository.trade_event_repository import TradeEventRepository
from src.services.risk_calculator import RiskCalculatorService
from src.services.precision_filter import PrecisionFilterService
from src.clients.binance_client import BinanceRestClient
from src.clients.telegram_client import TelegramNotifierClient


class TradeService:
    """Core orchestrator for validating signals, computing risk, and submitting Binance orders."""

    def __init__(
        self,
        instrument_repo: InstrumentRepository,
        watchlist_repo: WatchlistRepository,
        trade_repo: TradeRepository,
        trade_risk_repo: TradeRiskRepository,
        daily_risk_repo: DailyRiskRepository,
        order_repo: OrderRepository,
        trade_event_repo: TradeEventRepository,
        bracket_repo: Optional[InstrumentLeverageBracketRepository] = None,
        risk_profile_repo: Optional[RiskProfileRepository] = None,
        risk_calculator: Optional[RiskCalculatorService] = None,
        binance_client: Optional[BinanceRestClient] = None,
        telegram_client: Optional[TelegramNotifierClient] = None,
    ) -> None:
        self.instrument_repo = instrument_repo
        self.watchlist_repo = watchlist_repo
        self.trade_repo = trade_repo
        self.trade_risk_repo = trade_risk_repo
        self.daily_risk_repo = daily_risk_repo
        self.order_repo = order_repo
        self.trade_event_repo = trade_event_repo
        self.bracket_repo = bracket_repo
        self.risk_profile_repo = risk_profile_repo
        self.risk_calc = risk_calculator or RiskCalculatorService()
        self.binance_client = binance_client
        self.telegram_client = telegram_client

    async def execute_signal(
        self,
        signal_dto: ParsedSignalDTO,
        account_id: int = 1,
        signal_id: Optional[int] = None,
        strategy_id: Optional[int] = None,
        auto_tp_sl: bool = True,
    ) -> TradeExecutionResultDTO:
        """Process and execute an approved trading signal end-to-end.
        
        Args:
            signal_dto: Validated signal data transfer object.
            account_id: Trading account FK.
            signal_id: Optional signal record FK.
            strategy_id: Optional strategy configuration FK.
            auto_tp_sl: Whether to submit TP and SL orders immediately on entry.
            
        Returns:
            TradeExecutionResultDTO with execution details.
        """
        if not signal_dto.is_valid:
            raise TradeExecutionError(f"Cannot execute invalid signal: {signal_dto.error_message}")

        # Step 1: Instrument & Watchlist Validation
        instrument = await self.instrument_repo.get_by_symbol(signal_dto.symbol)
        if not instrument:
            raise SymbolNotWhitelistedError(f"Symbol {signal_dto.symbol} is not found in instruments table.")

        is_enabled = await self.watchlist_repo.is_symbol_enabled(signal_dto.symbol)
        if not is_enabled:
            raise SymbolNotWhitelistedError(f"Symbol {signal_dto.symbol} is disabled or not in watchlist.")

        # Step 2: Active Trade Duplicate Check
        active_trade = await self.trade_repo.get_active_trade_by_instrument(instrument.id)
        if active_trade:
            raise PairAlreadyActiveError(
                f"Active trade (ID: {active_trade.id}, Status: {active_trade.status}) already exists for {signal_dto.symbol}."
            )

        # Step 2b: Max Open Positions Limit Check
        if self.risk_profile_repo:
            profile = await self.risk_profile_repo.get_active_profile()
            max_limit = getattr(profile, "max_open_trade", None) or getattr(profile, "max_open_positions", None)
            if profile and max_limit:
                active_trades = await self.trade_repo.get_all_active_trades(account_id=account_id)
                if len(active_trades) >= max_limit:
                    raise MaxRiskExceededError(
                        f"Maximum open positions limit reached ({len(active_trades)}/{max_limit})."
                    )

        # Step 3: Daily Risk Circuit Breaker Check
        daily_risk = await self.daily_risk_repo.get_latest_snapshot(account_id=account_id)
        if daily_risk:
            remaining_budget = await self.daily_risk_repo.get_remaining_risk_budget(daily_risk.id)
            if remaining_budget <= Decimal("0"):
                raise DailyRiskLimitReachedError(
                    f"Daily risk limit breached (Remaining budget: {remaining_budget} USDT). Circuit breaker active."
                )

        # Step 4: Real-time Wallet Balance
        wallet_balance = Decimal("10000.0")  # Default fallback
        if self.binance_client:
            try:
                bal_data = await self.binance_client.fetch_balance()
                wallet_balance = bal_data.get("free_margin") or bal_data.get("total_wallet_balance") or Decimal("10000.0")
            except Exception:
                pass

        # Step 5: Risk & Dynamic Leverage Calculation
        brackets = None
        if self.bracket_repo:
            try:
                brackets = await self.bracket_repo.get_brackets_by_instrument(instrument.id)
            except Exception:
                pass

        req_leverage = signal_dto.leverage or 20
        risk_res = self.risk_calc.calculate_position_size(
            wallet_balance=wallet_balance,
            risk_percent=Decimal("2.0"),
            entry_price=signal_dto.avg_entry_price,
            sl_price=signal_dto.sl_price,
            leverage=req_leverage,
            tp_targets=signal_dto.tp_targets,
            tick_size=instrument.tick_size,
            step_size=instrument.step_size,
            price_precision=instrument.price_precision,
            qty_precision=instrument.qty_precision,
            min_notional=instrument.min_notional,
            brackets=brackets,
        )

        if not risk_res.is_valid:
            raise TradeExecutionError(f"Risk calculation rejected: {risk_res.warning}")

        effective_leverage = risk_res.leverage

        # Step 6: Leverage & Margin Mode on Binance
        if self.binance_client:
            await self.binance_client.set_leverage(signal_dto.symbol, effective_leverage)
            await self.binance_client.set_margin_mode(signal_dto.symbol, "ISOLATED")

        # Step 7: Create Trade & TradeRisk in Database
        trade = await self.trade_repo.create(
            TradeCreate(
                account_id=account_id,
                instrument_id=instrument.id,
                signal_id=signal_id,
                strategy_id=strategy_id,
                side=signal_dto.side,
                status="WAITING_ENTRY",
                entry_price=signal_dto.avg_entry_price,
                sl_price=signal_dto.sl_price,
                position_size=risk_res.position_size,
                remaining_qty=risk_res.position_size,
                leverage=effective_leverage,
            )
        )

        if daily_risk:
            await self.trade_risk_repo.create(
                TradeRiskCreate(
                    trade_id=trade.id,
                    daily_risk_id=daily_risk.id,
                    entry=signal_dto.avg_entry_price,
                    stop=signal_dto.sl_price,
                    stop_distance=risk_res.stop_distance,
                    qty=risk_res.position_size,
                    margin=risk_res.required_margin,
                    risk_amount=risk_res.risk_amount,
                    leverage=effective_leverage,
                )
            )

        # Step 8: Submit Entry Order to Binance & Save Order
        import time
        client_entry_id = f"ENTRY_{trade.id}_{int(time.time() * 1000)}"
        exchange_entry_id = None

        if self.binance_client:
            entry_resp = await self.binance_client.create_entry_order(
                symbol=signal_dto.symbol,
                side=signal_dto.side,
                order_type="MARKET",
                qty=risk_res.position_size,
                price=signal_dto.avg_entry_price,
                client_order_id=client_entry_id,
            )
            exchange_entry_id = entry_resp.get("id") or str(entry_resp.get("orderId", ""))

        await self.order_repo.create(
            OrderCreate(
                trade_id=trade.id,
                exchange_order_id=exchange_entry_id,
                client_order_id=client_entry_id,
                order_type="MARKET",
                purpose="ENTRY",
                side=signal_dto.side,
                price=signal_dto.avg_entry_price,
                qty=risk_res.position_size,
                status="FILLED" if exchange_entry_id else "NEW",
            )
        )

        # Step 9: Submit SL and TP orders
        sl_order_id = None
        tp_order_ids: List[str] = []

        if auto_tp_sl:
            opposite_side = "SELL" if signal_dto.side.upper() == "BUY" else "BUY"

            # Stop Loss Order
            client_sl_id = f"SL_{trade.id}_{int(time.time() * 1000)}"
            if self.binance_client:
                sl_resp = await self.binance_client.create_stop_loss_order(
                    symbol=signal_dto.symbol,
                    side=opposite_side,
                    stop_price=signal_dto.sl_price,
                    qty=risk_res.position_size,
                    client_order_id=client_sl_id,
                )
                sl_order_id = sl_resp.get("id") or str(sl_resp.get("orderId", ""))

            await self.order_repo.create(
                OrderCreate(
                    trade_id=trade.id,
                    exchange_order_id=sl_order_id,
                    client_order_id=client_sl_id,
                    order_type="STOP_MARKET",
                    purpose="SL",
                    side=opposite_side,
                    price=signal_dto.sl_price,
                    qty=risk_res.position_size,
                    status="NEW",
                    reduce_only=True,
                )
            )

            # Take Profit Orders
            for tp_alloc in risk_res.tp_allocations:
                client_tp_id = f"TP{tp_alloc.tp_level}_{trade.id}_{int(time.time() * 1000)}"
                exchange_tp_id = None

                if self.binance_client:
                    tp_resp = await self.binance_client.create_take_profit_order(
                        symbol=signal_dto.symbol,
                        side=opposite_side,
                        tp_price=tp_alloc.price,
                        qty=tp_alloc.quantity,
                        client_order_id=client_tp_id,
                    )
                    exchange_tp_id = tp_resp.get("id") or str(tp_resp.get("orderId", ""))
                    if exchange_tp_id:
                        tp_order_ids.append(exchange_tp_id)

                await self.order_repo.create(
                    OrderCreate(
                        trade_id=trade.id,
                        exchange_order_id=exchange_tp_id,
                        client_order_id=client_tp_id,
                        order_type="TAKE_PROFIT_MARKET",
                        purpose=f"TP{tp_alloc.tp_level}",
                        side=opposite_side,
                        price=tp_alloc.price,
                        qty=tp_alloc.quantity,
                        status="NEW",
                        reduce_only=True,
                    )
                )

        # Step 10: Log Trade Event
        event_payload = {
            "trace_id": getattr(signal_dto, "trace_id", ""),
            "symbol": signal_dto.symbol,
            "side": signal_dto.side,
            "entry_price": float(signal_dto.avg_entry_price),
            "sl_price": float(signal_dto.sl_price),
            "position_size": float(risk_res.position_size),
            "leverage": effective_leverage,
            "requested_leverage": req_leverage,
        }
        if risk_res.is_leverage_downscaled:
            event_payload["leverage_downscaled"] = True
            event_payload["leverage_reason"] = risk_res.leverage_adjustment_reason

        logger.info(f"[{getattr(signal_dto, 'trace_id', 'SIG')}] Executed Trade #{trade.id} for {signal_dto.symbol} {signal_dto.side}")

        await self.trade_event_repo.log_event(
            trade_id=trade.id,
            event_type="ENTRY",
            payload=event_payload,
        )

        # Step 11: Telegram Notification
        if self.telegram_client:
            try:
                await self.telegram_client.send_trade_opened_alert(
                    chat_id="ADMIN_CHANNEL",
                    symbol=signal_dto.symbol,
                    side=signal_dto.side,
                    entry_price=signal_dto.avg_entry_price,
                    leverage=effective_leverage,
                    position_size=risk_res.position_size,
                    margin=risk_res.required_margin,
                    sl_price=signal_dto.sl_price,
                    tp_targets=signal_dto.tp_targets,
                )
            except Exception:
                pass

        return TradeExecutionResultDTO(
            trade_id=trade.id,
            symbol=signal_dto.symbol,
            side=signal_dto.side,
            status=trade.status,
            position_size=risk_res.position_size,
            entry_price=signal_dto.avg_entry_price,
            entry_order_id=exchange_entry_id,
            sl_order_id=sl_order_id,
            tp_order_ids=tp_order_ids,
            is_success=True,
            message="Trade placed successfully.",
        )

    async def close_trade_manually(
        self,
        trade_id: int,
        reason: str = "MANUAL_CLOSE",
        close_reason: Optional[str] = None,
        position_manager: Optional[Any] = None,
    ) -> bool:
        """Manually close an open trade and cancel all pending orders."""
        eff_reason = close_reason or reason
        trade = await self.trade_repo.get(trade_id)
        if not trade:
            raise TradeNotFoundError(f"Trade with ID {trade_id} not found.", trade_id=trade_id)

        if trade.status in ("CLOSED", "CANCELLED"):
            return True

        instrument = await self.instrument_repo.get(trade.instrument_id)
        if not instrument:
            raise TradeExecutionError(f"Instrument {trade.instrument_id} not found for trade {trade_id}")

        # Cancel all open orders and send market close if binance client attached
        if self.binance_client:
            try:
                await self.binance_client.cancel_all_orders(symbol=instrument.symbol)
            except Exception:
                pass

            # Only execute market order closure if position is actually OPEN or PARTIAL
            if trade.status in ("OPEN", "PARTIAL") and trade.remaining_qty > Decimal("0"):
                close_side = "SELL" if trade.side == "BUY" else "BUY"
                try:
                    await self.binance_client.create_entry_order(
                        symbol=instrument.symbol,
                        side=close_side,
                        order_type="MARKET",
                        qty=trade.remaining_qty,
                    )
                except Exception:
                    pass

        # Finalize trade closure
        if position_manager:
            await position_manager.finalize_trade_closure(trade_id=trade_id, close_reason=eff_reason)
        else:
            await self.order_repo.cancel_all_open_orders_for_trade(trade_id)
            from src.schemas.trade import TradeStatusUpdate
            await self.trade_repo.update_trade_status(
                trade_id=trade_id,
                schema=TradeStatusUpdate(status="CLOSED", closed_at=datetime.now()),
            )

        return True
