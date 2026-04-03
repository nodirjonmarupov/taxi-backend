"""
Bir martalik (test): barcha haydovchilarni matching uchun \"tayyor\" holatga.
  is_available = true, status = 'active'

Ishga tushirish: loyiha ildizidan
  python scripts/reset_drivers_for_matching_test.py

Env: DATABASE_URL (postgresql+asyncpg → asyncpg uchun DSN ga aylantiriladi)
"""
from __future__ import annotations

import os
import sys

import asyncpg


def _dsn() -> str:
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/taxi_db",
    )
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


async def _run() -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        n = await conn.execute(
            """
            UPDATE drivers
            SET is_available = true,
                status = 'active'
            WHERE is_active = true
            """
        )
        print(f"OK: {n}")
    finally:
        await conn.close()


def main() -> None:
    import asyncio

    asyncio.run(_run())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Xato: {e}", file=sys.stderr)
        sys.exit(1)
