"""Generic Abstract Base Repository for SQLAlchemy 2.0 Async."""

from typing import Generic, TypeVar, Type, Optional, List, Union, Dict, Any
from pydantic import BaseModel
from sqlalchemy import select, func, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.connection import Base

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """Generic CRUD data-access repository using AsyncSession."""

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """Initialize with SQLAlchemy model class and active AsyncSession.
        
        Args:
            model: SQLAlchemy ORM class.
            session: Active SQLAlchemy AsyncSession.
        """
        self.model = model
        self.session = session

    async def get(self, id: Any) -> Optional[ModelType]:
        """Fetch a single record by its primary key.
        
        Args:
            id: Primary key value.
            
        Returns:
            The model instance if found, otherwise None.
        """
        stmt = select(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_multi(
        self, skip: int = 0, limit: int = 100
    ) -> List[ModelType]:
        """Fetch multiple records with offset and limit pagination.
        
        Args:
            skip: Number of records to skip.
            limit: Maximum number of records to return.
            
        Returns:
            List of model instances.
        """
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self, schema: Union[CreateSchemaType, Dict[str, Any]]
    ) -> ModelType:
        """Create and persist a new record in the database.
        
        Args:
            schema: Pydantic schema or dictionary containing column values.
            
        Returns:
            The newly created and refreshed model instance.
        """
        if isinstance(schema, BaseModel):
            data = schema.model_dump()
        else:
            data = schema.copy()

        db_obj = self.model(**data)
        self.session.add(db_obj)
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj

    async def update(
        self, db_obj: ModelType, schema: Union[UpdateSchemaType, Dict[str, Any]]
    ) -> ModelType:
        """Update fields of an existing model instance and commit changes.
        
        Args:
            db_obj: Existing SQLAlchemy model instance to update.
            schema: Pydantic schema or dictionary containing modified fields.
            
        Returns:
            The updated and refreshed model instance.
        """
        if isinstance(schema, BaseModel):
            update_data = schema.model_dump(exclude_unset=True)
        else:
            update_data = schema

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        self.session.add(db_obj)
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj

    async def delete(self, id: Any) -> bool:
        """Delete a record by primary key.
        
        Args:
            id: Primary key value.
            
        Returns:
            True if the record was found and deleted, False otherwise.
        """
        db_obj = await self.get(id)
        if not db_obj:
            return False

        await self.session.delete(db_obj)
        await self.session.commit()
        return True

    async def count(self) -> int:
        """Count total rows in the corresponding table.
        
        Returns:
            Total row count integer.
        """
        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0
