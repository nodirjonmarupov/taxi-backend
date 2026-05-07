"""
WebApp API routes
"""
import json
import os
import time
import httpx
from pathlib import Path
from typing import Optional, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis, get_trip_state, set_trip_state, delete_trip_state
from app.utils.webapp_token import verify_webapp_token
from app.services.driver_location_cache import set_driver_location, get_driver_location as get_driver_location_redis
from sqlalchemy.orm import selectinload

from app.crud.order_crud import OrderCRUD
from app.crud.user import UserCRUD, DriverCRUD
from app.services.settings_service import get_settings, SettingsLoadError
from app.utils.trip_finish import sanitize_distance_km
from app.services.taximeter_service import (
    compute_fare,
    update_distance,
)
from app.services.trip_billing import compute_server_final_price_for_completion
from app.models.order import Order, OrderStatus, order_skip_customer_notifications
from app.core.logger import get_logger

logger = get_logger(__name__)

# PRICING CHECKPOINT (stable model):
# SURGE_DISABLED_NEW_SNAPSHOTS = TRUE
# WAITING_MANUAL_ONLY = TRUE
# ALL_PATHS_USE_COMPUTE_FARE = TRUE

router = APIRouter(prefix="/api/webapp", tags=["webapp"])


async def _get_settings_webapp(db: AsyncSession):
    """get_settings + aniq JSON xato (generic 500 emas)."""
    try:
        return await get_settings(db)
    except SettingsLoadError as e:
        logger.error("settings_not_initialized: %s", e)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "settings_not_initialized",
                "message": "Settings row id=1 could not be loaded from the database.",
            },
        )

def _valid_coord(lat: float, lon: float) -> bool:
    """Koordinata yaxlit va Yer sirtida ekanligini tekshir."""
    return -90 <= lat <= 90 and -180 <= lon <= 180

def _parse_coords(lat, lon):
    """Koordinatalarni parse qiladi. Noto'g'ri bo'lsa None qaytaradi (mock yo'q)."""
    try:
        la, lo = float(lat), float(lon)
        if _valid_coord(la, lo):
            return la, lo
    except (TypeError, ValueError):
        pass
    return None

def _sanitize_distance(km) -> float:
    """1000 km dan oshsa 0 (ngrok/IP xato koordinata)"""
    return sanitize_distance_km(km)


def _tariff_snapshot_from_settings(s, at: Optional[datetime] = None) -> dict:
    """get_tariff bilan mos: tariff snapshot (surge pricing o'chirilgan — yangi safarlar 1.0)."""
    return {
        "base": float(s.min_price),
        "km": float(s.price_per_km),
        "wait": float(s.price_per_min_waiting),
        "surge_multiplier": 1.0,
        "tariff_version": 1,
    }


async def _ensure_trip_state_for_order_start(
    redis,
    order_id: int,
    driver_id: int,
    db: AsyncSession,
) -> None:
    """Safar boshlanganda Redis trip_state — mavjud bo'lsa qayta yozilmaydi."""
    if redis is None:
        return
    if get_trip_state(redis, order_id) is not None:
        return
    s = await _get_settings_webapp(db)
    now = time.time()
    state = {
        "driver_id": driver_id,
        "status": "trip",
        "distance_km": 0.0,
        "waiting_seconds": 0.0,
        "is_waiting": False,
        "last_lat": None,
        "last_lng": None,
        "last_ts": None,
        "last_speed_kmh": 0,
        "trip_started_ts": now,
        "pause_started_ts": None,
        "tariff_snapshot": _tariff_snapshot_from_settings(s),
        "updated_at": now,
    }
    set_trip_state(redis, order_id, state)


@router.get("/tariff")
async def get_tariff(db: AsyncSession = Depends(get_db)):
    """Taximeter uchun tarif (startPrice, pricePerKm, pricePerMinWaiting, minDistanceUpdate)."""
    s = await _get_settings_webapp(db)
    return {
        "startPrice": float(s.min_price),
        "pricePerKm": float(s.price_per_km),
        "pricePerMinWaiting": float(s.price_per_min_waiting),
        "minDistanceUpdate": 0.02,
        "surge_multiplier": 1.0,
        "is_surge_active": s.is_surge_active,
        "min_price": float(s.min_price),
        "price_per_km": float(s.price_per_km),
        "commission_rate": float(s.commission_rate),
        "cashback_percent": float(s.cashback_percent),
        "price_per_min_waiting": float(s.price_per_min_waiting),
    }


