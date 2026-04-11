"""
Real-time taximeter: haqiqiy yurilgan yo'l bo'yicha masofa (Haversine kesmalar).

Pure taximeter engine (Decimal, Redis trip_state dict, GPS filters) — quyi funksiyalar.
DB bilan ishlash: accumulate_order_distance_for_driver.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Union

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.models.order import Order, OrderStatus
from app.utils.distance import haversine_distance

# GPS shovqinini kamaytirish (kesma qo'shmasdan last nuqtani yangilash)
MIN_SEGMENT_M = 3.0

# --- Pure engine constants (backend taximeter) ---
GPS_NOISE_MAX_M = 5.0
MAX_SPEED_KMH = 160.0
WAITING_SPEED_KMH = 5.0
DEFAULT_ROUND_STEP_SOM = Decimal("100")
PRICE_TOLERANCE = Decimal("0.02")

_engine_log = get_logger(__name__)


def compute_fare(
    tariff_snapshot: Dict[str, Any],
    distance_km: Union[float, Decimal],
    waiting_seconds: Union[int, float],
    round_to: Decimal = DEFAULT_ROUND_STEP_SOM,
) -> Decimal:
    """
    Total = Base + (distance_km * km_price) + (waiting_seconds / 60 * wait_price).
    All money as Decimal; result rounded to nearest round_to (default 100 so'm).
    """
    base = Decimal(str(tariff_snapshot.get("base", 0)))
    km_p = Decimal(str(tariff_snapshot.get("km", 0)))
    wait_p = Decimal(str(tariff_snapshot.get("wait", 0)))
    d_km = Decimal(str(distance_km))
    w_sec = Decimal(str(waiting_seconds))

    total = base + (d_km * km_p) + ((w_sec / Decimal("60")) * wait_p)
    if round_to <= 0:
        return total
    q = (total / round_to).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * round_to
    return q


def verify_final_price(
    client_price: Union[Decimal, float, int, str],
    computed_price: Union[Decimal, float, int, str],
    tolerance: Decimal = PRICE_TOLERANCE,
) -> bool:
    """
    Server computed_price is authoritative. client_price is compared within ±tolerance.
    Returns True if within tolerance; logs warning if outside.
    """
    cp = Decimal(str(client_price))
    comp = Decimal(str(computed_price))
    if comp == 0:
        ok = cp == 0
        if not ok:
            _engine_log.warning(
                f"Final price mismatch (computed=0): client={cp} computed={comp}",
            )
        return ok
    diff_ratio = abs(cp - comp) / comp
    if diff_ratio > tolerance:
        _engine_log.warning(
            "Final price mismatch exceeds "
            f"{float(tolerance * 100):.2f}%: client={cp} computed={comp} ratio={diff_ratio}",
        )
        return False
    return True


def _segment_speed_kmh(segment_km: float, delta_s: float) -> float:
    if delta_s <= 0:
        return 0.0
    return (segment_km / float(delta_s)) * 3600.0


def apply_waiting_delta(
    trip_state: Dict[str, Any],
    delta_seconds: float,
    speed_kmh: float,
) -> Dict[str, Any]:
    """
    Increment waiting_seconds when speed < WAITING_SPEED_KMH (automatic waiting).

    When manual pause is active (pause_started_ts set), GPS ticks do not add waiting —
    paused time is credited only on resume to avoid double-counting with resume.
    Does not modify last_* GPS fields.
    """
    out = deepcopy(trip_state)
    if delta_seconds <= 0:
        return out

    if out.get("pause_started_ts") is not None:
        return out

    low_speed = speed_kmh < WAITING_SPEED_KMH
    if low_speed:
        ws = float(out.get("waiting_seconds") or 0)
        out["waiting_seconds"] = ws + delta_seconds
    return out


def update_distance(
    trip_state: Dict[str, Any],
    new_lat: float,
    new_lng: float,
    new_ts: Union[int, float],
) -> Dict[str, Any]:
    """
    Apply one GPS fix: Haversine segment, noise/speed filters, distance and waiting rules.

    Distance increases only if status == \"trip\" AND not in waiting mode
    (no manual pause AND speed >= WAITING_SPEED_KMH for the segment).

    Waiting from GPS increases when segment speed < WAITING_SPEED_KMH (manual pause time is added on resume).

    Ignores: movement < 5 m, speed > 160 km/h, duplicate timestamp (new_ts == last_ts).

    Updates: distance_km, waiting_seconds, last_lat, last_lng, last_ts, last_speed_kmh.
    """
    out = deepcopy(trip_state)
    last_ts = out.get("last_ts") or 0
    last_lat = out.get("last_lat")
    last_lng = out.get("last_lng")

    # Duplicate timestamp — no-op
    if new_ts == last_ts:
        return out

    # First fix after init (0,0) or missing last position
    if (
        last_lat is None
        or last_lng is None
        or last_ts == 0
        or (float(last_lat) == 0 and float(last_lng) == 0)
    ):
        out["last_lat"] = float(new_lat)
        out["last_lng"] = float(new_lng)
        out["last_ts"] = new_ts
        out["last_speed_kmh"] = float(out.get("last_speed_kmh") or 0)
        return out

    delta_s = float(new_ts) - float(last_ts)
    if delta_s <= 0:
        return out

    seg_km = haversine_distance(
        float(last_lat), float(last_lng), float(new_lat), float(new_lng)
    )
    speed_kmh = _segment_speed_kmh(seg_km, delta_s)

    out["last_speed_kmh"] = speed_kmh

    # Waiting: pause OR low speed — use interval [last_ts, new_ts]
    out = apply_waiting_delta(out, delta_s, speed_kmh)

    status = str(out.get("status") or "")
    pause_active = out.get("pause_started_ts") is not None
    in_waiting_mode = pause_active or (speed_kmh < WAITING_SPEED_KMH)

    seg_m = seg_km * 1000.0
    bad_speed = speed_kmh > MAX_SPEED_KMH
    noise = seg_m < GPS_NOISE_MAX_M

    can_add_distance = (
        status == "trip"
        and not in_waiting_mode
        and not bad_speed
        and not noise
    )

    if can_add_distance:
        dk = float(out.get("distance_km") or 0)
        out["distance_km"] = dk + seg_km

    out["last_lat"] = float(new_lat)
    out["last_lng"] = float(new_lng)
    out["last_ts"] = new_ts

    return out


async def accumulate_order_distance_for_driver(
    db: AsyncSession,
    driver_id: int,
    lat: float,
    lon: float,
) -> None:
    """
    Haydovchi in_progress buyurtmada bo'lsa: oldingi nuqtadan hozirgacha kesmani qo'shadi,
    last_lat/last_lon ni yangilaydi. flush — commit chaqiruvchi beradi.
    """
    result = await db.execute(
        select(Order)
        .where(Order.driver_id == driver_id)
        .where(Order.status == OrderStatus.IN_PROGRESS)
        .limit(1)
    )
    order = result.scalar_one_or_none()
    if not order:
        return

    oid = order.id
    last_lat = getattr(order, "last_lat", None)
    last_lon = getattr(order, "last_lon", None)

    if last_lat is None or last_lon is None:
        await db.execute(
            update(Order).where(Order.id == oid).values(last_lat=lat, last_lon=lon)
        )
        return

    seg_km = haversine_distance(float(last_lat), float(last_lon), lat, lon)
    if seg_km * 1000.0 < MIN_SEGMENT_M:
        await db.execute(
            update(Order).where(Order.id == oid).values(last_lat=lat, last_lon=lon)
        )
        return

    new_total = float(order.distance_km or 0) + seg_km
    if new_total > 1000:
        new_total = 0.0

    await db.execute(
        update(Order)
        .where(Order.id == oid)
        .values(distance_km=new_total, last_lat=lat, last_lon=lon)
    )
