"""Place Bracket Orders Use Case for Stop-Loss and Multi-Take-Profit order placement."""

import logging
import time
from decimal import Decimal
from typing import Any, List, Optional

from src.application.dto.trade_commands import BracketOrdersResultDTO, PlaceBracketOrdersCommand
from src.domain.exceptions import ExchangeAuthError, TradeExecutionError
from src.domain.ports.gateways import IExchangeGateway
from src.domain.ports.repositories import IOrderRepository, ITradeRepository

from src.domain.services.risk_calculator import RiskCalculatorDomainService
from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.trade_status import OrderType
from src.presentation.api.schemas.order import OrderCreate
from src.presentation.api.schemas.trade import TradeStatusUpdate

logger = logging.getLogger(__name__)


class PlaceBracketOrdersUseCase:
    """Orchestrates placement and persistence of Stop Loss and Multi-Take-Profit bracket orders."""

    def __init__(
        self,
        order_repo: IOrderRepository,
        exchange_gateway: Optional[IExchangeGateway] = None,
        trade_repo: Optional[ITradeRepository] = None,
        risk_calculator: Optional[RiskCalculatorDomainService] = None,
    ) -> None:
        self.order_repo = order_repo
        self.exchange_gateway = exchange_gateway
        self.trade_repo = trade_repo
        self.risk_calc = risk_calculator or RiskCalculatorDomainService()

    async def execute(self, cmd: PlaceBracketOrdersCommand) -> BracketOrdersResultDTO:
        """Place SL and TP bracket orders on the exchange and save records to the database."""
        if not cmd.auto_tp_sl:
            return BracketOrdersResultDTO(trade_id=cmd.trade_id, success=True)

        raw_side = cmd.side.value if isinstance(cmd.side, OrderSide) else str(cmd.side)
        is_long = raw_side.upper() in ("BUY", "LONG")
        opposite_side = "SELL" if is_long else "BUY"

        sl_order_id: Optional[str] = None
        tp_order_ids: List[str] = []

        # -----------------------------------------------------------------
        # 1. Stop Loss Order Placement
        # -----------------------------------------------------------------
        if cmd.sl_price and cmd.sl_price > Decimal("0"):
            client_sl_id = f"SL_{cmd.trade_id}_{int(time.time() * 1000)}"
            exch_sl_id: Optional[str] = None

            if self.exchange_gateway:
                try:
                    if hasattr(self.exchange_gateway, "create_stop_loss_order"):
                        sl_resp = await self.exchange_gateway.create_stop_loss_order(
                            symbol=cmd.symbol,
                            side=opposite_side,
                            stop_price=cmd.sl_price,
                            qty=cmd.position_size,
                            client_order_id=client_sl_id,
                        )
                    else:
                        sl_resp = await self.exchange_gateway.create_order(
                            symbol=cmd.symbol,
                            side=OrderSide(opposite_side),
                            order_type=OrderType.STOP_MARKET,
                            qty=cmd.position_size,
                            price=cmd.sl_price,
                            client_order_id=client_sl_id,
                            stop_price=cmd.sl_price,
                        )

                    exch_sl_id = str(
                        (sl_resp.get("exchange_order_id") if isinstance(sl_resp, dict) else None)
                        or (sl_resp.get("order_id") if isinstance(sl_resp, dict) else None)
                        or (sl_resp.get("id") if isinstance(sl_resp, dict) else None)
                        or f"SIM_SL_{cmd.trade_id}"
                    )

                    sl_order_id = exch_sl_id

                except ExchangeAuthError as exc:
                    if "apiKey" in str(exc).lower() or "binanceusdm" in str(exc).lower():
                        logger.warning("Exchange unauthenticated in SL placement, proceeding in simulated mode.")
                        exch_sl_id = f"SIM_SL_{cmd.trade_id}"
                        sl_order_id = exch_sl_id
                    else:
                        raise exc
                except Exception as exc:
                    logger.error("Failed to place exchange SL order: %s", exc)
                    if cmd.is_emergency_close_on_sl_fail and self.exchange_gateway:
                        try:
                            if hasattr(self.exchange_gateway, "create_entry_order"):
                                await self.exchange_gateway.create_entry_order(
                                    symbol=cmd.symbol,
                                    side=opposite_side,
                                    order_type="MARKET",
                                    qty=cmd.position_size,
                                    reduce_only=True,
                                )
                            else:
                                await self.exchange_gateway.create_order(
                                    symbol=cmd.symbol,
                                    side=OrderSide(opposite_side),
                                    order_type=OrderType.MARKET,
                                    qty=cmd.position_size,
                                    params={"reduceOnly": True},
                                )
                        except Exception as e_panic:
                            logger.error("Emergency panic close failed: %s", e_panic)



                        if self.trade_repo:
                            await self.trade_repo.update_trade_status(
                                trade_id=cmd.trade_id,
                                schema=TradeStatusUpdate(status="CLOSED"),
                            )
                        raise TradeExecutionError(
                            f"Failed to place SL order: {exc}. Position was emergency-closed."
                        ) from exc

            await self.order_repo.create(
                OrderCreate(
                    trade_id=cmd.trade_id,
                    exchange_order_id=exch_sl_id,
                    client_order_id=client_sl_id,
                    order_type="STOP_MARKET",
                    purpose="SL",
                    side=opposite_side,
                    price=cmd.sl_price,
                    qty=cmd.position_size,
                    status="NEW",
                )
            )

        # -----------------------------------------------------------------
        # 2. Take Profit Orders Placement
        # -----------------------------------------------------------------
        tp_targets: List[Decimal] = []
        if cmd.tp_targets:
            tp_targets = [Decimal(str(tp)) for tp in cmd.tp_targets if tp and Decimal(str(tp)) > Decimal("0")]
        else:
            for candidate in (cmd.tp1_price, cmd.tp2_price, cmd.tp3_price):
                if candidate and Decimal(str(candidate)) > Decimal("0"):
                    tp_targets.append(Decimal(str(candidate)))

        if tp_targets:
            allocations = self.risk_calc.calculate_tp_allocations(cmd.position_size, tp_targets)
            for idx, alloc in enumerate(allocations, start=1):
                tp_target = (
                    alloc[0]
                    if isinstance(alloc, (list, tuple))
                    else getattr(alloc, "price", getattr(alloc, "target_price", alloc))
                )
                tp_qty = (
                    alloc[1]
                    if isinstance(alloc, (list, tuple))
                    else getattr(alloc, "quantity", getattr(alloc, "allocated_qty", Decimal("0")))
                )
                purpose_name = f"TP{idx}"
                client_tp_id = f"TP_{cmd.trade_id}_{idx}_{int(time.time() * 1000)}"

                exch_tp_id: Optional[str] = None
                if self.exchange_gateway:
                    try:
                        if hasattr(self.exchange_gateway, "create_take_profit_order"):
                            tp_resp = await self.exchange_gateway.create_take_profit_order(
                                symbol=cmd.symbol,
                                side=opposite_side,
                                tp_price=tp_target,
                                qty=tp_qty,
                                client_order_id=client_tp_id,
                            )
                        else:
                            tp_resp = await self.exchange_gateway.create_order(
                                symbol=cmd.symbol,
                                side=OrderSide(opposite_side),
                                order_type=OrderType.TAKE_PROFIT_MARKET,
                                qty=tp_qty,
                                price=tp_target,
                                client_order_id=client_tp_id,
                                stop_price=tp_target,
                            )

                        exch_tp_id = str(
                            (tp_resp.get("exchange_order_id") if isinstance(tp_resp, dict) else None)
                            or (tp_resp.get("order_id") if isinstance(tp_resp, dict) else None)
                            or (tp_resp.get("id") if isinstance(tp_resp, dict) else None)
                            or f"SIM_TP_{cmd.trade_id}_{idx}"
                        )

                        if exch_tp_id:
                            tp_order_ids.append(exch_tp_id)

                    except ExchangeAuthError as exc:
                        if "apiKey" in str(exc).lower() or "binanceusdm" in str(exc).lower():
                            logger.warning("Exchange unauthenticated in TP placement, proceeding in simulated mode.")
                            exch_tp_id = f"SIM_TP_{cmd.trade_id}_{idx}"
                            tp_order_ids.append(exch_tp_id)
                        else:
                            raise exc
                    except Exception as exc:
                        logger.warning("Failed to place exchange %s order: %s", purpose_name, exc)

                await self.order_repo.create(
                    OrderCreate(
                        trade_id=cmd.trade_id,
                        exchange_order_id=exch_tp_id,
                        client_order_id=client_tp_id,
                        order_type="TAKE_PROFIT_MARKET",
                        purpose=purpose_name,
                        side=opposite_side,
                        price=tp_target,
                        qty=tp_qty,
                        status="NEW",
                    )
                )

        return BracketOrdersResultDTO(
            trade_id=cmd.trade_id,
            sl_order_id=sl_order_id,
            tp_order_ids=tp_order_ids,
            success=True,
        )
