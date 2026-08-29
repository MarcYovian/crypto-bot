"""Abstract generic mapper interface for converting between ORM models and Domain entities."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, List

DomainType = TypeVar("DomainType")
ORMType = TypeVar("ORMType")


class IMapper(Generic[DomainType, ORMType], ABC):
    """Abstract interface for Domain <-> ORM model mapping."""

    @classmethod
    @abstractmethod
    def to_domain(cls, orm_entity: ORMType) -> DomainType:
        """Convert SQLAlchemy ORM model to Domain entity or aggregate."""
        ...

    @classmethod
    @abstractmethod
    def to_orm(cls, domain_entity: DomainType) -> ORMType:
        """Convert Domain entity or aggregate to SQLAlchemy ORM model."""
        ...

    @classmethod
    def to_domain_list(cls, orm_entities: List[ORMType]) -> List[DomainType]:
        """Convert a list of ORM models to domain entities."""
        return [cls.to_domain(item) for item in orm_entities if item is not None]

    @classmethod
    def to_orm_list(cls, domain_entities: List[DomainType]) -> List[ORMType]:
        """Convert a list of domain entities to ORM models."""
        return [cls.to_orm(item) for item in domain_entities if item is not None]
