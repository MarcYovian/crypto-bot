"""Pydantic schemas and DTOs for user authentication and authorization."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class LoginRequest(BaseModel):
    """Admin login request schema."""
    username: str = Field(..., min_length=3, max_length=50, examples=["admin"])
    password: str = Field(..., min_length=6, max_length=128, examples=["Admin12345!"])


class TokenRefreshRequest(BaseModel):
    """JWT token refresh request schema."""
    refresh_token: str = Field(..., min_length=10)


class UserDTO(BaseModel):
    """User representation for API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str = "ADMIN"
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class LoginResponse(BaseModel):
    """Successful login response containing access & refresh tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserDTO


class UserCreateRequest(BaseModel):
    """Admin user creation schema."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="ADMIN", pattern="^(ADMIN|VIEWER)$")
    is_active: bool = True


class UserUpdatePasswordRequest(BaseModel):
    """Password change request schema."""
    old_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=8, max_length=128)
