"""Strategy business service for managing TP allocation distributions and trailing rules."""

import json
import logging
from typing import List

from src.schemas.master import (
    StrategyDTO,
    StrategyUpdateRequest,
    TPAllocationDTO,
)
from src.repository.strategy_repository import StrategyRepository
from src.domain.exceptions.provider import (
    StrategyNotFoundError,
    InvalidStrategyConfigError,
)

logger = logging.getLogger(__name__)


class StrategyService:
    """Service providing configuration management for Take Profit stage scaling and protection rules."""

    def __init__(self, strategy_repo: StrategyRepository) -> None:
        self.strategy_repo = strategy_repo

    def _parse_strategy_config(self, description: str | None) -> tuple[List[TPAllocationDTO], int, int]:
        """Parse TP allocations and trigger levels from JSON description with safe defaults."""
        default_tps = [
            TPAllocationDTO(tp_level=1, percentage=50.0),
            TPAllocationDTO(tp_level=2, percentage=30.0),
            TPAllocationDTO(tp_level=3, percentage=20.0),
        ]
        default_bep = 1
        default_trailing = 2

        if not description:
            return default_tps, default_bep, default_trailing

        try:
            cfg = json.loads(description)
            tp1 = float(cfg.get("tp1", 50.0))
            tp2 = float(cfg.get("tp2", 30.0))
            tp3 = float(cfg.get("tp3", 20.0))
            bep = int(cfg.get("bep", 1))
            trailing = int(cfg.get("trailing", 2))

            tps = [
                TPAllocationDTO(tp_level=1, percentage=tp1),
                TPAllocationDTO(tp_level=2, percentage=tp2),
                TPAllocationDTO(tp_level=3, percentage=tp3),
            ]
            return tps, bep, trailing
        except Exception:
            return default_tps, default_bep, default_trailing

    async def list_strategies(self) -> List[StrategyDTO]:
        """Fetch all trading strategies with their configured TP stage rules.

        Returns:
            List of StrategyDTO objects.
        """
        strategies = await self.strategy_repo.get_all_strategies()
        result: List[StrategyDTO] = []
        for s in strategies:
            tps, bep, trailing = self._parse_strategy_config(s.description)
            result.append(
                StrategyDTO(
                    id=s.id,
                    name=s.name,
                    tp_allocations=tps,
                    bep_trigger_level=bep,
                    trailing_trigger_level=trailing,
                    is_active=s.is_active,
                )
            )
        return result

    async def update_strategy(self, strategy_id: int, payload: StrategyUpdateRequest) -> StrategyDTO:
        """Update strategy TP percentage allocations and trailing/BEP trigger rules.

        Args:
            strategy_id: Primary key of the strategy.
            payload: Updated TP allocation values.

        Returns:
            Updated StrategyDTO.

        Raises:
            StrategyNotFoundError: If strategy ID does not exist.
            InvalidStrategyConfigError: If sum of TP percentages is not equal to 100%.
        """
        strategy = await self.strategy_repo.get(strategy_id)
        if not strategy:
            raise StrategyNotFoundError(f"Strategy with ID {strategy_id} not found.")

        current_tps, current_bep, current_trailing = self._parse_strategy_config(strategy.description)
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
