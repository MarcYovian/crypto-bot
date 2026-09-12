"""Use case for updating strategy TP percentage allocations and trailing/BEP trigger rules."""

import json
import logging
from src.domain.exceptions.provider import StrategyNotFoundError, InvalidStrategyConfigError
from src.domain.ports.repositories import IStrategyRepository
from src.presentation.api.schemas.master import StrategyDTO, StrategyUpdateRequest, TPAllocationDTO
from src.application.use_cases.strategies.list_strategies_use_case import ListStrategiesUseCase

logger = logging.getLogger(__name__)


class UpdateStrategyUseCase:
    """Use case to update strategy TP percentage allocations and trailing/BEP trigger rules."""

    def __init__(self, strategy_repo: IStrategyRepository) -> None:
        self.strategy_repo = strategy_repo

    async def execute(self, strategy_id: int, payload: StrategyUpdateRequest) -> StrategyDTO:
        """Update strategy TP percentage allocations and trailing/BEP trigger rules."""
        strategy = await self.strategy_repo.get(strategy_id)
        if not strategy:
            raise StrategyNotFoundError(f"Strategy with ID {strategy_id} not found.")

        current_tps, current_bep, current_trailing = ListStrategiesUseCase.parse_strategy_config(strategy.description)
        tp1 = payload.tp1_percent if payload.tp1_percent is not None else current_tps[0].percentage
        tp2 = payload.tp2_percent if payload.tp2_percent is not None else current_tps[1].percentage
        tp3 = payload.tp3_percent if payload.tp3_percent is not None else current_tps[2].percentage

        total_sum = round(tp1 + tp2 + tp3, 2)
        if total_sum != 100.0:
            raise InvalidStrategyConfigError(
                f"Total TP allocations must sum up to 100.0%, got {total_sum}% ({tp1}% + {tp2}% + {tp3}%)."
            )

        bep = payload.bep_trigger_level if payload.bep_trigger_level is not None else current_bep
        trailing = payload.trailing_trigger_level if payload.trailing_trigger_level is not None else current_trailing

        cfg = {
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "bep": bep,
            "trailing": trailing,
        }
        strategy.description = json.dumps(cfg)
        if hasattr(self.strategy_repo, "session") and self.strategy_repo.session:
            self.strategy_repo.session.add(strategy)
            await self.strategy_repo.session.flush()

        logger.info(f"Strategy {strategy.name} (ID: {strategy_id}) updated with new TP rules: {cfg}")

        return StrategyDTO(
            id=strategy.id,
            name=strategy.name,
            tp_allocations=[
                TPAllocationDTO(tp_level=1, percentage=tp1),
                TPAllocationDTO(tp_level=2, percentage=tp2),
                TPAllocationDTO(tp_level=3, percentage=tp3),
            ],
            bep_trigger_level=bep,
            trailing_trigger_level=trailing,
            is_active=strategy.is_active,
        )
