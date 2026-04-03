from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from app.models.order import OrderStatus

class OrderBase(BaseModel):
    pickup_latitude: float
    pickup_longitude: float
    pickup_address: Optional[str] = None
    destination_latitude: Optional[float] = None
    destination_longitude: Optional[float] = None
    destination_address: Optional[str] = None
    estimated_price: Optional[float] = None
    distance_km: Optional[float] = None

class OrderCreate(OrderBase):
    pass

class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    driver_id: Optional[int] = None
    final_price: Optional[float] = None

class OrderRead(OrderBase):
    """Buyurtmani o'qish uchun - barcha vaqt maydonlari Optional"""
    id: int
    user_id: int
    driver_id: Optional[int] = None
    estimated_price: Optional[float] = None
    final_price: Optional[float] = None
    distance_km: Optional[float] = None
    status: str = "pending"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OrderResponse(OrderRead):
    """OrderRead bilan bir xil"""
    pass

# Statistika uchun kerakli schemalar
class DriverStats(BaseModel):
    total_trips: int
    completed_trips: int
    total_earnings: float
    rating: float

class TopDriverItem(BaseModel):
    name: str
    phone: Optional[str] = None
    completed_orders: int
    rating: float = 5.0


class DailyStatItem(BaseModel):
    date: str  # YYYY-MM-DD
    revenue: float
    order_count: int


class RecentOrderItem(BaseModel):
    client_name: str
    driver_name: Optional[str] = None
    price: Optional[float] = None
    status: str


class TopUserItem(BaseModel):
    name: str
    phone: Optional[str] = None
    total_spent: float


class AdminStats(BaseModel):
    total_users: int
    total_drivers: int
    total_orders: int
    active_orders: int
    active_drivers: int = 0
    revenue: float = 0.0
    profit: float = 0.0
    top_drivers: List["TopDriverItem"] = []
    top_users: List["TopUserItem"] = []
    daily_stats: List["DailyStatItem"] = []
    recent_orders: List["RecentOrderItem"] = []