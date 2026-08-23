"""Common base models, mixins, and generic wrappers for Pydantic schemas."""

from datetime import datetime
from typing import Generic, TypeVar, List, Optional
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class BaseSchema(BaseModel):
    """Base schema configuration across all domain models."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
    )


class TimestampMixin(BaseSchema):
    """Reusable mixin providing standard audit timestamps."""

    created_at: Optional[datetime] = Field(default=None, description="Record creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Record last update timestamp")


class PaginatedResponse(BaseSchema, Generic[T]):
    """Generic pagination container for list endpoints."""

    items: List[T] = Field(default_factory=list, description="List of items for the current page")
    total: int = Field(..., ge=0, description="Total number of items available")
    page: int = Field(default=1, ge=1, description="Current page number")
    page_size: int = Field(default=50, ge=1, le=100, description="Number of items per page")
    total_pages: int = Field(default=1, ge=1, description="Total calculated pages")
