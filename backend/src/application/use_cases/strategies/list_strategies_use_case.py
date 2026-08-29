"""Use case for listing all trading strategies and their configured TP stage rules."""

import json
from typing import List, Tuple
from src.domain.ports.repositories import IStrategyRepository
from src.presentation.api.schemas.master import StrategyDTO, TPAllocationDTO


class ListStrategiesUseCase:
    """Use case to fetch all trading strategies with their configured TP stage rules."""

    def __init__(self, strategy_repo: IStrategyRepository) -> None:
        self.strategy_repo = strategy_repo

    @staticmethod
    def parse_strategy_config(description: str | None) -> Tuple[List[TPAllocationDTO], int, int]:
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

    async def execute(self) -> List[StrategyDTO]:
        """Fetch all trading strategies with their configured TP stage rules."""
        strategies = await self.strategy_repo.get_all_strategies()
        result: List[StrategyDTO] = []
        for s in strategies:
            tps, bep, trailing = self.parse_strategy_config(s.description)
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