@router.get("/order/{order_id}")
async def get_order_for_webapp(
    order_id: int,
    token: Optional[str] = Header(None, alias="X-WebApp-Token"),
    qtoken: Optional[str] = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db)
):
    try:
        t = token or qtoken
        if t:
            data = verify_webapp_token(t, order_id)
            if not data:
                logger.warning(
                    "❌ WebApp token rad etildi: order_id=%s  "
                    "(verify_webapp_token None qaytardi — log'da sabab bor)",
                    order_id,
                )
                raise HTTPException(
                    status_code=403,
                    detail="Invalid or expired WebApp token. Iltimos, taximeterni qayta oching.",
                )
            _, driver_id = data
        else:
            driver_id = None

        logger.info(f"📱 WebApp: Order {order_id} ma'lumotlari so'ralmoqda")
        order = await OrderCRUD.get_by_id(db, order_id)

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if driver_id is not None and getattr(order, "driver_id", None) != driver_id:
            logger.warning(
                "❌ WebApp: driver_id mos emas — token_driver=%s, order.driver_id=%s, order=%s",
                driver_id, getattr(order, "driver_id", None), order_id,
            )
            raise HTTPException(status_code=403, detail="Access denied: not your order")

        user_id = getattr(order, "user_id", None)
        user = await UserCRUD.get_by_id(db, user_id) if user_id else None

        pick_result = _parse_coords(
            getattr(order, "pickup_latitude", None),
            getattr(order, "pickup_longitude", None)
        )
        if pick_result is None:
            raise HTTPException(status_code=400, detail="Invalid pickup coordinates")
        pick_lat, pick_lon = pick_result

        dest_result = _parse_coords(
            getattr(order, "destination_latitude", None),
            getattr(order, "destination_longitude", None)
        )
        dest_lat, dest_lon = (dest_result if dest_result else (pick_lat, pick_lon))

        # Barcha maydonlarni str/float qilib qaytarish (500 xatoni oldini olish)
        status_val = order.status
        if hasattr(status_val, 'value'):
            status_val = status_val.value
        try:
            est = float(order.estimated_price or 0)
        except (TypeError, ValueError):
            est = 0.0
        try:
            dist = float(_sanitize_distance(order.distance_km))
        except (TypeError, ValueError):
            dist = 0.0
        logger.info(f"📍 XARITA KOORDINATLARI | order_id={order.id} | pickup_lat={pick_lat} | pickup_lon={pick_lon} | mijoz nuqtasiga center")
        print(f"[ORDER] order_id={order.id} qabul qilindi | pickup_lat={pick_lat} | pickup_lon={pick_lon} | ORDER_DATA.pickup_latitude ishlatiladi")
        driver_id = getattr(order, "driver_id", None)
        return {
            "id": int(order.id),
            "status": str(status_val),
            "driver_id": int(driver_id) if driver_id is not None else None,
            "customer_name": str(user.first_name if user and user.first_name else "Mijoz"),
            "customer_phone": str(user.phone if user and user.phone else "N/A"),
            "pickup_latitude": float(pick_lat),
            "pickup_longitude": float(pick_lon),
            "pickup_address": str(order.pickup_address or "N/A"),
            "destination_latitude": float(dest_lat),
            "destination_longitude": float(dest_lon),
            "estimated_price": est,
            "distance_km": dist
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Order GET xatosi: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _map_osrm_modifier_to_text(mod: str) -> str:
    if mod in ("fork left", "fork slight left"):
        return "Chap tomonga ajraling"
    if mod in ("fork right", "fork slight right"):
        return "O\u2018ng tomonga ajraling"
    if mod in ("merge left",):
        return "Chapga qo\u2018shiling"
    if mod in ("merge right",):
        return "O\u2018ngga qo\u2018shiling"
    if "roundabout" in mod:
        return "Aylanma harakatdan o\u2018ting"
    if mod in ("left", "slight left", "sharp left"):
        return "Chapga buriling"
    if mod in ("right", "slight right", "sharp right"):
        return "O'ngga buriling"
    if mod in ("uturn", "uturn left", "uturn right"):
        return "Ortga qayting"
    return "To'g'ri davom eting"


@router.get("/order/{order_id}/driving-directions")
async def driving_directions(
    order_id: int,
    origin_lat: float = Query(...),
    origin_lng: float = Query(...),
    dest_lat: float = Query(...),
    dest_lng: float = Query(...),
    token: Optional[str] = Header(None, alias="X-WebApp-Token"),
    qtoken: Optional[str] = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db),
):
    """
    OSRM route (server proxy — mijoz brauzeridan to'g'ridan-to'g'ri chaqirolmaydi CORS sababli).
    Redis / compute_fare / trip_state ga tegmaydi.
    """
    t = token or qtoken
    if not t:
        raise HTTPException(status_code=403, detail="WebApp token required")
    data_tok = verify_webapp_token(t, order_id)
    if not data_tok:
        raise HTTPException(status_code=403, detail="Invalid or expired WebApp token")
    _, driver_id = data_tok

    order = await OrderCRUD.get_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if getattr(order, "driver_id", None) != driver_id:
        raise HTTPException(status_code=403, detail="Access denied: not your order")

    for la, lo in ((origin_lat, origin_lng), (dest_lat, dest_lng)):
        if not _valid_coord(float(la), float(lo)):
            return {"ok": False, "error": "invalid_coordinates", "coordinates": [], "distance_km": 0.0, "instructions": []}

    redis = get_redis()
    origin_key = f"{round(origin_lat, 5)}_{round(origin_lng, 5)}"
    dest_key = f"{round(dest_lat, 5)}_{round(dest_lng, 5)}"
    cache_key = f"route_cache:{origin_key}:{dest_key}"

    cached = redis.get(cache_key) if redis else None
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    rate_key = f"route_rate:{order_id}"
    ok = redis.set(rate_key, "1", nx=True, ex=2) if redis else True
    if not ok:
        cached = redis.get(cache_key) if redis else None
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass
        return {"ok": False, "error": "rate_limited"}

    import math as _math
    _SNAP_MAX_M = 100.0  # reject snap if it moved the point more than this

    def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        R = 6_371_000.0
        dlat = _math.radians(lat2 - lat1)
        dlng = _math.radians(lng2 - lng1)
        a = (
            _math.sin(dlat / 2) ** 2
            + _math.cos(_math.radians(lat1)) * _math.cos(_math.radians(lat2))
            * _math.sin(dlng / 2) ** 2
        )
        return 2 * R * _math.atan2(_math.sqrt(a), _math.sqrt(1 - a))

    def _extract_snap(resp_json, orig_lat: float, orig_lng: float):
        """Return (snapped_lng, snapped_lat) from OSRM /nearest response.
        Uses number=3 candidates and picks the closest one within _SNAP_MAX_M.
        Falls back to original coords on any error or if all candidates are too far."""
        try:
            wps = resp_json.get("waypoints") if isinstance(resp_json, dict) else None
            if not wps or not isinstance(wps, list):
                return orig_lng, orig_lat
            best_lng, best_lat, best_dist = orig_lng, orig_lat, _SNAP_MAX_M
            for wp in wps:
                if not isinstance(wp, dict):
                    continue
                loc = wp.get("location")
                if not loc or not isinstance(loc, list) or len(loc) < 2:
                    continue
                clng, clat = float(loc[0]), float(loc[1])
                d = _haversine_m(orig_lat, orig_lng, clat, clng)
                if d < best_dist:
                    best_dist = d
                    best_lng, best_lat = clng, clat
            return best_lng, best_lat
        except Exception:
            return orig_lng, orig_lat

    # Snap origin and destination to nearest drivable road point in parallel.
    # IMPORTANT: snapped coords are used only for routing; UI pins use the originals.
    snapped_orig_lng = float(origin_lng)
    snapped_orig_lat = float(origin_lat)
    snapped_dest_lng = float(dest_lng)
    snapped_dest_lat = float(dest_lat)
    last_meters_to_destination = 0.0

    OSRM_BASE_URL = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org")
    ENABLE_OSRM_MATCH = os.getenv("ENABLE_OSRM_MATCH", "false").lower() == "true"

    nearest_orig_url = (
        f"{OSRM_BASE_URL}/nearest/v1/driving/"
        f"{float(origin_lng)},{float(origin_lat)}"
        "?number=3"
    )
    nearest_dest_url = (
        f"{OSRM_BASE_URL}/nearest/v1/driving/"
        f"{float(dest_lng)},{float(dest_lat)}"
        "?number=3"
    )

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            # Snap origin + destination in parallel (best-effort; failures fall back to raw coords)
            try:
                import asyncio as _asyncio
                n_orig_resp, n_dest_resp = await _asyncio.gather(
                    client.get(nearest_orig_url),
                    client.get(nearest_dest_url),
                    return_exceptions=True,
                )
                if not isinstance(n_orig_resp, Exception) and n_orig_resp.status_code == 200:
                    snapped_orig_lng, snapped_orig_lat = _extract_snap(
                        n_orig_resp.json(), float(origin_lat), float(origin_lng)
                    )
                if not isinstance(n_dest_resp, Exception) and n_dest_resp.status_code == 200:
                    snapped_dest_lng, snapped_dest_lat = _extract_snap(
                        n_dest_resp.json(), float(dest_lat), float(dest_lng)
                    )
            except Exception:
                pass

            # Distance from UI destination pin to snapped road point (used by frontend)
            try:
                last_meters_to_destination = _haversine_m(
                    float(dest_lat), float(dest_lng),
                    snapped_dest_lat, snapped_dest_lng,
                )
            except Exception:
                last_meters_to_destination = 0.0

            # Build route URL with snapped endpoints
            osrm_url = (
                f"{OSRM_BASE_URL}/route/v1/driving/"
                f"{snapped_orig_lng},{snapped_orig_lat};{snapped_dest_lng},{snapped_dest_lat}"
                "?overview=full&geometries=geojson&steps=true&continue_straight=true"
            )
            resp = await client.get(osrm_url)
            data = resp.json()
    except Exception as e:
        logger.error("driving_directions httpx: %s", e)
        return {"ok": False, "error": "no_route"}

    if resp.status_code != 200:
        logger.error("OSRM error: %s", data)
        return {"ok": False, "error": "no_route"}

    if data.get("code") != "Ok":
        logger.error("OSRM error: %s", data)
        return {"ok": False, "error": "no_route"}

    routes = data.get("routes")
    if not routes:
        logger.error("OSRM error: %s", data)
        return {"ok": False, "error": "no_route"}

    route = routes[0]
    geometry = (route.get("geometry") or {}).get("coordinates")
    if not geometry or not isinstance(geometry, list):
        logger.error("OSRM error: %s", data)
        return {"ok": False, "error": "no_route"}

    distance_km = float(route.get("distance") or 0) / 1000.0

    steps_out = []
    for leg in route.get("legs", []) or []:
        if not isinstance(leg, dict):
            continue
        for st in leg.get("steps", []) or []:
            if not isinstance(st, dict):
                continue
            man = st.get("maneuver") or {}
            if not isinstance(man, dict):
                continue
            loc = man.get("location")
            if not loc or not isinstance(loc, list) or len(loc) < 2:
                continue
            try:
                modifier = (man.get("modifier") or "").lower()
                text = _map_osrm_modifier_to_text(modifier.replace("_", " "))
                steps_out.append(
                    {
                        "lat": float(loc[1]),
                        "lng": float(loc[0]),
                        "text": text,
                        "modifier": modifier,
                        "distance": float(st.get("distance") or 0),
                    }
                )
            except (TypeError, ValueError):
                continue

    logger.info("OSRM route OK")
    response = {
        "ok": True,
        "coordinates": geometry,
        "distance_km": distance_km,
        "snapped_destination": [snapped_dest_lng, snapped_dest_lat],
        "last_meters_to_destination": float(last_meters_to_destination or 0.0),
        "steps": steps_out,
    }
    if redis:
        try:
            redis.set(cache_key, json.dumps(response), ex=5)
        except Exception:
            pass
    return response

