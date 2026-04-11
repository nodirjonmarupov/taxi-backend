"""
Redis client - GEO support bilan.
Returns None when Redis is unavailable (graceful fallback).
"""
import json
from typing import Any, Dict, Optional

from redis import Redis
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_redis_client: Optional[Redis] = None


def get_redis() -> Optional[Redis]:
    """Redis client olish. None qaytaradi agar Redis ishlamasa."""
    global _redis_client
    if _redis_client is not None:
        try:
            _redis_client.ping()
            return _redis_client
        except Exception:
            _redis_client = None
    try:
        _redis_client = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=False,  # GEO uchun kerak
            max_connections=20,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _redis_client.ping()
        logger.info("Redis client yaratildi")
        return _redis_client
    except Exception as e:
        logger.warning(f"Redis mavjud emas: {e}")
        return None


async def close_redis():
    """Redis connection yopish"""
    global _redis_client
    
    if _redis_client:
        _redis_client.close()
        _redis_client = None
        logger.info("Redis connection yopildi")


def trip_state_key(order_id: int) -> str:
    return f"trip_state:{order_id}"


def get_trip_state(redis: Optional[Redis], order_id: int) -> Optional[Dict[str, Any]]:
    """Faol safar holati (JSON). Redis yo'q yoki xato bo'lsa None."""
    if redis is None:
        return None
    try:
        raw = redis.get(trip_state_key(order_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"get_trip_state xato: {e}")
        return None


def set_trip_state(redis: Optional[Redis], order_id: int, state: Dict[str, Any]) -> None:
    if redis is None:
        return
    try:
        redis.set(trip_state_key(order_id), json.dumps(state, default=str))
    except Exception as e:
        logger.warning(f"set_trip_state xato: {e}")


def delete_trip_state(redis: Optional[Redis], order_id: int) -> None:
    if redis is None:
        return
    try:
        redis.delete(trip_state_key(order_id))
    except Exception as e:
        logger.warning(f"delete_trip_state xato: {e}")
