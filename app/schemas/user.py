"""
Pydantic schemas for User and Driver models.
Used for request/response validation and serialization.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

from app.models.user import UserRole


# User Schemas
class UserBase(BaseModel):
    """Base user schema with common fields."""
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating a new user."""
    role: UserRole = UserRole.USER


class UserUpdate(BaseModel):
    """Schema for updating user information."""
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    """Schema for user response."""
    id: int
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Driver Schemas
class DriverBase(BaseModel):
    """Base driver schema with common fields."""
    car_model: Optional[str] = None
    car_number: str
    car_color: Optional[str] = None
    license_number: Optional[str] = None


class DriverCreate(DriverBase):
    """Schema for creating a new driver."""
    user_id: int


class DriverUpdate(BaseModel):
    """Schema for updating driver information."""
    car_model: Optional[str] = None
    car_number: Optional[str] = None
    car_color: Optional[str] = None
    license_number: Optional[str] = None
    is_available: Optional[bool] = None
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None


class DriverResponse(DriverBase):
    """Schema for driver response."""
    id: int
    user_id: int
    is_available: bool
    is_verified: bool
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None
    rating: float
    total_trips: int
    total_earnings: float
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class DriverWithUser(DriverResponse):
    """Schema for driver response with user information."""
    user: UserResponse
    
    model_config = ConfigDict(from_attributes=True)


class DriverLocation(BaseModel):
    """Schema for updating driver location."""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


# Rating Schemas
class RatingCreate(BaseModel):
    """Schema for creating a rating."""
    trip_id: int
    score: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=500)


class RatingResponse(BaseModel):
    """Schema for rating response."""
    id: int
    user_id: int
    driver_id: int
    trip_id: int
    score: int
    comment: Optional[str] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
