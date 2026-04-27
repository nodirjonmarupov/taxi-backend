from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, BigInteger, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PaymentTransaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("provider", "provider_tx_id", name="uq_transactions_provider_tx"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # "paynet"
    provider_tx_id: Mapped[str] = mapped_column(String(128), nullable=False)

    driver_id: Mapped[int] = mapped_column(Integer, ForeignKey("drivers.id", ondelete="CASCADE"), nullable=True, index=True)
    phone_e164_snapshot: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    amount_uzs: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # accepted / rejected
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

