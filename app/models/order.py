"""
Order modeli
"""
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, Numeric, func, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class OrderStatus(str, PyEnum):
    """Buyurtma statuslari"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    STARTED = "in_progress"  # IN_PROGRESS bilan bir xil
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Order(Base):
    """Buyurtma modeli"""
    __tablename__ = "orders"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    driver_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("drivers.id", ondelete="SET NULL"), nullable=True)
    
    pickup_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    pickup_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    pickup_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    destination_latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    destination_longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    destination_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    estimated_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    final_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    distance_km: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, server_default="0")

    last_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    status: Mapped[str] = mapped_column(String(20), default=OrderStatus.PENDING, nullable=False, index=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=True
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # completed_at bilan bir xil
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_near_notified: Mapped[bool] = mapped_column(default=False, nullable=False)
    arrived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Mijozga "Haydovchini kuzatish" WebApp xabari — safar tugaganda olib tashlash uchun
    user_tracking_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Komissiya ikki marta yechilmasligi uchun idempotent chek
    commission_deducted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Cashback (EARN) va redeem (SPEND) tizimi uchun
    is_bonus_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Buyurtma yaratilganda muzlatilgan bonus (bekor bo'lsa qaytariladi)
    frozen_bonus: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    used_bonus: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="orders", lazy="selectin")
    driver: Mapped[Optional["Driver"]] = relationship("Driver", back_populates="orders", lazy="selectin")