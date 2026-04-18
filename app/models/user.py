"""
User va Driver modellari
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional, Any

from sqlalchemy import Boolean, BigInteger, Integer, String, Float, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from geoalchemy2 import Geography

from app.core.database import Base


class UserRole(str, PyEnum):
    """Foydalanuvchi rollari"""
    USER = "user"
    DRIVER = "driver"
    ADMIN = "admin"


class DriverStatus(str, PyEnum):
    """Haydovchi statuslari"""
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"


class User(Base):
    """Foydalanuvchi modeli"""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    role: Mapped[str] = mapped_column(String(20), default=UserRole.USER, nullable=False)
    language_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # uz, ru, uz_cyrl - NULL = til tanlanmagan
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_approved_driver: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Cashback/redeem tizimi uchun foydalanuvchi bonus balansi
    bonus_balance: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    # Keyingi buyurtmada cashback ishlatish istagi (bir martalik flag)
    use_cashback_next_order: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    orders: Mapped[list["Order"]] = relationship(
        "Order", back_populates="user", lazy="selectin", uselist=True
    )
    driver: Mapped[Optional["Driver"]] = relationship("Driver", back_populates="user", uselist=False, lazy="selectin")


class Driver(Base):
    """Haydovchi modeli"""
    __tablename__ = "drivers"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    car_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    car_model: Mapped[str] = mapped_column(String(100), nullable=False)
    car_color: Mapped[str] = mapped_column(String(50), nullable=False)
    car_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    license_number: Mapped[str] = mapped_column(String(50), nullable=False)
    car_photo_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    driver_license_photo_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    status: Mapped[str] = mapped_column(String(20), default=DriverStatus.PENDING, nullable=False, index=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    balance: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    wallet_balance: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    # Bonus kompensatsiyasi hisobi (bonus_used - komissiya neti)
    virtual_balance: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    min_balance_required: Mapped[float] = mapped_column(Numeric(10, 2), default=10000.0, nullable=False)
    has_active_card: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # card_linked
    payme_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    rating: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    total_ratings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    current_latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # PostGIS/Geography(Point) - radius bo‘yicha tez matching uchun
    location: Mapped[Optional[Any]] = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    location_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    total_trips: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_trips: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancelled_trips: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_earnings: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    total_commission_paid: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    
    blocked_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    commission_rate: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, default=None
    )
    admin_notes: Mapped[Optional[str]] = mapped_column(
        String(2000), nullable=True, default=None
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="driver", lazy="selectin")
    orders: Mapped[list["Order"]] = relationship(
        "Order", back_populates="driver", lazy="selectin", uselist=True
    )


class Rating(Base):
    """Reyting modeli"""
    __tablename__ = "ratings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    driver_id: Mapped[int] = mapped_column(Integer, ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class BalanceTransaction(Base):
    """Balans operatsiyalari tarixi"""
    __tablename__ = "balance_transactions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    driver_id: Mapped[int] = mapped_column(Integer, ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False)
    
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    
    balance_before: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    
    order_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)