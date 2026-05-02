"""
Safar yakunida server tomonidan yakuniy narx (taksometr formulasi).
Klient qiymatiga ishonilmaydi.
"""
from __future__ import annotations

import time
from typing import Any, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.services.pricing_service import PricingService
from app.services.settings_service import get_settings
from app.services.taximeter_service import compute_fare
from app.utils.trip_finish import sanitize_distance_km

logger = get_logger(__name__)

# PRICING CHECKPOINT (stable model):
# SURGE_DISABLED_NEW_SNAPSHOTS = TRUE
# WAITING_MANUAL_ONLY = TRUE
# ALL_PATHS_USE_COMPUTE_FARE = TRUE


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
    if trip_st is not None:
        d_km = sanitize_distance_km(float(trip_st.get("distance_km") or 0))
        ws_stored = float(trip_st.get("waiting_seconds") or 0)
        pts = trip_st.get("pause_started_ts")
        if pts is not None:
            try:
                live_paused = max(0.0, time.time() - float(pts))
            except (TypeError, ValueError):
                live_paused = 0.0
            w_sec = ws_stored + live_paused
        else:
            w_sec = ws_stored
        tariff = trip_st.get("tariff_snapshot")
        if not tariff:
            tariff = getattr(order, "tariff_snapshot_json", None)
        if not tariff:
            s_cfg = await get_settings(db)
            tariff = PricingService.build_tariff_snapshot_from_settings(s_cfg)
        computed = compute_fare(tariff, d_km, w_sec)
        return float(computed), tariff, d_km

    d_src = float(getattr(order, "distance_km", None) or 0.0)
    d_km = sanitize_distance_km(d_src)
    tariff = getattr(order, "tariff_snapshot_json", None)
    if not tariff:
        s_cfg = await get_settings(db)
        tariff = PricingService.build_tariff_snapshot_from_settings(s_cfg)

    try:
        ws_stored = float(getattr(order, "waiting_seconds", 0) or 0)
    except (TypeError, ValueError):
        ws_stored = 0.0
    pts = getattr(order, "pause_started_ts", None)
    if pts is not None:
        try:
            live_paused = max(0.0, time.time() - float(pts))
        except (TypeError, ValueError):
            live_paused = 0.0
        w_sec = ws_stored + live_paused
    else:
        w_sec = ws_stored

    computed = compute_fare(tariff, d_km, w_sec)
    logger.warning(
        "Trip complete: Redis trip_state yo'q — server narx: tariff_snapshot yoki "
        "fresh DB snapshot, waiting_seconds=%s (order_id=%s)",
        w_sec,
        order_id,
    )
    return float(computed), tariff, d_km
