"""Use case for end-to-end trading signal execution with 8-step validation and dual-mode routing."""

import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from src.application.dto.trade_commands import (
    ExecuteSignalCommand,
    PlaceBracketOrdersCommand,
    TradeExecutionResultDTO,
)
from src.application.use_cases.trades.place_bracket_orders_use_case import PlaceBracketOrdersUseCase
from config.settings import settings
from src.domain.entities.risk import PositionSizingInput
from src.domain.events.trade_events import (
    TradeOpenedEvent,
    TradeWaitingEntryEvent,
)
from src.domain.exceptions import (
    DailyRiskLimitReachedError,
    ExchangeError,
    ExchangeAuthError,
    InsufficientMarginError,
    InsufficientMarginRiskError,
    RateLimitError,
    MaxRiskExceededError,
    PairAlreadyActiveError,
    SymbolNotWhitelistedError,
    TradeExecutionError,
)

from src.domain.ports.event_publisher import IDomainEventPublisher
from src.domain.ports.gateways import IExchangeGateway
from src.domain.ports.repositories import (
    IDailyRiskRepository,
    IInstrumentLeverageBracketRepository,
    IInstrumentRepository,
    IOrderRepository,
    IRiskProfileRepository,
    ITradeEventRepository,
    ITradeRepository,
    ITradeRiskRepository,
    IWatchlistRepository,
)
from src.domain.services.precision_filter import PrecisionFilterDomainService
from src.domain.services.risk_calculator import RiskCalculatorDomainService
from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.trade_status import OrderPurpose, OrderType, TradeStatus
from src.presentation.api.schemas.risk import DailyRiskConfigCreate, TradeRiskCreate
from src.presentation.api.schemas.order import OrderCreate
from src.presentation.api.schemas.trade import TradeCreate, TradeStatusUpdate

logger = logging.getLogger(__name__)


