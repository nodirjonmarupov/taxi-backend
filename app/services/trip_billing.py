"""
Safar yakunida server tomonidan yakuniy narx (taksometr formulasi).
Klient qiymatiga ishonilmaydi.
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.services.settings_service import get_settings
from app.services.taximeter_service import (
    compute_fare,
    resolve_effective_surge_multiplier,
)
from app.utils.trip_finish import sanitize_distance_km

logger = get_logger(__name__)


async def compute_server_final_price_for_completion(
    db: AsyncSession,
    order_id: int,
    order: Any,
    *,
    trip_st: Optional[dict] = None,
) -> Tuple[float, dict, float]:
    """
    Redis trip_state yoki buyurtma tariff_snapshot + masofa/kutish bo'yicha compute_fare.
    Masofa: faqat Redis trip_state yoki DB order.distance_km (klient parametrlariga ishonilmaydi).

    Returns:
        (final_price_float, tariff_snapshot_dict, distance_km_used)
    """
    def _snapshot_from_settings(s) -> dict:
        surge = resolve_effective_surge_multiplier(s)
        return {
            "base": float(s.min_price),
            "km": float(s.price_per_km),
            "wait": float(s.price_per_min_waiting),
            "surge_multiplier": float(surge),
            "tariff_version": 1,
        }

    if trip_st is not None:
        d_km = sanitize_distance_km(float(trip_st.get("distance_km") or 0))
        w_sec = float(trip_st.get("waiting_seconds") or 0)
        tariff = trip_st.get("tariff_snapshot")
        if not tariff:
            tariff = getattr(order, "tariff_snapshot_json", None)
        if not tariff:
            s_cfg = await get_settings(db)
            tariff = _snapshot_from_settings(s_cfg)
        computed = compute_fare(tariff, d_km, w_sec)
        return float(computed), tariff, d_km

    d_src = float(getattr(order, "distance_km", None) or 0.0)
    d_km = sanitize_distance_km(d_src)
    tariff = getattr(order, "tariff_snapshot_json", None)
    if not tariff:
        s_cfg = await get_settings(db)
        tariff = _snapshot_from_settings(s_cfg)
    computed = compute_fare(tariff, d_km, 0.0)
    logger.warning(
        "Trip complete: Redis trip_state yo'q — server narx: tariff_snapshot yoki "
        "fresh DB snapshot, kutish 0 (order_id=%s)",
        order_id,
    )
    return float(computed), tariff, d_km
