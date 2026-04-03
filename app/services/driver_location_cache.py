"""
Redis driver location cache - driver_loc:{driver_id}
TTL: 5 daqiqa (300s) - haydovchi ilovani yopsa ma'lumot avtomatik o'chadi
"""
import json
from typing import Optional, Tuple
from redis import Redis

from app.core.logger import get_logger

logger = get_logger(__name__)

DRIVER_LOC_KEY = "driver_loc:{driver_id}"
DRIVER_LOC_TTL = 300  # 5 daqiqa


def set_driver_location(redis: Redis, driver_id: int, lat: float, lon: float, heading: Optional[float] = None) -> bool:
    """Redis'ga haydovchi joylashuvini yozish (TTL 5 min)"""
    try:
        key = DRIVER_LOC_KEY.format(driver_id=driver_id)
        payload = {"lat": lat, "lon": lon}
        if heading is not None:
            payload["heading"] = heading
        value = json.dumps(payload).encode("utf-8")
        redis.setex(key, DRIVER_LOC_TTL, value)
        return True
    except Exception as e:
        logger.error(f"Driver location Redis yozish xato: {e}")
        return False


def get_driver_location(redis: Redis, driver_id: int) -> Optional[Tuple[float, float]]:
    """Redis'dan haydovchi joylashuvini o'qish. (lat, lon) yoki None"""
    try:
        key = DRIVER_LOC_KEY.format(driver_id=driver_id)
        raw = redis.get(key)
        if not raw:
            return None
        data = json.loads(raw.decode("utf-8"))
        lat = data.get("lat")
        lon = data.get("lon")
        if lat is None or lon is None:
            return None
        return float(lat), float(lon)
    except Exception as e:
        logger.error(f"Driver location Redis o'qish xato: {e}")
        return None
