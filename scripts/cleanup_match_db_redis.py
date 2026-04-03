"""
Bir martalik: orders (driver 1 stuck) -> cancelled; driver 1 -> active; Redis FLUSHALL.
Ishga tushirish: loyiha ildizidan `python scripts/cleanup_match_db_redis.py`
Env: DATABASE_URL, REDIS_URL (docker-compose bilan localhost:5432 / localhost:6379)
"""
from __future__ import annotations

import os
import sys

import asyncpg
import redis


def _asyncpg_dsn() -> str:
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/taxi_db",
    )
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


async def _run() -> None:
    dsn = _asyncpg_dsn()
    conn = await asyncpg.connect(dsn)
    try:
        u1 = await conn.execute(
            """
            UPDATE orders
            SET status = 'cancelled'
            WHERE driver_id = 1
              AND status IN ('accepted', 'in_progress')
            """
        )
        u2 = await conn.execute(
            """
            UPDATE drivers
            SET status = 'active',
                is_available = true,
                is_active = true,
                location_updated_at = NOW()
            WHERE id = 1
            """
        )
        print(f"orders update: {u1}")
        print(f"drivers update: {u2}")
    finally:
        await conn.close()

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    r = redis.Redis.from_url(redis_url, decode_responses=False)
    r.flushall()
    print("Redis: FLUSHALL done.")


def main() -> None:
    import asyncio

    asyncio.run(_run())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Xato: {e}", file=sys.stderr)
        sys.exit(1)
