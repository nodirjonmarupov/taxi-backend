"""
Narx va masofa hisoblash — bitta manba (DRY).
OSRM yo'l masofasi + zaxira (Haversine * shahar koeffitsiyenti) + tarif + 100 so'm yaxlitlash.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.services.settings_service import TariffSettings, get_settings
from app.utils.distance import haversine_distance

logger = get_logger(__name__)

# OSRM umumiy server (demo). Ishlab chiqarishda o'z serveringizni ishlating.
OSRM_ROUTE_BASE = "https://router.project-osrm.org/route/v1/driving"
CITY_DETOUR_COEFFICIENT = 1.25
HTTP_TIMEOUT_SEC = 15.0


class PricingService:
    """Masofa (OSRM / zaxira) va narx (bazadagi tarif + 100 so'm yaxlitlash)."""

    @staticmethod
    async def fetch_osrm_distance_km(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> Optional[float]:
        """
        OSRM orqali haydovchi yo'li masofasi (km).
        Muvaffaqiyatsiz bo'lsa None.
        """
        # OSRM: lon,lat;lon,lat
        url = (
            f"{OSRM_ROUTE_BASE}/{lon1},{lat1};{lon2},{lat2}"
            f"?overview=false"
        )
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC) as client:
                r = await client.get(url)
                r.raise_for_status()
                data = r.json()
            routes = data.get("routes") or []
            if not routes:
                logger.warning("OSRM: routes bo'sh")
                return None
            meters = routes[0].get("distance")
            if meters is None:
                return None
            return float(meters) / 1000.0
        except Exception as e:
            logger.warning(f"OSRM masofa olinmadi: {e}")
            return None

    @staticmethod
    def fallback_distance_km(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """Tarmoq xatosi: to'g'ri chiziq * shahar koeffitsiyenti."""
        h = haversine_distance(lat1, lon1, lat2, lon2)
        return h * CITY_DETOUR_COEFFICIENT

    @staticmethod
    def round_price_to_100_soum(price: float) -> int:
        """Yuqoriga 100 so'm qadam bilan yaxlitlash."""
        return int(math.ceil(max(0.0, float(price)) / 100.0) * 100)

    @staticmethod
    def apply_tariff_and_round_to_100(
        distance_km: float,
        tariff: TariffSettings,
    ) -> float:
        """
        min_price + km * price_per_km, surge, min_price past bo'lmasin,
        keyin 100 so'mga yaxlitlash.
        """
        raw = float(tariff.min_price) + (float(distance_km) * float(tariff.price_per_km))
        if tariff.is_surge_active and tariff.surge_multiplier and tariff.surge_multiplier > 0:
            raw *= float(tariff.surge_multiplier)
        raw = max(raw, float(tariff.min_price))
        return float(PricingService.round_price_to_100_soum(raw))

    @staticmethod
    async def estimate_trip_price(
        db: AsyncSession,
        pickup_lat: float,
        pickup_lon: float,
        dest_lat: float,
        dest_lon: float,
    ) -> Tuple[float, float]:
        """
        Tarifni bazadan oladi, masofani OSRM yoki zaxira bilan hisoblaydi.

        Returns:
            (distance_km, estimated_price_soum)
        """
        tariff = await get_settings(db)
        dist = await PricingService.fetch_osrm_distance_km(
            pickup_lat, pickup_lon, dest_lat, dest_lon
        )
        if dist is None:
            dist = PricingService.fallback_distance_km(
                pickup_lat, pickup_lon, dest_lat, dest_lon
            )
            logger.info(
                f"Narx: zaxira masofa Haversine×{CITY_DETOUR_COEFFICIENT} = {dist:.4f} km"
            )
        else:
            logger.info(f"Narx: OSRM masofa = {dist:.4f} km")

        price = PricingService.apply_tariff_and_round_to_100(dist, tariff)
        return dist, price
