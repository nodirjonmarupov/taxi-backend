"""
Settings service: Redis → SQL → config.
Tariff narxlari, komissiya va surge uchun.
"""
import json
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as config
from app.core.redis import get_redis
from app.core.logger import get_logger

logger = get_logger(__name__)

REDIS_SETTINGS_KEY = "taxi:settings"


@dataclass
class TariffSettings:
    min_price: float
    price_per_km: float
    commission_rate: float
    surge_multiplier: float
    is_surge_active: bool
    cashback_percent: float
    max_bonus_usage_percent: float
    max_bonus_cap: float  # Absolyut limit: bir safardan ishlatiladigan maks bonus (so'm)

    def to_dict(self) -> dict:
        return {
            "min_price": self.min_price,
            "price_per_km": self.price_per_km,
            "commission_rate": self.commission_rate,
            "surge_multiplier": self.surge_multiplier,
            "is_surge_active": self.is_surge_active,
            "cashback_percent": self.cashback_percent,
            "max_bonus_usage_percent": self.max_bonus_usage_percent,
            "max_bonus_cap": self.max_bonus_cap,
        }


def _default_settings() -> TariffSettings:
    """Business defaults when Redis and DB both fail."""
    return TariffSettings(
        min_price=5000,
        price_per_km=2500,
        commission_rate=10.0,
        surge_multiplier=1.5,
        is_surge_active=False,
        cashback_percent=0.0,
        max_bonus_usage_percent=0.0,
        max_bonus_cap=5000.0,
    )


def _settings_from_dict(data: dict) -> TariffSettings:
    return TariffSettings(
        min_price=float(data.get("min_price", 5000)),
        price_per_km=float(data.get("price_per_km", 2500)),
        commission_rate=float(data.get("commission_rate", 10.0)),
        surge_multiplier=float(data.get("surge_multiplier", 1.5)),
        is_surge_active=bool(data.get("is_surge_active", False)),
        cashback_percent=float(data.get("cashback_percent", 0.0)),
        max_bonus_usage_percent=float(data.get("max_bonus_usage_percent", 0.0)),
        max_bonus_cap=float(data.get("max_bonus_cap", 5000.0)),
    )


async def get_settings(db: AsyncSession | None = None) -> TariffSettings:
    """
    Redis → SQL → config ketma-ketligida settings olish.
    db berilmasa, faqat Redis va config tekshiriladi (yangi sessiya ochilmaydi).
    """
    redis = get_redis()
    if redis is not None:
        try:
            raw = redis.get(REDIS_SETTINGS_KEY)
            if raw:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                data = json.loads(raw)
                return _settings_from_dict(data)
        except Exception as e:
            logger.debug(f"Redis'dan settings olinmadi: {e}")

    if db:
        try:
            row = await db.execute(
                text(
                    "SELECT min_price, price_per_km, commission_rate, surge_multiplier, is_surge_active, "
                    "cashback_percent, max_bonus_usage_percent, max_bonus_cap FROM settings WHERE id = 1"
                )
            )
            r = row.fetchone()
            if r:
                s = TariffSettings(
                    min_price=float(r[0]),
                    price_per_km=float(r[1]),
                    commission_rate=float(r[2]),
                    surge_multiplier=float(r[3]),
                    is_surge_active=bool(r[4]),
                    cashback_percent=float(r[5] or 0.0),
                    max_bonus_usage_percent=float(r[6] or 0.0),
                    max_bonus_cap=float(r[7] or 5000.0),
                )
                redis = get_redis()
                if redis is not None:
                    try:
                        redis.set(REDIS_SETTINGS_KEY, json.dumps(s.to_dict()), ex=3600)
                    except Exception:
                        pass
                return s
        except Exception as e:
            logger.debug(f"SQL'dan settings olinmadi: {e}")
            try:
                await db.rollback()
            except Exception:
                pass

    return _default_settings()


async def update_settings(
    db: AsyncSession,
    *,
    min_price: Optional[float] = None,
    price_per_km: Optional[float] = None,
    commission_rate: Optional[float] = None,
    surge_multiplier: Optional[float] = None,
    is_surge_active: Optional[bool] = None,
    cashback_percent: Optional[float] = None,
    max_bonus_usage_percent: Optional[float] = None,
    max_bonus_cap: Optional[float] = None,
    admin_user_id: Optional[int] = None,
) -> TariffSettings:
    """
    Settings yangilash: DB + Redis + admin_logs.
    """
    redis = get_redis()
    if redis:
        try:
            redis.delete(REDIS_SETTINGS_KEY)
        except Exception:
            pass

    current = await get_settings(db)
    updates = {}
    if min_price is not None:
        updates["min_price"] = min_price
    if price_per_km is not None:
        updates["price_per_km"] = price_per_km
    if commission_rate is not None:
        updates["commission_rate"] = commission_rate
    if surge_multiplier is not None:
        updates["surge_multiplier"] = surge_multiplier
    if is_surge_active is not None:
        updates["is_surge_active"] = is_surge_active
    if cashback_percent is not None:
        updates["cashback_percent"] = cashback_percent
    if max_bonus_usage_percent is not None:
        updates["max_bonus_usage_percent"] = max_bonus_usage_percent
    if max_bonus_cap is not None:
        updates["max_bonus_cap"] = max_bonus_cap

    if not updates:
        return current

    new_values = {**current.to_dict(), **updates}
    await db.execute(
        text(
            """
            INSERT INTO settings (
                id, min_price, price_per_km, commission_rate, surge_multiplier, is_surge_active,
                cashback_percent, max_bonus_usage_percent, max_bonus_cap
            )
            VALUES (
                1, :min_price, :price_per_km, :commission_rate, :surge_multiplier, :is_surge_active,
                :cashback_percent, :max_bonus_usage_percent, :max_bonus_cap
            )
            ON CONFLICT (id) DO UPDATE SET
                min_price = EXCLUDED.min_price,
                price_per_km = EXCLUDED.price_per_km,
                commission_rate = EXCLUDED.commission_rate,
                surge_multiplier = EXCLUDED.surge_multiplier,
                is_surge_active = EXCLUDED.is_surge_active,
                cashback_percent = EXCLUDED.cashback_percent,
                max_bonus_usage_percent = EXCLUDED.max_bonus_usage_percent,
                max_bonus_cap = EXCLUDED.max_bonus_cap,
                updated_at = CURRENT_TIMESTAMP
        """
        ),
        new_values,
    )

    redis = get_redis()
    if redis is not None:
        try:
            redis.set(REDIS_SETTINGS_KEY, json.dumps(new_values), ex=3600)
        except Exception as e:
            logger.warning(f"Redis settings yangilanmadi: {e}")

    if admin_user_id is not None:
        try:
            await db.execute(
                text("INSERT INTO admin_logs (admin_user_id, action, details) VALUES (:uid, 'settings_update', CAST(:details AS JSONB))"),
                {"uid": admin_user_id, "details": json.dumps(updates)},
            )
        except Exception as e:
            logger.warning(f"Admin log yozilmadi: {e}")

    await db.commit()
    return _settings_from_dict(new_values)


def calculate_price(
    distance_km: float,
    s: TariffSettings,
) -> float:
    """
    Masofa bo'yicha narx (PricingService — 100 so'm yaxlitlash).
    """
    from app.services.pricing_service import PricingService

    return PricingService.apply_tariff_and_round_to_100(distance_km, s)
