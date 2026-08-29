"""Use case for listing active trading instruments with leverage brackets."""

from typing import List, Optional

from src.domain.ports.repositories import IInstrumentRepository, IExchangeRepository
from src.presentation.api.schemas.master import InstrumentDTO, LeverageBracketDTO, ExchangeCreate


class ListInstrumentsUseCase:
    """Use case to fetch all active trading instruments with leverage brackets."""

    def __init__(
        self,
        instrument_repo: IInstrumentRepository,
        exchange_repo: Optional[IExchangeRepository] = None,
    ) -> None:
        self.instrument_repo = instrument_repo
        self.exchange_repo = exchange_repo

    async def _ensure_exchange_id(self, exchange_id: Optional[int] = None) -> int:
        if exchange_id is not None:
            return exchange_id
        if self.exchange_repo:
            exchange = await self.exchange_repo.get_by_code("BINANCE")
            if not exchange:
                exchange = await self.exchange_repo.create(
                    ExchangeCreate(code="BINANCE", name="Binance Futures", status=True)
                )
            if exchange:
                return exchange.id
        return 1

    async def execute(self, exchange_id: Optional[int] = None) -> List[InstrumentDTO]:
        """Fetch all active instruments with leverage brackets mapped to InstrumentDTOs."""
        resolved_ex_id = await self._ensure_exchange_id(exchange_id)
        instruments = await self.instrument_repo.get_all_instruments_with_brackets(resolved_ex_id)

        result: List[InstrumentDTO] = []
        for inst in instruments:
            max_lev = 125
            brackets_dto: List[LeverageBracketDTO] = []
            if inst.leverage_brackets:
                max_lev = max(b.initial_leverage for b in inst.leverage_brackets)
                for b in inst.leverage_brackets:
                    brackets_dto.append(
                        LeverageBracketDTO(
                            bracket=b.bracket,
                            initial_leverage=b.initial_leverage,
                            notional_cap=float(b.notional_cap),
                            notional_floor=float(b.notional_floor),
                            maint_margin_ratio=float(b.maint_margin_ratio),
                            cum=float(b.cum),
                        )
                    )

            result.append(
                InstrumentDTO(
                    symbol=inst.symbol,
                    base_asset=inst.base_asset,
                    quote_asset=inst.quote_asset,
                    price_precision=inst.price_precision,
                    qty_precision=inst.qty_precision,
                    tick_size=float(inst.tick_size),
                    step_size=float(inst.step_size),
                    min_notional=float(inst.min_notional),
                    max_leverage=max_lev,
                    brackets=brackets_dto if brackets_dto else None,
                )
            )

        return result