class MapMatchRequest(BaseModel):
    coordinates: list
    timestamps: list
    radiuses: list

@router.post("/order/{order_id}/map-match")
async def map_match(
    order_id: int,
    body: MapMatchRequest,
    token: str = Header(None, alias="X-WebApp-Token"),
    qtoken: str = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db)
):
    # Feature flag
    if not os.getenv("ENABLE_OSRM_MATCH", "false").lower() == "true":
        return {"matched": None, "reason": "disabled"}

    # Auth guard — copied verbatim from driving-directions
    t = token or qtoken
    if not t:
        raise HTTPException(status_code=403, detail="WebApp token required")
    data_tok = verify_webapp_token(t, order_id)
    if not data_tok:
        raise HTTPException(status_code=403, detail="Invalid or expired WebApp token")
    _, driver_id = data_tok
    order = await OrderCRUD.get_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if getattr(order, "driver_id", None) != driver_id:
        raise HTTPException(status_code=403, detail="Access denied: not your order")

    # Validate input
    coords = body.coordinates
    if not (3 <= len(coords) <= 7):
        return {"matched": None, "reason": "invalid_input"}
    if len(body.timestamps) != len(coords) or len(body.radiuses) != len(coords):
        return {"matched": None, "reason": "invalid_input"}

    try:
        _osrm_base = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org")
        coords_str = ";".join(f"{c[0]},{c[1]}" for c in coords)
        radii_str  = ";".join(str(r) for r in body.radiuses)
        ts_str     = ";".join(str(t) for t in body.timestamps)
        url = (
            f"{_osrm_base}/match/v1/driving/{coords_str}"
            f"?overview=false&geometries=geojson"
            f"&radiuses={radii_str}&timestamps={ts_str}"
        )
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(url)
            data = resp.json()

        if data.get("code") != "Ok" or not data.get("matchings"):
            return {"matched": None, "reason": "no_match"}

        last = data["matchings"][0]["geometry"]["coordinates"][-1]
        return {"matched": {"lat": last[1], "lng": last[0]}}

    except Exception:
        return {"matched": None, "reason": "error"}


