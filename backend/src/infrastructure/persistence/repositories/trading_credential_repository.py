"""Data-access repository for the TradingCredential entity."""

from datetime import datetime
from typing import Optional, Union, Dict, Any
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.persistence.models import TradingCredential
from src.presentation.api.schemas.master import TradingCredentialCreate, TradingCredentialUpdate
from src.infrastructure.persistence.repositories.base import BaseRepository
from src.domain.ports.repositories import ITradingCredentialRepository
from src.utils.security import encrypt_secret, decrypt_secret


class TradingCredentialRepository(
    BaseRepository[TradingCredential, TradingCredentialCreate, TradingCredentialUpdate],
    ITradingCredentialRepository,
):
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

        enc_api = data.pop("encrypted_api_key", None) or (encrypt_secret(raw_api_key) if raw_api_key else "")
        enc_sec = data.pop("encrypted_secret_key", None) or (encrypt_secret(raw_secret_key) if raw_secret_key else "")
        enc_pass = data.pop("encrypted_passphrase", None) or (encrypt_secret(raw_passphrase) if raw_passphrase else None)

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
            raw_key = data.pop("api_key")
            db_obj.encrypted_api_key = str(encrypt_secret(raw_key)) if raw_key else ""
        if "encrypted_api_key" in data:
            val = data.pop("encrypted_api_key")
            db_obj.encrypted_api_key = str(val or "")

        if "secret_key" in data:
            raw_sec = data.pop("secret_key")
            db_obj.encrypted_secret_key = str(encrypt_secret(raw_sec)) if raw_sec else ""
        if "encrypted_secret_key" in data:
            val = data.pop("encrypted_secret_key")
            db_obj.encrypted_secret_key = str(val or "")

        if "passphrase" in data:
            raw_pass = data.pop("passphrase")
            db_obj.encrypted_passphrase = str(encrypt_secret(raw_pass)) if raw_pass else None
        if "encrypted_passphrase" in data:
            val = data.pop("encrypted_passphrase")
            db_obj.encrypted_passphrase = str(val) if val is not None else None

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

    async def get_by_account_id(self, account_id: int) -> Optional[TradingCredential]:
        """Fetch active credential by account_id."""
        return await self.get_active_credential(account_id)

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

    async def save_credential(self, credential: Any) -> Any:
        """Save or persist credential entity."""
        if hasattr(credential, "id") and credential.id:
            return await self.update(credential, credential)
        return await self.create(credential)

