"""Abstract generic mapper interface for converting between ORM models and Domain entities."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, List, Optional

DomainType = TypeVar("DomainType")
ORMType = TypeVar("ORMType")


class IMapper(Generic[DomainType, ORMType], ABC):
    """Abstract interface for Domain <-> ORM model mapping."""

    @classmethod
    @abstractmethod
    def to_domain(cls, orm_entity: Optional[ORMType]) -> Optional[DomainType]:
        """Convert SQLAlchemy ORM model to Domain entity or aggregate."""
        ...

    @classmethod
    @abstractmethod
    def to_orm(cls, domain_entity: Optional[DomainType]) -> Optional[ORMType]:
        """Convert Domain entity or aggregate to SQLAlchemy ORM model."""
        ...

    @classmethod
    def to_domain_list(cls, orm_entities: List[ORMType]) -> List[DomainType]:
        """Convert a list of ORM models to domain entities."""
        result: List[DomainType] = []
        for item in orm_entities:
            if item is not None:
                d = cls.to_domain(item)
                if d is not None:
                    result.append(d)
        return result

    @classmethod
    def to_orm_list(cls, domain_entities: List[DomainType]) -> List[ORMType]:
        """Convert a list of domain entities to ORM models."""
        result: List[ORMType] = []
        for item in domain_entities:
            if item is not None:
                o = cls.to_orm(item)
                if o is not None:
                    result.append(o)
        return result
