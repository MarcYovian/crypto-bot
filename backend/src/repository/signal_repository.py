"""Data-access layer for the ``trading_signals`` table."""

from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import TradingSignal
from src.services.signal_parser import ParsedSignal


class SignalRepository:
    """CRUD operations for trading signals."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_signal_from_parsed(
        self,
        parsed: ParsedSignal,
        telegram_message_id: Optional[int] = None,
        source: str = "TELEGRAM"
    ) -> TradingSignal:
        """Persist a parsed signal to the ``trading_signals`` table.

        Low-confidence signals (< 70 %) are created with a ``PENDING``
        confirmation status so the user can approve or reject them manually.

        Args:
            parsed: The parsed signal dataclass.
            telegram_message_id: Original Telegram message ID for dedup.
            source: Signal source identifier.

        Returns:
            The newly created ``TradingSignal`` ORM instance.
        """
        conf_status = "PENDING" if (parsed.confidence and parsed.confidence < 0.70) else "NOT_REQUIRED"

        signal = TradingSignal(
            telegram_message_id=telegram_message_id,
            source=source,
            symbol=parsed.symbol,
            side=parsed.side,
            entry_min=parsed.entry_min,
            entry_max=parsed.entry_max,
            sl_price=parsed.sl_price,
            tp1_price=parsed.tp_prices[0] if len(parsed.tp_prices) > 0 else None,
            tp2_price=parsed.tp_prices[1] if len(parsed.tp_prices) > 1 else None,
            tp3_price=parsed.tp_prices[2] if len(parsed.tp_prices) > 2 else None,
            confidence=parsed.confidence,
            status="RECEIVED" if parsed.is_valid else "REJECTED",
            confirmation_status=conf_status
        )

        self.session.add(signal)
        await self.session.commit()
        await self.session.refresh(signal)
        return signal

    async def get_by_id(self, signal_id: int) -> Optional[TradingSignal]:
        """Fetch a signal by its primary key."""
        stmt = select(TradingSignal).where(TradingSignal.id == signal_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_confirmation_status(self, signal_id: int, status: str) -> None:
        """Set the user-confirmation status (``APPROVED`` / ``REJECTED``)."""
        stmt = (
            update(TradingSignal)
            .where(TradingSignal.id == signal_id)
            .values(confirmation_status=status)
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def update_signal_status(self, signal_id: int, status: str) -> None:
        """Advance the signal lifecycle status.

        Typical transitions: ``RECEIVED`` → ``EXECUTED`` / ``REJECTED`` /
        ``CANCELLED`` / ``EXPIRED``.
        """
        stmt = (
            update(TradingSignal)
            .where(TradingSignal.id == signal_id)
            .values(status=status)
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def is_duplicate_active_signal(self, symbol: str, side: str) -> bool:
        """Return ``True`` if an active signal already exists for this pair and side.

        An active signal is one with status ``RECEIVED`` or ``EXECUTED``.
        """
        stmt = select(TradingSignal).where(
            TradingSignal.symbol == symbol,
            TradingSignal.side == side,
            TradingSignal.status.in_(["RECEIVED", "EXECUTED"])
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None