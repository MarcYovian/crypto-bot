"""Data-access repository for dynamic Bot Settings and configuration."""

import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.persistence.models import BotSetting
from src.presentation.api.schemas.system import BotSettingCreate, BotSettingUpdate
from src.infrastructure.persistence.repositories.base import BaseRepository
from src.domain.ports.repositories import IBotSettingRepository


class BotSettingRepository(BaseRepository[BotSetting, BotSettingCreate, BotSettingUpdate], IBotSettingRepository):
    """CRUD repository for the ``bot_settings`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(BotSetting, session)

    async def get_by_key(self, key: str) -> Optional[BotSetting]:
        """Fetch setting record by its unique key (case-insensitive).
        
        Args:
            key: Setting key name.
            
        Returns:
            BotSetting instance or None.
        """
        stmt = select(BotSetting).where(
            func.upper(BotSetting.key) == key.strip().upper()
        ).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Fetch raw string value of a setting, with default fallback.
        
        Args:
            key: Setting key name.
            default: Fallback string value if key is not set.
            
        Returns:
            Value string or default.
        """
        setting = await self.get_by_key(key)
        return setting.value if setting is not None else default

    async def get_bool(self, key: str, default: bool = False) -> bool:
        """Fetch boolean value of a setting.
        
        Args:
            key: Setting key name.
            default: Fallback boolean value.
            
        Returns:
            Boolean True if value is 'true', '1', 'yes', 'on'; False otherwise.
        """
        val = await self.get_value(key)
        if val is None:
            return default
        return val.strip().lower() in ("true", "1", "yes", "on")

    async def get_int(self, key: str, default: int = 0) -> int:
        """Fetch integer value of a setting.
        
        Args:
            key: Setting key name.
            default: Fallback integer value.
            
        Returns:
            Parsed integer value.
        """
        val = await self.get_value(key)
        if val is None:
            return default
        try:
            return int(val.strip())
        except (ValueError, TypeError):
            return default

    async def get_float(self, key: str, default: float = 0.0) -> float:
        """Fetch float value of a setting.
        
        Args:
            key: Setting key name.
            default: Fallback float value.
            
        Returns:
            Parsed float value.
        """
        val = await self.get_value(key)
        if val is None:
            return default
        try:
            return float(val.strip())
        except (ValueError, TypeError):
            return default

    async def get_json(self, key: str, default: Optional[Any] = None) -> Optional[Any]:
        """Fetch and deserialize JSON value of a setting.
        
        Args:
            key: Setting key name.
            default: Fallback object.
            
        Returns:
            Deserialized Python object or default.
        """
        val = await self.get_value(key)
        if val is None:
            return default
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default

    async def set_value(
        self,
        key: str,
        value: str,
        category: str = "GENERAL",
        setting_type: str = "STRING",
        description: Optional[str] = None,
    ) -> BotSetting:
        """Upsert a setting value (insert if new, update if existing).
        
        Args:
            key: Setting key name.
            value: Setting value string.
            category: Setting group category ("GENERAL", "TRADING", "RISK", "TELEGRAM", "SYSTEM").
            setting_type: Data type enum ("STRING", "INTEGER", "FLOAT", "BOOLEAN", "JSON").
            description: Optional description.
            
        Returns:
            The created or updated BotSetting instance.
        """
        norm_key = key.strip().upper()
        setting = await self.get_by_key(norm_key)

        if setting:
            setting.value = str(value)
            setting.category = category.strip().upper()
            setting.type = setting_type.strip().upper()
            if description is not None:
                setting.description = description
            setting.updated_at = datetime.now()
            self.session.add(setting)
        else:
            setting = BotSetting(
                key=norm_key,
                value=str(value),
                category=category.strip().upper(),
                type=setting_type.strip().upper(),
                description=description,
            )
            self.session.add(setting)

        await self.session.commit()
        await self.session.refresh(setting)
        return setting

    async def get_all_by_category(self, category: str) -> List[BotSetting]:
        """Fetch all settings within a specific category.
        
        Args:
            category: Category group name.
            
        Returns:
            List of BotSetting instances ordered by key ASC.
        """
        stmt = (
            select(BotSetting)
            .where(func.upper(BotSetting.category) == category.strip().upper())
            .order_by(BotSetting.key.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_as_dict(self) -> Dict[str, str]:
        """Fetch all settings as a key-value dictionary for caching.
        
        Returns:
            Dictionary mapping setting keys to string values.
        """
        stmt = select(BotSetting)
        result = await self.session.execute(stmt)
        settings = result.scalars().all()
        return {s.key: s.value for s in settings}
