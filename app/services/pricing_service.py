"""
Narx va masofa hisoblash — bitta manba (DRY).
OSRM yo'l masofasi + zaxira (Haversine * shahar koeffitsiyenti) + tarif + 100 so'm yaxlitlash.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.services.settings_service import get_settings
from app.services.taximeter_service import compute_fare
from app.utils.distance import haversine_distance

logger = get_logger(__name__)

# PRICING CHECKPOINT (stable model):
# SURGE_DISABLED_NEW_SNAPSHOTS = TRUE
# WAITING_MANUAL_ONLY = TRUE
# ALL_PATHS_USE_COMPUTE_FARE = TRUE

# OSRM umumiy server (demo). Ishlab chiqarishda o'z serveringizni ishlating.
OSRM_ROUTE_BASE = "https://router.project-osrm.org/route/v1/driving"
CITY_DETOUR_COEFFICIENT = 1.25
HTTP_TIMEOUT_SEC = 15.0


class PricingService:
    """Masofa (OSRM / zaxira) va narx (bazadagi tarif + 100 so'm yaxlitlash)."""

    @staticmethod
    def build_tariff_snapshot_from_settings(s: Any) -> Dict[str, Any]:
        """
        Single source of truth for ALL pricing snapshots.
        Matches WebApp snapshot fields consumed by compute_fare().
        """
        return {
            "base": float(getattr(s, "min_price", 0) or 0),
            "km": float(getattr(s, "price_per_km", 0) or 0),
            "wait": float(getattr(s, "price_per_min_waiting", 0) or 0),
            "surge_multiplier": 1.0,
            "tariff_version": 1,
        }

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
        s = await get_settings(db)
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

        snap = PricingService.build_tariff_snapshot_from_settings(s)
        price = float(compute_fare(snap, dist, 0))
        logger.info(
            f"[PRICE CALCULATED] estimate dist_km={dist:.4f} rounded_price={price} "
            f"(min_price={snap.get('base')} price_per_km={snap.get('km')} surge_multiplier={snap.get('surge_multiplier')})"
        )
        return dist, price
