"""Data-access repository for the TradingCredential entity."""

from datetime import datetime
from typing import Optional, Union, Dict, Any
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import TradingCredential
from src.schemas.master import TradingCredentialCreate, TradingCredentialUpdate
from src.repository.base import BaseRepository


class TradingCredentialRepository(BaseRepository[TradingCredential, TradingCredentialCreate, TradingCredentialUpdate]):
    """CRUD repository for the ``trading_credentials`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(TradingCredential, session)

    async def create(self, schema: Union[TradingCredentialCreate, Dict[str, Any]]) -> TradingCredential:
        """Insert a new credential mapping plain/pre-encrypted keys to ORM columns."""
        if hasattr(schema, "model_dump"):
            data = schema.model_dump(exclude_unset=True)
        else:
            data = schema.copy()

        raw_api_key = data.pop("api_key", None)
        raw_secret_key = data.pop("secret_key", None)
        raw_passphrase = data.pop("passphrase", None)

        enc_api = data.pop("encrypted_api_key", None) or raw_api_key or ""
        enc_sec = data.pop("encrypted_secret_key", None) or raw_secret_key or ""
        enc_pass = data.pop("encrypted_passphrase", None) or raw_passphrase

        db_obj = TradingCredential(
            account_id=data.get("account_id"),
            key_name=data.get("key_name", "Default Key"),
            encrypted_api_key=enc_api,
            encrypted_secret_key=enc_sec,
            encrypted_passphrase=enc_pass,
            key_version=data.get("key_version", 1),
            is_active=data.get("is_active", True),
        )
        self.session.add(db_obj)
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj

    async def update(self, db_obj: TradingCredential, schema: Union[TradingCredentialUpdate, Dict[str, Any]]) -> TradingCredential:
        """Update existing credential mapping plain/pre-encrypted keys to ORM columns."""
        if hasattr(schema, "model_dump"):
            data = schema.model_dump(exclude_unset=True)
        else:
            data = schema.copy()

        if "api_key" in data:
            db_obj.encrypted_api_key = data.pop("api_key")
        if "encrypted_api_key" in data:
            db_obj.encrypted_api_key = data.pop("encrypted_api_key")

        if "secret_key" in data:
            db_obj.encrypted_secret_key = data.pop("secret_key")
        if "encrypted_secret_key" in data:
            db_obj.encrypted_secret_key = data.pop("encrypted_secret_key")

        if "passphrase" in data:
            db_obj.encrypted_passphrase = data.pop("passphrase")
        if "encrypted_passphrase" in data:
            db_obj.encrypted_passphrase = data.pop("encrypted_passphrase")

        for key, value in data.items():
            setattr(db_obj, key, value)

        db_obj.updated_at = datetime.now()
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj

    async def get_active_credential(self, account_id: int) -> Optional[TradingCredential]:
        """Fetch the active API credential for a trading account.
        
        Args:
            account_id: FK to trading_accounts table.
            
        Returns:
            The active TradingCredential instance, or None.
        """
        stmt = (
            select(TradingCredential)
            .where(
                TradingCredential.account_id == account_id,
                TradingCredential.is_active.is_(True)
            )
            .order_by(TradingCredential.key_version.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def deactivate_old_credentials(self, account_id: int) -> int:
        """Deactivate all active credentials for an account during key rotation.
        
        Args:
            account_id: FK to trading_accounts table.
            
        Returns:
            Number of rows updated.
        """
        stmt = (
            update(TradingCredential)
            .where(
                TradingCredential.account_id == account_id,
                TradingCredential.is_active.is_(True)
            )
            .values(is_active=False, updated_at=datetime.now())
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return int(getattr(result, "rowcount", 0) or 0)