def _validate_status_transition(current: str, new_status: str, mapped: Any) -> None:
    """Status o'tishini tekshirish. Noto'g'ri bo'lsa HTTPException."""
    allowed = {
        "accepted": ["arrived", "started", "in_progress", "cancelled"],
        "in_progress": ["completed", "cancelled"],
        "pending": ["cancelled"],
    }
    cur = current.lower() if isinstance(current, str) else str(current)
    new_lower = new_status.lower()
    valid = allowed.get(cur, [])
    if new_lower not in valid and new_lower != cur:
        raise HTTPException(status_code=400, detail=f"Invalid status transition: {cur} -> {new_lower}")

@router.post("/order/{order_id}/status")
async def update_order_status(
    order_id: int,
    new_status: str,
    distance_km: Optional[float] = None,
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None),
    token: Optional[str] = Header(None, alias="X-WebApp-Token"),
    qtoken: Optional[str] = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db)
):
    try:
        t = token or qtoken
        if not t:
            raise HTTPException(status_code=403, detail="WebApp token required")
        data = verify_webapp_token(t, order_id)
        if not data:
            raise HTTPException(status_code=403, detail="Invalid or expired WebApp token")
        _, driver_id = data

        logger.info(f"📱 WebApp: Order {order_id} status yangilanmoqda: {new_status} (driver={driver_id})")
        order = await OrderCRUD.get_by_id_for_update(db, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        ord_driver = getattr(order, "driver_id", None)
        if ord_driver != driver_id:
            raise HTTPException(status_code=403, detail="Access denied: only assigned driver can update")

        cur_status = (order.status.value if hasattr(order.status, "value") else order.status) or ""

        # Idempotent: takroriy "completed" — komissiya va xabarlar qayta ishlamaydi
        if new_status.lower() == "completed" and str(cur_status).lower() == "completed":
            r_clean = get_redis()
            if r_clean is not None:
                delete_trip_state(r_clean, order_id)
            logger.info(f"📱 WebApp: Order {order_id} allaqachon completed — idempotent javob")
            return {"success": True, "status": "completed", "idempotent": True}

        status_map = {
            "arrived": OrderStatus.ACCEPTED,
            "started": OrderStatus.IN_PROGRESS,
            "in_progress": OrderStatus.IN_PROGRESS,
            "completed": OrderStatus.COMPLETED,
            "cancelled": OrderStatus.CANCELLED
        }
        mapped_status = status_map.get(new_status.lower(), OrderStatus.IN_PROGRESS)
        _validate_status_transition(cur_status, new_status.lower(), mapped_status)

        sanitized_dist = _sanitize_distance(distance_km) if distance_km is not None else None
        now = datetime.utcnow()

        apply_taximeter_start = (
            mapped_status == OrderStatus.IN_PROGRESS
            and str(cur_status).lower() == "accepted"
        )
        trip_lat = lat
        trip_lon = lon
        if apply_taximeter_start and (trip_lat is None or trip_lon is None) and getattr(order, "driver_id", None):
            drv = await DriverCRUD.get_by_id(db, order.driver_id)
            if drv:
                if trip_lat is None:
                    trip_lat = getattr(drv, "current_latitude", None)
                if trip_lon is None:
                    trip_lon = getattr(drv, "current_longitude", None)
        if trip_lat is not None:
            trip_lat = float(trip_lat)
        if trip_lon is not None:
            trip_lon = float(trip_lon)
        if apply_taximeter_start and trip_lat is not None and trip_lon is not None:
            if not _valid_coord(trip_lat, trip_lon):
                trip_lat, trip_lon = None, None

        resolved_final: Optional[float] = None
        tariff_snapshot_for_db: Optional[dict] = None
        if mapped_status == OrderStatus.COMPLETED:
            r_ts = get_redis()
            trip_st = get_trip_state(r_ts, order_id) if r_ts else None
            resolved_final, tariff_snapshot_for_db, sanitized_dist = (
                await compute_server_final_price_for_completion(
                    db,
                    order_id,
                    order,
                    trip_st=trip_st,
                )
            )
            logger.info(
                f"[PRICE CALCULATED] order={order_id} server_final={resolved_final} "
                f"distance_km={sanitized_dist}"
            )

        updated_order = await OrderCRUD.update_status(
            db,
            order_id,
            mapped_status,
            distance_km=sanitized_dist,
            final_price=resolved_final if mapped_status == OrderStatus.COMPLETED else None,
            updated_at=now,
            apply_taximeter_start=apply_taximeter_start,
            trip_start_lat=trip_lat,
            trip_start_lon=trip_lon,
            tariff_snapshot_json=tariff_snapshot_for_db
            if mapped_status == OrderStatus.COMPLETED
            else None,
        )

        if apply_taximeter_start and updated_order:
            r0 = get_redis()
            if r0 is not None:
                await _ensure_trip_state_for_order_start(r0, order_id, driver_id, db)
            try:
                drv_busy = await DriverCRUD.get_by_id(db, driver_id)
                if drv_busy is not None:
                    drv_busy.is_available = False
                    await db.commit()
            except Exception as ex_unavail:
                logger.warning(
                    "driver is_available=False after taximeter start order=%s: %s",
                    order_id,
                    ex_unavail,
                )

        if mapped_status == OrderStatus.COMPLETED and updated_order and driver_id:
            try:
                drv_done = await DriverCRUD.get_by_id(db, driver_id)
                if drv_done is not None:
                    drv_done.is_available = True
                    await db.commit()
            except Exception as ex_avail:
                logger.warning(
                    "driver is_available=True after trip complete order=%s: %s",
                    order_id,
                    ex_avail,
                )

        if mapped_status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED) and updated_order:
            r1 = get_redis()
            if r1 is not None:
                delete_trip_state(r1, order_id)

        # Safar yakunlanganda komissiya ayirish va xabarlar + FSM ni tozalab, mijozni bosh menyuga qaytarish
        if mapped_status == OrderStatus.COMPLETED and updated_order:
            from app.services.commission import deduct_commission_on_trip_complete
            from app.bot.messages import get_text
            from aiogram.fsm.storage.base import StorageKey
            from aiogram.fsm.context import FSMContext
            from app.bot.keyboards.main_menu import get_main_keyboard
            from app.core.database import AsyncSessionLocal

            # Telegram ID va til ma'lumotlarini ALOHIDA sessiyada olamiz.
            # Sabab: request db update_status ichida commit qilingan; bir xil
            # sessiya bilan yana so'rov yuborilsa asyncpg "transaction is closed"
            # xatoligini berishi mumkin. Yangi sessiya bu muammoni butunlay yo'q qiladi.
            user_telegram_id = None
            driver_telegram_id = None
            user_lang = "uz"
            driver_lang = "uz"
            async with AsyncSessionLocal() as _fetch_session:
                _user = await UserCRUD.get_by_id(_fetch_session, order.user_id)
                _driver = await DriverCRUD.get_by_id(_fetch_session, order.driver_id)
                _driver_user = (
                    await UserCRUD.get_by_id(_fetch_session, _driver.user_id)
                    if _driver and _driver.user_id else None
                )
                user_telegram_id = getattr(_user, "telegram_id", None) if _user else None
                driver_telegram_id = getattr(_driver_user, "telegram_id", None) if _driver_user else None
                user_lang = getattr(_user, "language_code", None) or "uz" if _user else "uz"
                driver_lang = getattr(_driver_user, "language_code", None) or "uz" if _driver_user else "uz"

            # Commission o'z sessiyasida ishlaydi — request db uzatilmaydi
            bonus_info = await deduct_commission_on_trip_complete(updated_order)

            # Mijoz va haydovchiga xabar - use plain vars only (no ORM access after commit)
            try:
                from decimal import Decimal as _Dec
                final_price_val = int(getattr(updated_order, "final_price", None) or 0)
                dist_km = float(getattr(updated_order, "distance_km", None) or 0)
                dist_val = f"{dist_km:.1f}" if dist_km else "0"

                used_bonus    = int(bonus_info.get("used_bonus", 0))
                earned_cashback = int(bonus_info.get("earned_cashback", 0))
                payable_amount  = int(bonus_info.get("payable_amount", 0))
                commission_val  = int(bonus_info.get("commission", 0))

                def _fmt(n: int) -> str:
                    return f"{n:,}".replace(",", " ")

                # Mijoz xabari (o'zgarmagan format)
                dist_line = "\n" + get_text(user_lang, "distance_label", dist=dist_val) if dist_km else ""
                msg_user = (
                    get_text(user_lang, "trip_completed_title")
                    + "\n\n"
                    + get_text(
                        user_lang,
                        "user_final_bill",
                        payable=_fmt(payable_amount),
                        used=_fmt(used_bonus),
                        earned=_fmt(earned_cashback),
                    )
                    + dist_line
                )

                # Haydovchi xabari — minimalist, bonus/no-bonus ikkita variant
                if used_bonus > 0:
                    net_cash = final_price_val - used_bonus   # mijoz naqd to'lagan
                    balance_change = used_bonus - commission_val
                    msg_driver = (
                        f"✅ <b>Safar yakunlandi!</b>\n"
                        f"💵 Naqd: <b>{_fmt(net_cash)} so'm</b>\n"
                        f"🎁 Bonus: <b>{_fmt(used_bonus)} so'm</b>\n"
                        f"📉 Kom: <b>-{_fmt(commission_val)} so'm</b>\n"
                        f"📈 Balans: <b>+{_fmt(balance_change)} so'm</b>"
                    )
                else:
                    msg_driver = (
                        f"✅ <b>Safar yakunlandi!</b>\n"
                        f"💵 To'lov: <b>{_fmt(final_price_val)} so'm</b>\n"
                        f"📉 Kom: <b>-{_fmt(commission_val)} so'm</b>"
                    )

                from app.bot.telegram_bot import bot, dp
                sent_user = False
                sent_driver = False
                user_main_menu_sent = False

                if user_telegram_id and not order_skip_customer_notifications(updated_order):
                    try:
                        from app.bot.tracking_message_cleanup import clear_user_tracking_message

                        tracking_mid = getattr(updated_order, "user_tracking_message_id", None)
                        await clear_user_tracking_message(
                            bot, user_telegram_id, tracking_mid
                        )

                        await bot.send_message(user_telegram_id, msg_user, parse_mode="HTML")
                        sent_user = True

                        key = StorageKey(
                            bot_id=bot.id,
                            chat_id=user_telegram_id,
                            user_id=user_telegram_id,
                        )
                        user_fsm = FSMContext(storage=dp.storage, key=key)
                        await user_fsm.clear()

                        await bot.send_message(
                            chat_id=user_telegram_id,
                            text=get_text(user_lang, "order_finished"),
                            reply_markup=get_main_keyboard(user_lang),
                        )
                        user_main_menu_sent = True
                    except Exception as ex:
                        logger.warning(f"Mijozga xabar yuborishda xato (bloklangan yoki boshqa): {ex}")

                if driver_telegram_id:
                    try:
                        await bot.send_message(driver_telegram_id, msg_driver, parse_mode="HTML")
                        sent_driver = True
                    except Exception as ex:
                        logger.warning(f"Haydovchiga xabar yuborishda xato: {ex}")

                if sent_user or sent_driver:
                    logger.info(
                        f"📱 Safar #{order_id} yakunlandi - mijoz: {sent_user}, haydovchi: {sent_driver}, "
                        f"bosh menyu yuborildi: {user_main_menu_sent}"
                    )
            except Exception as ex:
                logger.warning(f"Xabar yuborishda xato: {ex}")

        return {"success": True, "status": str(mapped_status.value if hasattr(mapped_status, 'value') else mapped_status)}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.error(f"❌ Status POST xatosi: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Baza xatosi: {str(e)}")


