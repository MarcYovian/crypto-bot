"""Unit tests for SimulateRiskUseCase."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.application.dto.risk_commands import SimulateRiskCommand
from src.application.use_cases.risk.simulate_risk_use_case import SimulateRiskUseCase
from src.domain.ports.repositories import (
    IDailyRiskRepository,
    IInstrumentRepository,
    IRiskProfileRepository,
)


@pytest.mark.asyncio
async def test_simulate_risk_use_case():
    instrument_repo = MagicMock(spec=IInstrumentRepository)
    risk_profile_repo = MagicMock(spec=IRiskProfileRepository)
    daily_risk_repo = MagicMock(spec=IDailyRiskRepository)

    mock_inst = MagicMock(
        id=1,
        symbol="BTCUSDT",
        tick_size=Decimal("0.1"),
        step_size=Decimal("0.001"),
        min_notional=Decimal("5.0"),
        price_precision=2,
        qty_precision=3,
    )
    instrument_repo.get_by_symbol = AsyncMock(return_value=mock_inst)
    risk_profile_repo.get_or_create_default_profile = AsyncMock(return_value=MagicMock(risk_percent=Decimal("2.0")))

    use_case = SimulateRiskUseCase(
        instrument_repo=instrument_repo,
        risk_profile_repo=risk_profile_repo,
        daily_risk_repo=daily_risk_repo,
    )

    cmd = SimulateRiskCommand(
        symbol="BTCUSDT",
        side="BUY",
        entry_price=Decimal("65000.0"),
        sl_price=Decimal("63000.0"),
        tp_targets=[Decimal("67000.0"), Decimal("70000.0")],
        leverage=10,
        custom_balance=Decimal("10000.0"),
    )

    res = await use_case.execute(cmd)

    assert res["symbol"] == "BTCUSDT"
    assert res["side"] == "BUY"
    assert res["is_valid"] is True
    assert res["risk_amount"] == 200.0  # 2.0% of 10000
    assert len(res["tp_allocations"]) == 2
    assert len(res["risk_reward_ratios"]) == 2
