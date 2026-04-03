"""
Database Migration - Yangi ustunlarni qo'shish
"""
import asyncio
from sqlalchemy import text
from app.core.database import engine


async def migrate():
    """Migratsiya"""
    print("🔄 Migratsiya boshlanmoqda...")
    
    async with engine.begin() as conn:
        # Users table
        print("📝 Users table...")
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_approved_driver BOOLEAN DEFAULT FALSE"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS language_code VARCHAR(10)"
        ))
        
        # Drivers table
        print("📝 Drivers table...")
        await conn.execute(text(
            "ALTER TABLE drivers ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'pending'"
        ))
        await conn.execute(text(
            "ALTER TABLE drivers ADD COLUMN IF NOT EXISTS balance NUMERIC(10,2) DEFAULT 0.0"
        ))
        await conn.execute(text(
            "ALTER TABLE drivers ADD COLUMN IF NOT EXISTS min_balance_required NUMERIC(10,2) DEFAULT 10000.0"
        ))
        await conn.execute(text(
            "ALTER TABLE drivers ADD COLUMN IF NOT EXISTS has_active_card BOOLEAN DEFAULT FALSE"
        ))
        await conn.execute(text(
            "ALTER TABLE drivers ADD COLUMN IF NOT EXISTS car_year INTEGER"
        ))
        await conn.execute(text(
            "ALTER TABLE drivers ADD COLUMN IF NOT EXISTS car_photo_id VARCHAR(200)"
        ))
        await conn.execute(text(
            "ALTER TABLE drivers ADD COLUMN IF NOT EXISTS completed_trips INTEGER DEFAULT 0"
        ))
        await conn.execute(text(
            "ALTER TABLE drivers ADD COLUMN IF NOT EXISTS total_commission_paid NUMERIC(12,2) DEFAULT 0.0"
        ))
        
        # Balance Transactions table
        print("📝 Balance Transactions table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS balance_transactions (
                id SERIAL PRIMARY KEY,
                driver_id INTEGER NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,
                transaction_type VARCHAR(50) NOT NULL,
                amount NUMERIC(10,2) NOT NULL,
                balance_before NUMERIC(10,2) NOT NULL,
                balance_after NUMERIC(10,2) NOT NULL,
                order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL,
                payment_id VARCHAR(255),
                description VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        print("✅ Migratsiya tugadi!")


if __name__ == "__main__":
    asyncio.run(migrate())