@router.post("/order/{order_id}/arrived")
async def driver_arrived(
    order_id: int,
    token: Optional[str] = Header(None, alias="X-WebApp-Token"),
    qtoken: Optional[str] = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db)
):
    """Haydovchi mijoz oldiga keldi — mijozga xabar yuborish. Token talab qilinadi."""
    try:
        t = token or qtoken
        if not t:
            return JSONResponse({"ok": False, "detail": "WebApp token required"}, status_code=403)
        data = verify_webapp_token(t, order_id)
        if not data:
            return JSONResponse({"ok": False, "detail": "Invalid or expired token"}, status_code=403)
        _, driver_id = data

        from sqlalchemy import select
        from app.models.order import Order
        from app.models.user import User
        from app.bot.telegram_bot import send_message_to_user

        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if not order:
            return JSONResponse({"ok": False, "detail": "Order topilmadi"})
        if getattr(order, "driver_id", None) != driver_id:
            return JSONResponse({"ok": False, "detail": "Access denied"}, status_code=403)

        # Save arrived timestamp
        await db.execute(
            text("UPDATE orders SET arrived_at = :now WHERE id = :oid"),
            {"now": datetime.utcnow(), "oid": order_id}
        )
        await db.commit()

        if order_skip_customer_notifications(order):
            return JSONResponse({"ok": True})

        user_result = await db.execute(select(User).where(User.id == order.user_id))
        user = user_result.scalar_one_or_none()
        if not user or not getattr(user, "telegram_id", None):
            return JSONResponse({"ok": False, "detail": "User telegram_id yo'q"})

        lang = getattr(user, "language_code", None) or "uz"
        lang = lang.lower()

        if lang == "ru":
            msg = (
                "🚕 Ваш водитель прибыл!\n\n"
                "Пожалуйста, приготовьтесь выходить.\n"
                "Водитель ждёт вас. 🙏"
            )
        elif lang == "uz_cyrl":
            msg = (
                "🚕 Ҳайдовчингиз етиб келди!\n\n"
                "Илтимос, чиқишга тайёр туринг.\n"
                "Ҳайдовчи сизни кутмоқда. 🙏"
            )
        else:
            msg = (
                "🚕 Haydovchingiz yetib keldi!\n\n"
                "Iltimos, chiqishga tayyor bo'ling.\n"
                "Haydovchi sizi kutmoqda. 🙏"
            )

        try:
            await send_message_to_user(user.telegram_id, msg)
        except Exception:
            pass

        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "detail": str(e)})


