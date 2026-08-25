"""API Router for Interactive Live Risk & Position Sizing Simulator Sandbox."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status

from src.database.models.users import User
from src.schemas.risk import (
    RiskSimulationRequest,
    RiskSimulationResponse,
)
from src.services.risk_calculator import RiskCalculatorService
from src.domain.exceptions.risk import (
    ZeroStopDistanceError,
    InvalidSignalGeometryError,
    RiskCalculationError,
)
from src.api.deps import (
    get_current_user,
    get_risk_calculator_service,
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
    risk_calc_service: RiskCalculatorService = Depends(get_risk_calculator_service),
) -> RiskSimulationResponse:
    """Execute live position sizing, margin requirement, and liquidation price simulation."""
    try:
        return await risk_calc_service.simulate_risk_position(payload)
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
