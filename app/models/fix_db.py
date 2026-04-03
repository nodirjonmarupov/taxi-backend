import asyncio
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

async def fix_database():
    print("🚀 Bazaga yangi ustunlar qo'shilmoqda...")
    async with AsyncSessionLocal() as session:
        try:
            # Finished_at ustunini qo'shish
            await session.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP;"))
            await session.commit()
            print("✅ Muvaffaqiyatli yakunlandi! 'finished_at' ustuni qo'shildi.")
        except Exception as e:
            print(f"❌ Xatolik yuz berdi: {e}")

if __name__ == "__main__":
    asyncio.run(fix_database())