@router.post("/order/{order_id}/trip/pause")
async def trip_pause(
    order_id: int,
    token: Optional[str] = Header(None, alias="X-WebApp-Token"),
    qtoken: Optional[str] = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db),
):
    """Safarni pauza (kutish): Redis trip_state — takroriy chaqiriq xavfsiz."""
    t = token or qtoken
    if not t:
        raise HTTPException(status_code=403, detail="WebApp token required")
    data = verify_webapp_token(t, order_id)
    if not data:
        raise HTTPException(status_code=403, detail="Invalid or expired WebApp token")
    _, driver_id = data
    order = await OrderCRUD.get_by_id(db, order_id)
    if not order or getattr(order, "driver_id", None) != driver_id:
        raise HTTPException(status_code=403, detail="Access denied")
    redis = get_redis()
    if redis is None:
        raise HTTPException(status_code=503, detail="Redis unavailable")
    lock_key = f"trip_lock:{order_id}"
    ok = redis.set(lock_key, "1", nx=True, ex=2)
    if not ok:
        return {"ok": True, "skipped": True}
    try:
        st = get_trip_state(redis, order_id)
        if not st:
            return {"ok": True, "active": False}
        if int(st.get("driver_id") or 0) != driver_id:
            raise HTTPException(status_code=403, detail="Access denied")
        if st.get("pause_started_ts") is not None:
            return {"ok": True, "idempotent": True}
        now = time.time()
        st["is_waiting"] = True
        st["pause_started_ts"] = now
        st["updated_at"] = now
        set_trip_state(redis, order_id, st)
        try:
            order.pause_started_ts = now
            await db.commit()

        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass

            raise HTTPException(
                status_code=500,
                detail="Failed to persist pause state",
            )
        return {"ok": True}
    finally:
        try:
            redis.delete(lock_key)
        except Exception:
            pass


@router.post("/order/{order_id}/trip/resume")
async def trip_resume(
    order_id: int,
    token: Optional[str] = Header(None, alias="X-WebApp-Token"),
    qtoken: Optional[str] = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db),
):
    """Pauzadan chiqish: to'xtagan vaqtni waiting_seconds ga qo'shadi (idempotent)."""
    t = token or qtoken
    if not t:
        raise HTTPException(status_code=403, detail="WebApp token required")
    data = verify_webapp_token(t, order_id)
    if not data:
        raise HTTPException(status_code=403, detail="Invalid or expired WebApp token")
    _, driver_id = data
    order = await OrderCRUD.get_by_id(db, order_id)
    if not order or getattr(order, "driver_id", None) != driver_id:
        raise HTTPException(status_code=403, detail="Access denied")
    redis = get_redis()
    if redis is None:
        raise HTTPException(status_code=503, detail="Redis unavailable")
    lock_key = f"trip_lock:{order_id}"
    ok = redis.set(lock_key, "1", nx=True, ex=2)
    if not ok:
        return {"ok": True, "skipped": True}
    try:
        st = get_trip_state(redis, order_id)
        if not st:
            return {"ok": True, "active": False}
        if int(st.get("driver_id") or 0) != driver_id:
            raise HTTPException(status_code=403, detail="Access denied")
        pause_ts = st.get("pause_started_ts")
        if pause_ts is None:
            return {"ok": True, "idempotent": True}
        pause_ts_val = float(pause_ts or 0)
        pause_ts_key = int(pause_ts_val * 1000)  # millisecond precision
        resume_key = f"resume_once:{order_id}:{pause_ts_key}"
        now = time.time()
        paused = float(now) - float(pause_ts)
        if paused > 0:
            st["waiting_seconds"] = float(st.get("waiting_seconds") or 0) + paused
        st["is_waiting"] = False
        st["pause_started_ts"] = None
        st["updated_at"] = now
        set_trip_state(redis, order_id, st)
        try:
            prev_db = float(getattr(order, "waiting_seconds", None) or 0.0)
            if paused > 0:
                order.waiting_seconds = prev_db + float(paused)
            order.pause_started_ts = None
            await db.commit()
            try:
                redis.set(resume_key, "1", nx=True, ex=60)
            except Exception:
                pass

        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass

            raise HTTPException(
                status_code=500,
                detail="Failed to persist billing state",
            )
        return {"ok": True}
    finally:
        try:
            redis.delete(lock_key)
        except Exception:
            pass


