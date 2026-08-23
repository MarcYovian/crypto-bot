"""Data-access repository for Instrument Leverage and Notional Brackets."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Union, Dict, Any
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import InstrumentLeverageBracket
from src.schemas.master import InstrumentLeverageBracketCreate, InstrumentLeverageBracketUpdate
from src.repository.base import BaseRepository


class InstrumentLeverageBracketRepository(
    BaseRepository[InstrumentLeverageBracket, InstrumentLeverageBracketCreate, InstrumentLeverageBracketUpdate]
):
    """CRUD repository for the ``instrument_leverage_brackets`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(InstrumentLeverageBracket, session)

    async def get_brackets_by_instrument(
        self, instrument_id: int
    ) -> List[InstrumentLeverageBracket]:
        """Fetch all leverage brackets for an instrument ordered by tier level.

        Args:
            instrument_id: FK to instruments table.

        Returns:
            List of InstrumentLeverageBracket models sorted by bracket ascending.
        """
        stmt = (
            select(InstrumentLeverageBracket)
            .where(InstrumentLeverageBracket.instrument_id == instrument_id)
            .order_by(InstrumentLeverageBracket.bracket.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_bracket_for_notional(
        self, instrument_id: int, notional_value: Decimal
    ) -> Optional[InstrumentLeverageBracket]:
        """Find the matching leverage bracket for a specific trade position notional value.

        Args:
            instrument_id: FK to instruments table.
            notional_value: Position value in USDT (Quantity * Entry Price).

        Returns:
            Matching InstrumentLeverageBracket or the highest bracket tier if beyond max cap.
        """
        stmt = (
            select(InstrumentLeverageBracket)
            .where(
                InstrumentLeverageBracket.instrument_id == instrument_id,
                InstrumentLeverageBracket.notional_floor <= notional_value,
                InstrumentLeverageBracket.notional_cap >= notional_value,
            )
            .order_by(InstrumentLeverageBracket.bracket.asc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        bracket = result.scalar_one_or_none()

        # If notional exceeds the highest cap, fallback to the most conservative (last) bracket
        if not bracket:
            fallback_stmt = (
                select(InstrumentLeverageBracket)
                .where(InstrumentLeverageBracket.instrument_id == instrument_id)
                .order_by(InstrumentLeverageBracket.bracket.desc())
                .limit(1)
            )
            res = await self.session.execute(fallback_stmt)
            bracket = res.scalar_one_or_none()

        return bracket

    async def get_max_leverage_for_symbol(self, instrument_id: int) -> int:
        """Fetch the absolute maximum allowable leverage for an instrument (Bracket 1).

        Args:
            instrument_id: FK to instruments table.

        Returns:
            Max leverage integer (e.g. 50, 75, 125). Defaults to 20 if unseeded.
        """
        stmt = select(func.max(InstrumentLeverageBracket.initial_leverage)).where(
            InstrumentLeverageBracket.instrument_id == instrument_id
        )
        result = await self.session.execute(stmt)
        val = result.scalar_one_or_none()
        return int(val) if val is not None else 20

    async def bulk_upsert_brackets(
        self,
        instrument_id: int,
        brackets: List[Union[InstrumentLeverageBracketCreate, Dict[str, Any]]],
    ) -> int:
        """Insert or update leverage brackets for a specific instrument.

        Args:
            instrument_id: FK to instruments table.
            brackets: List of schemas or raw dictionaries with bracket data.

        Returns:
            Number of upserted bracket records.
        """
        existing_brackets = await self.get_brackets_by_instrument(instrument_id)
        existing_map = {b.bracket: b for b in existing_brackets}

        count = 0
        for item in brackets:
            raw_data = item.model_dump() if isinstance(item, InstrumentLeverageBracketCreate) else item.copy()
            data = {
                "instrument_id": instrument_id,
                "bracket": int(raw_data.get("bracket", 1)),
                "initial_leverage": int(raw_data.get("initial_leverage") or raw_data.get("initialLeverage", 20)),
                "notional_cap": Decimal(str(raw_data.get("notional_cap") or raw_data.get("notionalCap", 50000))),
                "notional_floor": Decimal(str(raw_data.get("notional_floor") or raw_data.get("notionalFloor", 0))),
                "maint_margin_ratio": Decimal(str(raw_data.get("maint_margin_ratio") or raw_data.get("maintMarginRatio", 0.01))),
                "cum": Decimal(str(raw_data.get("cum", 0))),
            }
            bracket_num = data["bracket"]

            if bracket_num in existing_map:
                existing = existing_map[bracket_num]
                for k, v in data.items():
                    setattr(existing, k, v)
                existing.updated_at = datetime.now()
                self.session.add(existing)
            else:
                new_bracket = InstrumentLeverageBracket(**data)
                self.session.add(new_bracket)
            count += 1

        await self.session.commit()
        return count

    async def delete_brackets_by_instrument(self, instrument_id: int) -> int:
        """Delete all leverage brackets associated with an instrument.

        Args:
            instrument_id: FK to instruments table.

        Returns:
            Number of deleted records.
        """
        stmt = delete(InstrumentLeverageBracket).where(
            InstrumentLeverageBracket.instrument_id == instrument_id
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount
