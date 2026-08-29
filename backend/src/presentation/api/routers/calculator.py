"""API Router for Interactive Live Risk & Position Sizing Simulator Sandbox."""

import logging
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status

from src.infrastructure.persistence.models.users import User
from src.presentation.api.schemas.risk import (
    RiskSimulationRequest,
    RiskSimulationResponse,
)
from src.application.dto.risk_commands import SimulateRiskCommand
from src.application.use_cases.risk import SimulateRiskUseCase
from src.domain.exceptions.risk import (
    ZeroStopDistanceError,
    InvalidSignalGeometryError,
    RiskCalculationError,
)
from src.presentation.api.deps import (
    get_current_user,
    get_simulate_risk_use_case,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/calculator", tags=["Risk Calculator"])


@router.post(
    "/simulate",
    response_model=RiskSimulationResponse,
    summary="Live Risk & Position Sizing Simulator Sandbox",
    description=(
        "Calculates exact lot size, required margin, liquidation price, and confirms strict 2.0% loss cap at Stop Loss."
    ),
)
async def simulate_risk(
    payload: RiskSimulationRequest,
    current_user: User = Depends(get_current_user),
    use_case: SimulateRiskUseCase = Depends(get_simulate_risk_use_case),
) -> RiskSimulationResponse:
    """Execute live position sizing, margin requirement, and liquidation price simulation."""
    try:
        cmd = SimulateRiskCommand(
            symbol=payload.symbol,
            side=payload.side,
            entry_price=Decimal(str(payload.entry_price)),
            sl_price=Decimal(str(payload.sl_price)),
            tp_targets=[],
            leverage=payload.requested_leverage,
            custom_balance=Decimal(str(payload.wallet_balance)),
            risk_percent=Decimal(str(payload.risk_percent)),
        )
        res = await use_case.execute(cmd)
        return RiskSimulationResponse(**res)
    except (ZeroStopDistanceError, InvalidSignalGeometryError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except RiskCalculationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error during risk simulation for {payload.symbol}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error calculating position simulation: {e}",
        )