@router.get("/order/{order_id}/trip-meter")
async def trip_meter(
    order_id: int,
    token: Optional[str] = Header(None, alias="X-WebApp-Token"),
    qtoken: Optional[str] = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db),
):
    """Faol safar o'lchovi: Redis + server compute_fare (klientga ishonilmaydi)."""
    t = token or qtoken
    if not t:
        raise HTTPException(status_code=403, detail="WebApp token required")
    data = verify_webapp_token(t, order_id)
    if not data:
        raise HTTPException(status_code=403, detail="Invalid or expired WebApp token")
    _, driver_id = data
    order = await OrderCRUD.get_by_id(db, order_id)
    if not order or getattr(order, "driver_id", None) != driver_id:
        raise HTTPException(status_code=403, detail="Access denied")
    redis = get_redis()
    empty = {
        "active": False,
        "distance_km": 0.0,
        "waiting_seconds": 0.0,
        "estimated_fare": None,
        "is_waiting": False,
        "status": None,
    }
    if redis is None:
        return empty
    st = get_trip_state(redis, order_id)
    if not st or int(st.get("driver_id") or 0) != driver_id:
        return empty
    snap = st.get("tariff_snapshot")
    if not snap:
        snap = getattr(order, "tariff_snapshot_json", None)
    if not snap:
        s = await _get_settings_webapp(db)
        snap = _tariff_snapshot_from_settings(s)
    # Read-only live credit for an active manual pause: if pause_started_ts is set,
    # add the elapsed paused time to waiting_seconds for THIS response only.
    # Redis state is NOT mutated here; the authoritative credit is still applied
    # exactly once in trip_resume. No double counting, because after resume
    # pause_started_ts becomes None and ws_stored already includes the full
    # paused interval.
    ws_stored = float(st.get("waiting_seconds") or 0)
    pts = st.get("pause_started_ts")
    if pts is not None:
        try:
            live_paused = max(0.0, time.time() - float(pts))
        except (TypeError, ValueError):
            live_paused = 0.0
        ws_effective = ws_stored + live_paused
    else:
        ws_effective = ws_stored

    is_waiting_mode = bool(st.get("is_waiting"))
    waiting_seconds_raw = ws_effective
    ws_for_compute_fare = ws_effective
    if settings.DEBUG:
        logger.info(
            json.dumps(
                {
                    "waiting_seconds_raw": waiting_seconds_raw,
                    "is_waiting_mode": is_waiting_mode,
                    "ws_effective": ws_for_compute_fare,
                },
                default=str,
            )
        )
    est = compute_fare(snap, float(st.get("distance_km") or 0), ws_for_compute_fare)
    _raw_surge = float(snap.get("surge_multiplier") or 1.0)
    _surge_out = max(1.0, min(2.0, _raw_surge))
    _dist_out = float(st.get("distance_km") or 0)
    _min_p = float(snap.get("base", 0) or 0)
    _km_p = float(snap.get("km", 0) or 0)
    _wait_p = float(snap.get("wait", 0) or 0)
    if settings.TRIP_METER_DEBUG:
        logger.debug(
            "[TRIP_METER_DEBUG] order_id=%s active=%s distance_km=%s waiting_seconds_stored=%s "
            "waiting_seconds_effective=%s min_price=%s price_per_km=%s price_per_min_waiting=%s "
            "surge_multiplier=%s estimated_fare=%s",
            order_id,
            True,
            _dist_out,
            ws_stored,
            ws_effective,
            _min_p,
            _km_p,
            _wait_p,
            _surge_out,
            int(est),
        )
    return {
        "active": True,
        "distance_km": _dist_out,
        "waiting_seconds": ws_effective,
        "estimated_fare": int(est),
        "is_waiting": bool(st.get("is_waiting")),
        "status": st.get("status"),
        "surge_multiplier": _surge_out,
    }


class UpdateDriverLocationBody(BaseModel):
    driver_id: int
    latitude: float
    longitude: float
    snapped_latitude: Optional[float] = None   # Haydovchi tomonidan hisoblangan snap nuqta
    snapped_longitude: Optional[float] = None  # Haydovchi tomonidan hisoblangan snap nuqta
    heading: Optional[float] = None
    order_id: Optional[int] = None


