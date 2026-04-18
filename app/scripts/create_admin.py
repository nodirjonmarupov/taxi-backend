"""
Panel admin yaratish (Django createsuperuser ga o'xshash).

Ishga tushirish (loyiha ildizidan):
    python -m app.scripts.create_admin
"""
from __future__ import annotations

import asyncio
import getpass
import sys


async def main() -> None:
    from sqlalchemy import func, select

    from app.core.database import AsyncSessionLocal
    from app.core.security import get_password_hash
    from app.models.user import User, UserRole

    print("Timgo Taxi — admin foydalanuvchi yaratish")
    username = input("Username: ").strip()
    if not username:
        print("Xato: username bo'sh bo'lmasligi kerak.", file=sys.stderr)
        sys.exit(1)

    pw1 = getpass.getpass("Password: ")
    pw2 = getpass.getpass("Password (again): ")
    if pw1 != pw2:
        print("Xato: parollar mos emas.", file=sys.stderr)
        sys.exit(1)
    if len(pw1) < 8:
        print("Xato: parol kamida 8 belgi bo'lishi kerak.", file=sys.stderr)
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        taken = await db.execute(select(User.id).where(User.username == username))
        if taken.scalar_one_or_none() is not None:
            print(f"Xato: '{username}' username allaqachon band.", file=sys.stderr)
            sys.exit(1)

        r = await db.execute(select(func.min(User.telegram_id)).where(User.telegram_id < 0))
        min_neg = r.scalar()
        next_tg = (min_neg - 1) if min_neg is not None else -1

        hp = get_password_hash(pw1)
        u = User(
            telegram_id=next_tg,
            username=username,
            first_name="Admin",
            last_name="",
            role=UserRole.ADMIN.value,
            is_admin=True,
            is_active=True,
            is_blocked=False,
            hashed_password=hp,
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        print(f"Muvaffaqiyatli: admin yaratildi (id={u.id}, username={username}).")


if __name__ == "__main__":
    asyncio.run(main())
