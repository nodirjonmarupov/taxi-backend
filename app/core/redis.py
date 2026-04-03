"""
Redis client - GEO support bilan.
Returns None when Redis is unavailable (graceful fallback).
"""
from redis import Redis
from typing import Optional
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