@router.post("/update_driver_location")
async def update_driver_location_api(
    body: UpdateDriverLocationBody,
    token: Optional[str] = Header(None, alias="X-WebApp-Token"),
    qtoken: Optional[str] = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db)
):
    """Haydovchi joylashuvini Redis ga yozish va yaqinlashish (50m) xabarini yuborish.

    Smart Driver Arrival:
    - 50 m dan kam qolsa, mijozga yaqinlashish xabari (oldidagi logika) yuboriladi
    - Driver Web-panelida 'Keldim' tugmasi frontend orqali faollashadi (distance < 50m)
    """
    if not _valid_coord(body.latitude, body.longitude):
        raise HTTPException(status_code=400, detail="Invalid coordinates")

    # Verify driver exists (auth when order_id is None)
    driver = await DriverCRUD.get_by_id(db, body.driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    t = token or qtoken
    if t and body.order_id is not None:
        data = verify_webapp_token(t, body.order_id)
        if not data:
            raise HTTPException(status_code=403, detail="Invalid or expired WebApp token")
        _, tok_driver_id = data
        if tok_driver_id != body.driver_id:
            raise HTTPException(status_code=403, detail="Token driver_id mismatch")

    redis = get_redis()
    if redis is not None:
        try:
            redis.set(f"web_active:{driver.id}", "1", ex=30)
        except Exception as e:
            logger.error(f"Failed to set web_active for driver {driver.id}: {e}")
    # Snapped koordinata mavjud bo'lsa — uni saqlash, aks holda raw GPS
    store_lat = body.snapped_latitude if body.snapped_latitude is not None else body.latitude
    store_lon = body.snapped_longitude if body.snapped_longitude is not None else body.longitude
    if redis is not None:
        ok = set_driver_location(redis, body.driver_id, store_lat, store_lon, body.heading)
        if not ok:
            logger.warning("Redis driver location write failed (continuing with DB update)")

    # DB-ga yozish (har 3 soniyada bir marta) - matching uchun PostGIS location + location_updated_at
    try:
        DB_WRITE_THROTTLE_SEC = 3
        should_write = True
        if redis is not None:
            throttle_key = f"driver_loc_db_throttle:{body.driver_id}"
            should_write = redis.set(throttle_key, "1", ex=DB_WRITE_THROTTLE_SEC, nx=True)
        if should_write:
            await db.execute(
                text("""
                    UPDATE drivers
                    SET
                        current_latitude = :lat,
                        current_longitude = :lon,
                        location = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                        location_updated_at = NOW()
                    WHERE id = :driver_id
                """),
                {
                    "driver_id": body.driver_id,
                    "lat": store_lat,
                    "lon": store_lon,
                },
            )
            # Snapped koordinata orders jadvaliga ham yoziladi (mijoz sahifasi uchun)
            oid_for_snap = body.order_id
            if oid_for_snap is None and redis is not None:
                _ongoing = await OrderCRUD.get_ongoing_order_for_driver(db, body.driver_id)
                if _ongoing:
                    _st = _ongoing.status.value if hasattr(_ongoing.status, "value") else _ongoing.status
                    if str(_st).lower() == "in_progress":
                        oid_for_snap = _ongoing.id
            if oid_for_snap is not None and body.snapped_latitude is not None:
                await db.execute(
                    text("""
                        UPDATE orders
                        SET snapped_lat = :slat, snapped_lon = :slon
                        WHERE id = :order_id
                    """),
                    {
                        "slat": body.snapped_latitude,
                        "slon": body.snapped_longitude,
                        "order_id": oid_for_snap,
                    }
                )
        oid = body.order_id
        if oid is None and redis is not None:
            ongoing = await OrderCRUD.get_ongoing_order_for_driver(db, body.driver_id)
            if ongoing:
                st_ord = ongoing.status.value if hasattr(ongoing.status, "value") else ongoing.status
                if str(st_ord).lower() == "in_progress":
                    oid = ongoing.id
        if redis is not None and oid is not None:
            lock_key = f"trip_lock:{oid}"
            ok = redis.set(lock_key, "1", nx=True, ex=2)
            skip_trip_state = not ok
            if not skip_trip_state:
                try:
                    st = get_trip_state(redis, oid)
                    if st and int(st.get("driver_id") or 0) == body.driver_id:
                        now_ts = time.time()
                        st_after = update_distance(st, store_lat, store_lon, now_ts)
                        st_after["is_waiting"] = st_after.get("pause_started_ts") is not None
                        st_after["updated_at"] = now_ts
                        set_trip_state(redis, oid, st_after)
                finally:
                    try:
                        redis.delete(lock_key)
                    except Exception:
                        pass
        elif oid is not None:
            logger.warning(
                f"Redis unavailable during active trip GPS update — skipping taximeter "
                f"(driver={body.driver_id}, order={oid})"
            )
        await db.commit()
    except Exception as ex:
        # Redis ishlasa ham, DB throttle yangilashda xato bo‘lsa matching vaqtincha ishlamasligi mumkin.
        # Shuning uchun warning log qilamiz, lekin endpointni fail qilmexmaymiz.
        logger.warning(f"DB driver location update xato: {ex}")
        try:
            await db.rollback()
        except Exception:
            pass

    order = await OrderCRUD.get_active_order_for_driver(db, body.driver_id)
    if not order or not order.user_id:
        return {"ok": True}
    if order_skip_customer_notifications(order):
        return {"ok": True}
    if getattr(order, "is_near_notified", False):
        return {"ok": True}
    pickup_lat = getattr(order, "pickup_latitude", None)
    pickup_lon = getattr(order, "pickup_longitude", None)
    if pickup_lat is None or pickup_lon is None:
        return {"ok": True}

    from app.utils.distance import haversine_distance
    dist_km = haversine_distance(store_lat, store_lon, float(pickup_lat), float(pickup_lon))
    if dist_km >= 0.05:
        return {"ok": True}

    try:
        from app.bot.telegram_bot import bot
        user = await UserCRUD.get_by_id(db, order.user_id)
        if user and user.telegram_id:
            from app.bot.messages import get_text as _get_text
            user_lang = getattr(user, "language_code", None) or "uz"
            msg = _get_text(user_lang, "driver_near")
            await bot.send_message(user.telegram_id, msg, parse_mode="HTML")
            await OrderCRUD.mark_near_notified(db, order.id)
            logger.info(f"📱 Proximity xabar yuborildi: order #{order.id}, user {user.telegram_id}")
    except Exception as ex:
        logger.warning(f"Proximity xabar xato: {ex}")

    return {"ok": True}


@router.get("/order/{order_id}/driver-location")
async def get_driver_location(order_id: int, db: AsyncSession = Depends(get_db)):
    """Buyurtma uchun haydovchi joylashuvini qaytarish (Redis birinchi, keyin PostgreSQL)."""
    try:
        order = await OrderCRUD.get_by_id(db, order_id)
        if not order or not getattr(order, "driver_id", None):
            return {"driver": None, "latitude": None, "longitude": None}
        driver = await DriverCRUD.get_by_id(db, order.driver_id)
        if not driver:
            return {"driver": None, "latitude": None, "longitude": None}
        user = await UserCRUD.get_by_id(db, driver.user_id) if driver.user_id else None

        # Redis'dan birinchi o'qish (snapped koordinata saqlangan bo'ladi)
        redis = get_redis()
        cached = get_driver_location_redis(redis, order.driver_id) if redis else None
        if cached:
            lat, lon = cached
        else:
            lat = getattr(driver, "current_latitude", None)
            lon = getattr(driver, "current_longitude", None)
        # orders jadvalidan snapped koordinatani olish
        snapped_lat = getattr(order, "snapped_lat", None)
        snapped_lon = getattr(order, "snapped_lon", None)
        car = getattr(driver, "car_model", "") or ""
        if getattr(driver, "car_number", None):
            car = (car + " " + str(driver.car_number)).strip()
        return {
            "driver": {"name": getattr(user, "first_name", None) or "Haydovchi", "car": car or "—"},
            "latitude": float(lat) if lat is not None else None,
            "longitude": float(lon) if lon is not None else None,
            "snapped_latitude": float(snapped_lat) if snapped_lat is not None else None,
            "snapped_longitude": float(snapped_lon) if snapped_lon is not None else None,
        }
    except Exception as e:
        logger.error(f"Driver location xato: {e}")
        return {"driver": None, "latitude": None, "longitude": None}


@router.post("/debug-log")
async def webapp_debug_log(payload: dict[str, Any]):
    """Client-side debug loglarini qabul qilish (taximeter WebApp)."""
    try:
        log_path = Path(__file__).resolve().parents[3] / "debug-8ab418.log"
        line = json.dumps({**payload, "timestamp": payload.get("timestamp")}, ensure_ascii=False) + "\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    return {"ok": True}