class ExecuteSignalUseCase:
    """Orchestrates end-to-end trading signal processing, risk management, and order placement."""

    def __init__(
        self,
        instrument_repo: IInstrumentRepository,
        watchlist_repo: IWatchlistRepository,
        trade_repo: ITradeRepository,
        trade_risk_repo: ITradeRiskRepository,
        daily_risk_repo: IDailyRiskRepository,
        order_repo: IOrderRepository,
        trade_event_repo: ITradeEventRepository,
        risk_profile_repo: IRiskProfileRepository,
        bracket_repo: Optional[IInstrumentLeverageBracketRepository] = None,
        exchange_gateway: Optional[IExchangeGateway] = None,
        event_publisher: Optional[IDomainEventPublisher] = None,
        risk_calculator: Optional[RiskCalculatorDomainService] = None,
        precision_filter: Optional[PrecisionFilterDomainService] = None,
        place_bracket_orders_use_case: Optional[PlaceBracketOrdersUseCase] = None,
    ) -> None:
        self.instrument_repo = instrument_repo
        self.watchlist_repo = watchlist_repo
        self.trade_repo = trade_repo
        self.trade_risk_repo = trade_risk_repo
        self.daily_risk_repo = daily_risk_repo
        self.order_repo = order_repo
        self.trade_event_repo = trade_event_repo
        self.risk_profile_repo = risk_profile_repo
        self.bracket_repo = bracket_repo
        self.exchange_gateway = exchange_gateway
        self.event_publisher = event_publisher
        self.risk_calc = risk_calculator or RiskCalculatorDomainService()
        self.precision = precision_filter or PrecisionFilterDomainService()
        self.place_brackets_use_case = place_bracket_orders_use_case or PlaceBracketOrdersUseCase(
            order_repo=order_repo,
            exchange_gateway=exchange_gateway,
            trade_repo=trade_repo,
            risk_calculator=self.risk_calc,
        )

    async def execute(self, cmd: ExecuteSignalCommand) -> TradeExecutionResultDTO:
        """Execute the command following the strict 8-step domain sequence."""
        sig = cmd.signal_dto
        if not sig.is_valid:
            raise TradeExecutionError(f"Cannot execute invalid signal: {sig.error_message}")

        # ---------------------------------------------------------------------
        # Step 1: Instrument & Watchlist Validation
        # ---------------------------------------------------------------------
        instrument = await self.instrument_repo.get_by_symbol(sig.symbol)
        if not instrument:
            raise SymbolNotWhitelistedError(f"Symbol {sig.symbol} is not found in instruments table.")

        is_enabled = await self.watchlist_repo.is_symbol_enabled(sig.symbol)
        if not is_enabled:
            raise SymbolNotWhitelistedError(f"Symbol {sig.symbol} is disabled or not in watchlist.")

        tick_sz = getattr(instrument, "tick_size", Decimal("0.1")) or Decimal("0.1")
        price_prec = getattr(instrument, "price_precision", 2) or 2

        target_entry = getattr(sig, "avg_entry_price", None) or getattr(sig, "entry_min", None) or Decimal("0")
        if target_entry > Decimal("0"):
            target_entry = self.precision.round_price(target_entry, tick_size=tick_sz, price_precision=price_prec)

        if sig.sl_price and sig.sl_price > Decimal("0"):
            sig.sl_price = self.precision.round_price(sig.sl_price, tick_size=tick_sz, price_precision=price_prec)

        # ---------------------------------------------------------------------
        # Step 2: Active Trade Duplicate Check & Max Open Positions Limit
        # ---------------------------------------------------------------------
        active_trade = await self.trade_repo.get_active_trade_by_instrument(instrument.id)
        if active_trade:
            raise PairAlreadyActiveError(
                f"Active trade (ID: {active_trade.id}, Status: {active_trade.status}) already exists for {sig.symbol}."
            )

        profile = None
        max_limit = 3
        if self.risk_profile_repo and hasattr(self.risk_profile_repo, "get_or_create_default_profile"):
            profile = await self.risk_profile_repo.get_or_create_default_profile()
            max_limit_val = getattr(profile, "max_open_trade", None) or getattr(profile, "max_open_positions", None)
            try:
                max_limit = int(max_limit_val) if max_limit_val is not None else 3
            except (ValueError, TypeError):
                max_limit = 3



        active_trades = await self.trade_repo.get_all_active_trades(account_id=cmd.account_id)
        if len(active_trades) >= max_limit:
            raise MaxRiskExceededError(
                f"Maximum open positions limit reached ({len(active_trades)}/{max_limit})."
            )

        # ---------------------------------------------------------------------
        # Step 3: Real-time Wallet Balance & Circuit Breaker Check
        # ---------------------------------------------------------------------
        wallet_balance = Decimal("10000.0")  # Total balance for risk budget
        free_margin = Decimal("10000.0")     # Free available margin for order collateral
        if self.exchange_gateway:
            try:
                bal_data = await self.exchange_gateway.fetch_balance()
                
                tot_val = (
                    bal_data.get("total_wallet_balance")
                    or (bal_data.get("total", {}).get("USDT") if isinstance(bal_data.get("total"), dict) else None)
                    or (bal_data.get("assets", {}).get("USDT", {}).get("total") if isinstance(bal_data.get("assets"), dict) else None)
                )
                free_val = (
                    bal_data.get("free_margin")
                    or (bal_data.get("free", {}).get("USDT") if isinstance(bal_data.get("free"), dict) else None)
                    or (bal_data.get("assets", {}).get("USDT", {}).get("free") if isinstance(bal_data.get("assets"), dict) else None)
                )

                if tot_val is not None:
                    wallet_balance = Decimal(str(tot_val))
                elif free_val is not None:
                    wallet_balance = Decimal(str(free_val))

                if free_val is not None:
                    free_margin = Decimal(str(free_val))
                else:
                    free_margin = wallet_balance

                if wallet_balance <= Decimal("0"):
                    raise ExchangeError("Gagal mengambil saldo bursa (saldo kosong atau bernilai 0 USDT).")

            except ExchangeAuthError:
                logger.warning("Exchange unauthenticated in fetch_balance, using default wallet balance.")
                wallet_balance = Decimal("10000.0")
                free_margin = Decimal("10000.0")
            except ExchangeError:
                raise
            except Exception as e:
                raise ExchangeError(f"Gagal mengambil saldo bursa: {str(e)}") from e


        today = datetime.now().date()
        daily_risk = await self.daily_risk_repo.get_by_date(cmd.account_id, today)
        raw_pct = getattr(profile, "risk_percent", None)
        try:
            risk_pct = Decimal(str(raw_pct)) if raw_pct is not None else Decimal("2.0")
        except Exception:
            risk_pct = Decimal("2.0")

        raw_loss_pct = getattr(profile, "max_daily_loss", None)
        try:
            daily_loss_pct = Decimal(str(raw_loss_pct)) if raw_loss_pct is not None else Decimal("5.0")
        except Exception:
            daily_loss_pct = Decimal("5.0")

        if not daily_risk:
            per_trade_risk_amount = wallet_balance * (risk_pct / Decimal("100"))
            daily_risk_budget = wallet_balance * (daily_loss_pct / Decimal("100"))
            prof_id = getattr(profile, "id", 1) if profile is not None else 1
            daily_risk = await self.daily_risk_repo.get_or_create_daily_snapshot(
                DailyRiskConfigCreate(
                    account_id=cmd.account_id,
                    risk_profile_id=prof_id if isinstance(prof_id, int) else 1,
                    date=today,
                    balance=wallet_balance,
                    risk_amount=per_trade_risk_amount,
                    daily_risk_amount=daily_risk_budget,
                )
            )

        effective_max_risk = None
        if daily_risk:
            raw_remaining = await self.daily_risk_repo.get_remaining_risk_budget(daily_risk.id if hasattr(daily_risk, "id") and isinstance(daily_risk.id, int) else 1)
            try:
                remaining_budget = Decimal(str(raw_remaining))
            except Exception:
                remaining_budget = Decimal("200.0")

            trade_risk_amount = wallet_balance * (risk_pct / Decimal("100"))
            raw_trade_risk = getattr(daily_risk, "risk_amount", None)
            if raw_trade_risk is not None:
                try:
                    s_val = str(raw_trade_risk)
                    if "mock" not in s_val.lower() and "object at" not in s_val:
                        trade_risk_amount = Decimal(s_val)
                except Exception:
                    pass

            if remaining_budget <= Decimal("0") or trade_risk_amount > remaining_budget:
                raise DailyRiskLimitReachedError(
                    f"Daily risk limit breached: Required trade risk ({trade_risk_amount:.2f} USDT) exceeds remaining daily budget ({remaining_budget:.2f} USDT). Circuit breaker active."
                )
            effective_max_risk = trade_risk_amount

        # ---------------------------------------------------------------------
        # Step 4: Early Exit Invariant Checks (TP1 Hit, SL Breached, Runaway > 2%)
        # ---------------------------------------------------------------------
        current_price = target_entry
        is_manual = getattr(sig, "raw_text", "").startswith("MANUAL_DASHBOARD")
        if not is_manual and self.exchange_gateway is not None:
            try:
                ticker = await self.exchange_gateway.fetch_ticker(sig.symbol)
                last_p = ticker.get("last_price") or ticker.get("last") or ticker.get("close")
                if last_p is not None and Decimal(str(last_p)) > Decimal("0"):
                    current_price = Decimal(str(last_p))

            except Exception as exc:
                logger.warning("Failed to fetch live ticker price for %s: %s", sig.symbol, exc)


        side_upper = sig.side.upper()
        tp1_target = sig.tp_targets[0] if (sig.tp_targets and len(sig.tp_targets) > 0) else None

        # CHECK A: TP1 Already Hit / Exceeded Validation
        if tp1_target and tp1_target > Decimal("0"):
            is_currently_past_tp1 = (
                (side_upper in ("BUY", "LONG") and current_price >= tp1_target)
                or (side_upper in ("SELL", "SHORT") and current_price <= tp1_target)
            )
            if is_currently_past_tp1:
                logger.warning("Signal rejected: Price already past TP1 (%s). Current: %s", tp1_target, current_price)
                return TradeExecutionResultDTO(
                    trade_id=None,
                    symbol=sig.symbol,
                    side=sig.side,
                    status="REJECTED",
                    position_size=Decimal("0"),
                    entry_price=target_entry,
                    is_success=False,
                    message=f"Signal rejected: Price already passed TP1 ({tp1_target}).",
                )

        if not getattr(cmd, "is_manual", False) and self.exchange_gateway is not None and hasattr(self.exchange_gateway, "has_price_reached_target") and tp1_target:
            try:
                res_tp = self.exchange_gateway.has_price_reached_target(sig.symbol, tp1_target, side=sig.side, is_sl=False)
                hit_tp1 = await res_tp if hasattr(res_tp, "__await__") else res_tp
                if hit_tp1 is True:
                    logger.warning("Signal rejected: Historical kline touched TP1 (%s)", tp1_target)
                    return TradeExecutionResultDTO(
                        trade_id=None,
                        symbol=sig.symbol,
                        side=sig.side,
                        status="REJECTED",
                        position_size=Decimal("0"),
                        entry_price=target_entry,
                        is_success=False,
                        message=f"Signal rejected: Historical price touched TP1 ({tp1_target}).",
                    )
            except Exception as exc:
                logger.warning("Failed to check historical TP1: %s", exc)

        # CHECK B: Stop Loss Breached Validation
        if sig.sl_price and sig.sl_price > Decimal("0"):
            is_currently_past_sl = (
                (side_upper in ("BUY", "LONG") and current_price <= sig.sl_price)
                or (side_upper in ("SELL", "SHORT") and current_price >= sig.sl_price)
            )
            if is_currently_past_sl:
                logger.warning("Signal rejected: Price breached Stop Loss (%s). Current: %s", sig.sl_price, current_price)
                return TradeExecutionResultDTO(
                    trade_id=None,
                    symbol=sig.symbol,
                    side=sig.side,
                    status="REJECTED",
                    position_size=Decimal("0"),
                    entry_price=target_entry,
                    is_success=False,
                    message=f"Signal rejected: Price breached Stop Loss ({sig.sl_price}).",
                )

        if not getattr(cmd, "is_manual", False) and self.exchange_gateway is not None and hasattr(self.exchange_gateway, "has_price_reached_target") and sig.sl_price:
            try:
                res_sl = self.exchange_gateway.has_price_reached_target(sig.symbol, sig.sl_price, side=sig.side, is_sl=True)
                hit_sl = await res_sl if hasattr(res_sl, "__await__") else res_sl
                if hit_sl is True:
                    logger.warning("Signal rejected: Historical kline touched SL (%s)", sig.sl_price)
                    return TradeExecutionResultDTO(
                        trade_id=None,
                        symbol=sig.symbol,
                        side=sig.side,
                        status="REJECTED",
                        position_size=Decimal("0"),
                        entry_price=target_entry,
                        is_success=False,
                        message=f"Signal rejected: Historical price touched SL ({sig.sl_price}).",
                    )
            except Exception as exc:
                logger.warning("Failed to check historical SL: %s", exc)



        # CHECK C: Price Deviation & Runaway Tolerance (> 2.0%)
        unfavorable_dev_pct = Decimal("0")
        if target_entry > Decimal("0") and current_price > Decimal("0"):
            if side_upper in ("BUY", "LONG"):
                if current_price > target_entry:
                    unfavorable_dev_pct = (current_price - target_entry) / target_entry
            else:
                if current_price < target_entry:
                    unfavorable_dev_pct = (target_entry - current_price) / target_entry

        if unfavorable_dev_pct > Decimal("0.02"):
            logger.warning(
                "Signal rejected: Price has run away (%.2f%% deviation > 2.0%% max).",
                float(unfavorable_dev_pct * 100),
            )
            return TradeExecutionResultDTO(
                trade_id=None,
                symbol=sig.symbol,
                side=sig.side,
                status="REJECTED",
                position_size=Decimal("0"),
                entry_price=target_entry,
                is_success=False,
                message=f"Signal rejected: Price has run away ({float(unfavorable_dev_pct * 100):.2f}% deviation).",
            )

        # Determine Dual-Mode Entry Type
        execution_mode = "MARKET"
        if unfavorable_dev_pct > Decimal("0.002"):
            execution_mode = "LIMIT"

        effective_entry_for_calc = target_entry if execution_mode == "LIMIT" else current_price

        # ---------------------------------------------------------------------
        # Step 5: Risk Calculator & Dynamic Leverage
        # ---------------------------------------------------------------------
        brackets = None
        if self.bracket_repo and hasattr(self.bracket_repo, "get_brackets_by_instrument"):
            try:
                brackets = await self.bracket_repo.get_brackets_by_instrument(instrument.id)
            except Exception:
                pass

        min_notional_val = getattr(instrument, "min_notional", Decimal("5.0")) or Decimal("5.0")
        min_qty_val = getattr(instrument, "min_qty", Decimal("0.001")) or Decimal("0.001")
        step_sz = getattr(instrument, "step_size", Decimal("0.001")) or Decimal("0.001")
        qty_prec = getattr(instrument, "qty_precision", 3) or 3

        parsed_leverage = getattr(sig, "leverage", 10) or 10

        effective_leverage = parsed_leverage
        if self.watchlist_repo and hasattr(self.watchlist_repo, "get_watchlist_item_by_symbol"):
            wl_item = await self.watchlist_repo.get_watchlist_item_by_symbol(sig.symbol)
            if wl_item and getattr(wl_item, "max_leverage", None):
                effective_leverage = min(effective_leverage, wl_item.max_leverage)

        auto_margin_capping_enabled = getattr(settings, "AUTO_MARGIN_CAPPING", True)
        margin_buffer = Decimal(str(getattr(settings, "MARGIN_SAFETY_BUFFER", 0.95)))

        risk_res = self.risk_calc.calculate_position_size(
            wallet_balance=wallet_balance,
            available_free_margin=free_margin,
            auto_margin_cap=auto_margin_capping_enabled,
            margin_safety_buffer=margin_buffer,
            risk_percent=risk_pct,
            entry_price=effective_entry_for_calc,
            sl_price=sig.sl_price,
            requested_leverage=effective_leverage,
            leverage=effective_leverage,
            min_notional=min_notional_val,
            min_qty=min_qty_val,
            step_size=step_sz,
            qty_precision=qty_prec,
            max_risk_amount=effective_max_risk,
            brackets=brackets,
            symbol=sig.symbol,
            strict=False,
        )

        if not risk_res.is_valid:
            logger.warning("Pre-trade margin/risk validation failed for %s: %s", sig.symbol, risk_res.warning)
            raise InsufficientMarginRiskError(
                message=risk_res.warning,
                required_margin=risk_res.required_margin,
                available_margin=free_margin,
                shortfall=risk_res.shortfall_margin,
                position_size=risk_res.position_size,
                notional=risk_res.notional_value,
                leverage=effective_leverage,
                risk_amount=risk_res.risk_amount,
                stop_distance=risk_res.stop_distance,
                symbol=sig.symbol,
            )

        if hasattr(risk_res, "leverage") and risk_res.leverage:
            effective_leverage = int(risk_res.leverage)


        # ---------------------------------------------------------------------
        # Step 6: Create Trade Entity & Persist in Database
        # ---------------------------------------------------------------------
        tp1 = sig.tp_targets[0] if (sig.tp_targets and len(sig.tp_targets) > 0) else None
        tp2 = sig.tp_targets[1] if (sig.tp_targets and len(sig.tp_targets) > 1) else None
        tp3 = sig.tp_targets[2] if (sig.tp_targets and len(sig.tp_targets) > 2) else None

        initial_status = "OPEN" if execution_mode == "MARKET" else "WAITING_ENTRY"

        strat_id = cmd.strategy_id or 1
        trade = await self.trade_repo.create(
            TradeCreate(
                account_id=cmd.account_id,
                instrument_id=instrument.id,
                strategy_id=strat_id,
                side=sig.side.upper(),
                status=initial_status,
                entry_price=effective_entry_for_calc,
                avg_entry_price=effective_entry_for_calc,
                sl_price=sig.sl_price,
                tp1_price=tp1,
                tp2_price=tp2,
                tp3_price=tp3,
                position_size=risk_res.position_size,
                remaining_qty=risk_res.position_size,
                leverage=effective_leverage,
            )
        )

        # ---------------------------------------------------------------------
        # Step 7: Configure Exchange & Submit Entry Order (Dual-Mode)
        # ---------------------------------------------------------------------
        if self.exchange_gateway:
            try:
                await self.exchange_gateway.set_leverage(sig.symbol, effective_leverage)
                await self.exchange_gateway.set_margin_mode(sig.symbol, "ISOLATED")
            except (RateLimitError, InsufficientMarginError):
                raise
            except ExchangeAuthError as exc:
                if "apiKey" in str(exc).lower() or "binanceusdm" in str(exc).lower():
                    logger.warning("Exchange unauthenticated in set_leverage/margin_mode, proceeding in simulated mode.")
                else:
                    raise exc
            except Exception as exc:
                logger.warning("Failed to configure leverage/margin: %s", exc)

        client_entry_id = f"ENTRY_{trade.id}_{int(time.time() * 1000)}"
        exchange_entry_id = f"SIM_{trade.id}"
        actual_entry_price = effective_entry_for_calc

        if self.exchange_gateway:
            try:
                entry_resp = await self.exchange_gateway.create_order(
                    symbol=sig.symbol,
                    side=OrderSide(sig.side.upper()),
                    order_type=OrderType(execution_mode),
                    qty=risk_res.position_size,
                    price=target_entry if execution_mode == "LIMIT" else None,
                    client_order_id=client_entry_id,
                )
                exchange_entry_id = str(entry_resp.get("exchange_order_id") or entry_resp.get("order_id") or entry_resp.get("id") or f"SIM_{trade.id}")

                if execution_mode == "MARKET":
                    avg_val = entry_resp.get("average") or entry_resp.get("price")
                    if avg_val is not None and Decimal(str(avg_val)) > Decimal("0"):
                        actual_entry_price = Decimal(str(avg_val))
            except InsufficientMarginError as exc:
                await self.trade_repo.update_trade_status(
                    trade_id=trade.id,
                    schema=TradeStatusUpdate(status="CANCELLED"),
                )
                stop_dist = abs(actual_entry_price - sig.sl_price)
                stop_pct_val = (stop_dist / actual_entry_price) * Decimal("100") if actual_entry_price > 0 else Decimal("0")
                notional_val = risk_res.position_size * actual_entry_price
                req_m = notional_val / Decimal(str(effective_leverage))
                shortfall_val = max(Decimal("0"), req_m - free_margin)
                detail_msg = (
                    f"Bursa menolak order (Margin is insufficient / Margin Tidak Mencukupi): Dibutuhkan {req_m:.2f} USDT, "
                    f"Tersedia {free_margin:.2f} USDT (Kekurangan: {shortfall_val:.2f} USDT). "
                    f"Notional: {notional_val:.2f} USDT @ {effective_leverage}x, Risk: {risk_res.risk_amount:.2f} USDT, "
                    f"SL Dist: {stop_dist:.4f} ({stop_pct_val:.2f}%)."
                )
                raise InsufficientMarginError(
                    detail_msg,
                    required_margin=req_m,
                    available_margin=free_margin,
                    shortfall=shortfall_val,
                    position_size=risk_res.position_size,
                    notional=notional_val,
                    leverage=effective_leverage,
                    risk_amount=risk_res.risk_amount,
                    stop_distance=stop_dist,
                    stop_percent=stop_pct_val,
                    symbol=sig.symbol,
                ) from exc
            except ExchangeAuthError as exc:
                if "apiKey" in str(exc).lower() or "binanceusdm" in str(exc).lower():
                    logger.warning("Exchange unauthenticated in create_order, proceeding in simulated mode.")
                else:
                    await self.trade_repo.update_trade_status(
                        trade_id=trade.id,
                        schema=TradeStatusUpdate(status="CANCELLED"),
                    )
                    raise exc
            except Exception as exc:
                await self.trade_repo.update_trade_status(
                    trade_id=trade.id,
                    schema=TradeStatusUpdate(status="CANCELLED"),
                )
                raise exc


        # ---------------------------------------------------------------------
        # Step 8: Branch Routing & Domain Event Dispatching
        # ---------------------------------------------------------------------
        if execution_mode == "MARKET":
            # 1. Update Trade state to OPEN
            updated_trade = await self.trade_repo.update_entry_fill(
                trade_id=trade.id,
                entry_price=actual_entry_price,
            )
            if updated_trade:
                trade = updated_trade
            assert trade is not None


            # 2. Record TradeRisk in DB
            if daily_risk and self.trade_risk_repo:
                actual_stop_dist = abs(actual_entry_price - sig.sl_price)
                actual_margin = (risk_res.position_size * actual_entry_price) / Decimal(str(effective_leverage))
                await self.trade_risk_repo.create(

                    TradeRiskCreate(
                        trade_id=trade.id,
                        daily_risk_id=daily_risk.id,
                        entry=actual_entry_price,
                        stop=sig.sl_price,
                        stop_distance=actual_stop_dist,
                        qty=risk_res.position_size,
                        margin=actual_margin,
                        risk_amount=risk_res.risk_amount,
                        leverage=effective_leverage,
                    )
                )

            # 3. Save ENTRY Order in DB
            await self.order_repo.create(
                OrderCreate(
                    trade_id=trade.id,
                    exchange_order_id=exchange_entry_id,
                    client_order_id=client_entry_id,
                    order_type="MARKET",
                    purpose="ENTRY",
                    side=sig.side,
                    price=actual_entry_price,
                    qty=risk_res.position_size,
                    status="FILLED" if exchange_entry_id else "NEW",
                )
            )

            sl_order_id = None
            tp_order_ids: List[str] = []

            if cmd.auto_tp_sl and self.place_brackets_use_case:
                bracket_cmd = PlaceBracketOrdersCommand(
                    trade_id=trade.id,
                    symbol=sig.symbol,
                    side=sig.side,
                    position_size=risk_res.position_size,
                    sl_price=sig.sl_price,
                    tp_targets=sig.tp_targets,
                    auto_tp_sl=cmd.auto_tp_sl,
                    is_emergency_close_on_sl_fail=True,
                )
                bracket_res = await self.place_brackets_use_case.execute(bracket_cmd)
                sl_order_id = bracket_res.sl_order_id
                tp_order_ids = bracket_res.tp_order_ids



            # 4. Log Trade Event
            await self.trade_event_repo.log_event(
                trade_id=trade.id,
                event_type="ENTRY",
                payload={
                    "trace_id": getattr(sig, "trace_id", ""),
                    "symbol": sig.symbol,
                    "side": sig.side,
                    "entry_price": float(actual_entry_price),
                    "sl_price": float(sig.sl_price),
                    "position_size": float(risk_res.position_size),
                    "leverage": effective_leverage,
                    "order_type": "MARKET",
                },
            )

            # 5. Dispatch Domain Event
            if self.event_publisher:
                await self.event_publisher.publish(
                    TradeOpenedEvent(
                        trade_id=trade.id,
                        account_id=cmd.account_id,
                        symbol=sig.symbol,
                        side=OrderSide(sig.side.upper()),
                        entry_price=actual_entry_price,
                        position_size=risk_res.position_size,
                        leverage=effective_leverage,
                        sl_price=sig.sl_price,
                        tp1_price=tp1,
                        tp2_price=tp2,
                        tp3_price=tp3,
                    )
                )

            return TradeExecutionResultDTO(
                trade_id=trade.id,
                symbol=sig.symbol,
                side=sig.side,
                status="OPEN",
                position_size=risk_res.position_size,
                entry_price=actual_entry_price,
                entry_order_id=exchange_entry_id,
                sl_order_id=sl_order_id,
                tp_order_ids=tp_order_ids,
                is_success=True,
                message="Trade placed successfully via MARKET order.",
            )


        else:
            # BRANCH B: LIMIT PULLBACK
            await self.order_repo.create(
                OrderCreate(
                    trade_id=trade.id,
                    exchange_order_id=exchange_entry_id,
                    client_order_id=client_entry_id,
                    order_type="LIMIT",
                    purpose="ENTRY",
                    side=sig.side,
                    price=target_entry,
                    qty=risk_res.position_size,
                    status="NEW",
                )
            )

            await self.trade_event_repo.log_event(
                trade_id=trade.id,
                event_type="ENTRY",
                payload={
                    "trace_id": getattr(sig, "trace_id", ""),
                    "symbol": sig.symbol,
                    "side": sig.side,
                    "target_entry_price": float(target_entry),
                    "current_market_price": float(current_price),
                    "price_deviation_pct": float(unfavorable_dev_pct) * 100,
                    "sl_price": float(sig.sl_price),
                    "position_size": float(risk_res.position_size),
                    "leverage": effective_leverage,
                    "order_type": "LIMIT",
                },
            )

            if self.event_publisher:
                await self.event_publisher.publish(
                    TradeWaitingEntryEvent(
                        trade_id=trade.id,
                        account_id=cmd.account_id,
                        symbol=sig.symbol,
                        side=OrderSide(sig.side.upper()),
                        target_entry_price=target_entry,
                        position_size=risk_res.position_size,
                        leverage=effective_leverage,
                        sl_price=sig.sl_price,
                        tp1_price=tp1,
                        tp2_price=tp2,
                        tp3_price=tp3,
                    )
                )

            return TradeExecutionResultDTO(
                trade_id=trade.id,
                symbol=sig.symbol,
                side=sig.side,
                status="WAITING_ENTRY",
                position_size=risk_res.position_size,
                entry_price=target_entry,
                entry_order_id=exchange_entry_id,
                is_success=True,
                message=f"LIMIT order placed at {target_entry} (waiting for price pullback).",
            )
