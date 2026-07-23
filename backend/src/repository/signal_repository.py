from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import TradingSignal
from src.services.signal_parser import ParsedSignal


class SignalRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_signal_from_parsed(
        self, 
        parsed: ParsedSignal, 
        telegram_message_id: Optional[int] = None, 
        source: str = "TELEGRAM"
    ) -> TradingSignal:
        """Menyimpan hasil parsing sinyal ke tabel trading_signals."""
        
        # Tentukan status konfirmasi berdasarkan kebutuhan
        conf_status = "NOT_REQUIRED"
        if parsed.confidence and parsed.confidence < 0.70:
            conf_status = "PENDING"

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
        """Mengambil data sinyal berdasarkan Primary Key ID."""
        stmt = select(TradingSignal).where(TradingSignal.id == signal_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_confirmation_status(self, signal_id: int, status: str) -> None:
        """Update status konfirmasi user (APPROVED / REJECTED)."""
        stmt = (
            update(TradingSignal)
            .where(TradingSignal.id == signal_id)
            .values(confirmation_status=status)
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def update_signal_status(self, signal_id: int, status: str) -> None:
        """Update status siklus sinyal (EXECUTED / REJECTED / CANCELLED / EXPIRED)."""
        stmt = (
            update(TradingSignal)
            .where(TradingSignal.id == signal_id)
            .values(status=status)
        )
        await self.session.execute(stmt)
        await self.session.commit()
    
    async def is_duplicate_active_signal(self, symbol: str, side: str) -> bool:
        """Mencegah duplicate trade pada pair & side yang sama jika sinyal masih aktif."""
        stmt = select(TradingSignal).where(
            TradingSignal.symbol == symbol,
            TradingSignal.side == side,
            TradingSignal.status.in_(["RECEIVED", "EXECUTED"])
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None