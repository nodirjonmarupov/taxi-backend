"""
Settings modeli - Singleton (bitta qator)
Admin panel orqali o'zgartiriladi, Redis orqali keshlanadi
"""
from datetime import datetime

from sqlalchemy import Integer, Float, Boolean, DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Settings(Base):
    """Sozlamalar - faqat bitta qator (id=1)"""
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    min_price: Mapped[float] = mapped_column(Float, nullable=False, default=5000)
    price_per_km: Mapped[float] = mapped_column(Float, nullable=False, default=2500)
    commission_rate: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    surge_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.5)
    is_surge_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Cashback/redeem tizimi
    cashback_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_bonus_usage_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Bir safardan ishlatiladigan maksimal bonus (so'm, absolute limit)
    max_bonus_cap: Mapped[float] = mapped_column(Float, nullable=False, default=5000.0)
    # Kutish narxi (daqiqa) — settings_service SQL bilan mos
    price_per_min_waiting: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, default=500.0, server_default="500"
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
