"""
Settings: faqat DB (id=1). Runtime uchun qat'iy — soxta defaultlar yo'q.
"""
import json
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.core.logger import get_logger

logger = get_logger(__name__)

REDIS_SETTINGS_KEY = "taxi:settings"
SETTINGS_REDIS_TTL_SEC = 30


class SettingsLoadError(RuntimeError):
    """settings jadvalidan id=1 o'qib bo'lmadi yoki bootstrap yiqildi."""


@dataclass
class TariffSettings:
    min_price: float
    price_per_km: float
    commission_rate: float
    surge_multiplier: float
    is_surge_active: bool
    cashback_percent: float
    max_bonus_usage_percent: float
    max_bonus_cap: float
    price_per_min_waiting: float

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
            "price_per_min_waiting": self.price_per_min_waiting,
        }


# Faqat birinchi INSERT (ON CONFLICT DO NOTHING) uchun — runtime fallback EMAS.
_BOOTSTRAP_SETTINGS_SQL = {
    "min_price": 5000.0,
    "price_per_km": 2500.0,
    "commission_rate": 10.0,
    "surge_multiplier": 1.5,
    "is_surge_active": False,
    "cashback_percent": 0.0,
    "max_bonus_usage_percent": 0.0,
    "max_bonus_cap": 5000.0,
    "price_per_min_waiting": 500.0,
}


def _tariff_from_row(r) -> TariffSettings:
    return TariffSettings(
        min_price=float(r[0]),
        price_per_km=float(r[1]),
        commission_rate=float(r[2]),
        surge_multiplier=float(r[3]),
        is_surge_active=bool(r[4]),
        cashback_percent=float(r[5] if r[5] is not None else 0.0),
        max_bonus_usage_percent=float(r[6] if r[6] is not None else 0.0),
        max_bonus_cap=float(r[7] if r[7] is not None else 0.0),
        price_per_min_waiting=float(r[8] if r[8] is not None else 0.0),
    )


def _tariff_from_flat_dict(d: dict) -> TariffSettings:
    return TariffSettings(
        min_price=float(d["min_price"]),
        price_per_km=float(d["price_per_km"]),
        commission_rate=float(d["commission_rate"]),
        surge_multiplier=float(d["surge_multiplier"]),
        is_surge_active=bool(d["is_surge_active"]),
        cashback_percent=float(d["cashback_percent"]),
        max_bonus_usage_percent=float(d["max_bonus_usage_percent"]),
        max_bonus_cap=float(d["max_bonus_cap"]),
        price_per_min_waiting=float(d["price_per_min_waiting"]),
    )


async def _fetch_settings_row(db: AsyncSession) -> Optional[TariffSettings]:
    try:
        row = await db.execute(
            text(
                "SELECT min_price, price_per_km, commission_rate, surge_multiplier, is_surge_active, "
                "cashback_percent, max_bonus_usage_percent, max_bonus_cap, "
                "COALESCE(price_per_min_waiting, 500) FROM settings WHERE id = 1"
            )
        )
        r = row.fetchone()
        if not r:
            return None
        return _tariff_from_row(r)
    except Exception as e:
        logger.warning("settings SELECT failed: %s", e)
        return None


async def ensure_settings_row(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            INSERT INTO settings (
                id, min_price, price_per_km, commission_rate, surge_multiplier, is_surge_active,
                cashback_percent, max_bonus_usage_percent, max_bonus_cap, price_per_min_waiting
            )
            VALUES (
                1, :min_price, :price_per_km, :commission_rate, :surge_multiplier, :is_surge_active,
                :cashback_percent, :max_bonus_usage_percent, :max_bonus_cap, :price_per_min_waiting
            )
            ON CONFLICT (id) DO NOTHING
            """
        ),
        _BOOTSTRAP_SETTINGS_SQL,
    )


def _write_settings_redis_cache(s: TariffSettings) -> None:
    redis = get_redis()
    if redis is None:
        return
    try:
        redis.set(REDIS_SETTINGS_KEY, json.dumps(s.to_dict()), ex=SETTINGS_REDIS_TTL_SEC)
    except Exception as e:
        logger.debug("Redis settings cache skipped: %s", e)


async def get_settings(db: AsyncSession | None = None) -> TariffSettings:
    from app.core.database import AsyncSessionLocal

    async def _load(db_sess: AsyncSession) -> TariffSettings:
        s = await _fetch_settings_row(db_sess)
        if s is None:
            await ensure_settings_row(db_sess)
            s = await _fetch_settings_row(db_sess)
        if s is None:
            raise SettingsLoadError("settings id=1 could not be loaded after bootstrap")
        _write_settings_redis_cache(s)
        logger.debug(
            "[SETTINGS LOADED] source=database id=1 | min_price=%s price_per_km=%s cashback_percent=%s",
            s.min_price,
            s.price_per_km,
            s.cashback_percent,
        )
        return s

    if db is not None:
        return await _load(db)

    async with AsyncSessionLocal() as session:
        try:
            out = await _load(session)
            await session.commit()
            return out
        except Exception:
            try:
                await session.rollback()
            except Exception:
                pass
            raise


async def get_current_settings(db: AsyncSession | None = None) -> TariffSettings:
    return await get_settings(db)


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
    price_per_min_waiting: Optional[float] = None,
    admin_user_id: Optional[int] = None,
) -> TariffSettings:
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
    if price_per_min_waiting is not None:
        updates["price_per_min_waiting"] = price_per_min_waiting

    if not updates:
        return current

    new_values = {**current.to_dict(), **updates}
    await db.execute(
        text(
            """
            INSERT INTO settings (
                id, min_price, price_per_km, commission_rate, surge_multiplier, is_surge_active,
                cashback_percent, max_bonus_usage_percent, max_bonus_cap, price_per_min_waiting
            )
            VALUES (
                1, :min_price, :price_per_km, :commission_rate, :surge_multiplier, :is_surge_active,
                :cashback_percent, :max_bonus_usage_percent, :max_bonus_cap, :price_per_min_waiting
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
                price_per_min_waiting = EXCLUDED.price_per_min_waiting,
                updated_at = CURRENT_TIMESTAMP
        """
        ),
        new_values,
    )

    redis = get_redis()
    if redis is not None:
        try:
            redis.set(REDIS_SETTINGS_KEY, json.dumps(new_values), ex=SETTINGS_REDIS_TTL_SEC)
        except Exception as e:
            logger.warning("Redis settings yangilanmadi: %s", e)

    if admin_user_id is not None:
        try:
            await db.execute(
                text(
                    "INSERT INTO admin_logs (admin_user_id, action, details) VALUES "
                    "(:uid, 'settings_update', CAST(:details AS JSONB))"
                ),
                {"uid": admin_user_id, "details": json.dumps(updates)},
            )
        except Exception as e:
            logger.warning("Admin log yozilmadi: %s", e)

    await db.commit()
    return _tariff_from_flat_dict(new_values)


def calculate_price(
    distance_km: float,
    s: TariffSettings,
) -> float:
    from app.services.pricing_service import PricingService

    return PricingService.apply_tariff_and_round_to_100(distance_km, s)
