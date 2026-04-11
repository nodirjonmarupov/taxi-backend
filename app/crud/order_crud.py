"""
Order modeli uchun CRUD amallari.
Barcha funksiyalar OrderCRUD klassi ichiga jamlangan.
"""
from typing import Any, Optional, List
from datetime import datetime, timedelta
from sqlalchemy import select, update, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import Order, OrderStatus
from app.models.user import Driver
from app.schemas.order import OrderCreate, OrderUpdate

class OrderCRUD:
    @staticmethod
    async def create(db: AsyncSession, user_id: int, order_data: OrderCreate) -> Order:
        """Yangi buyurtma yaratish"""
        order = Order(
            **order_data.model_dump(),
            user_id=user_id,
            status=OrderStatus.PENDING
        )
        db.add(order)
        await db.commit()
        await db.refresh(order)
        return order

    @staticmethod
    async def get_by_id_for_update(db: AsyncSession, order_id: int) -> Optional[Order]:
        """Buyurtmani SELECT FOR UPDATE bilan olish - race condition oldini olish uchun."""
        stmt = select(Order).where(Order.id == order_id).with_for_update()
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, order_id: int) -> Optional[Order]:
        """Buyurtmani ID bo'yicha olish (oddiy select - user/driver kerak bo'lsa alohida UserCRUD/DriverCRUD orqali)"""
        try:
            stmt = select(Order).where(Order.id == order_id)
            if hasattr(Order, "user") and hasattr(Order, "driver"):
                stmt = stmt.options(
                    selectinload(Order.user),
                    selectinload(Order.driver).selectinload(Driver.user)
                )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            from app.core.logger import get_logger
            get_logger(__name__).warning(f"get_by_id selectinload xato: {e}, oddiy selectga o'tamiz")
            result = await db.execute(select(Order).where(Order.id == order_id))
            return result.scalar_one_or_none()

    @staticmethod
    async def get_multi(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        driver_id: Optional[int] = None,
        user_id: Optional[int] = None,
        status: Optional[str] = None
    ) -> List[Order]:
        stmt = select(Order)
        if driver_id is not None:
            stmt = stmt.where(Order.driver_id == driver_id)
        if user_id is not None:
            stmt = stmt.where(Order.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Order.status == status)
        stmt = stmt.order_by(Order.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_rating(db: AsyncSession, order_id: int, rating: int) -> Optional[Order]:
        """Buyurtma tugash vaqtini saqlash (rating ratings jadvalida saqlanadi)."""
        await db.execute(
            update(Order)
            .where(Order.id == order_id)
            .values(finished_at=datetime.utcnow())
        )
        await db.commit()
        return await OrderCRUD.get_by_id(db, order_id)

    @staticmethod
    async def update_status(
        db: AsyncSession,
        order_id: int,
        status: OrderStatus,
        driver_id: Optional[int] = None,
        distance_km: Optional[float] = None,
        final_price: Optional[float] = None,
        updated_at: Optional[datetime] = None,
        apply_taximeter_start: bool = False,
        trip_start_lat: Optional[float] = None,
        trip_start_lon: Optional[float] = None,
        tariff_snapshot_json: Optional[Any] = None,
    ) -> Optional[Order]:
        """Buyurtma holatini yangilash. distance_km > 1000 bo'lsa 0 saqlanadi."""
        update_data = {"status": status}

        if status == OrderStatus.ACCEPTED and driver_id:
            update_data["driver_id"] = driver_id
            update_data["accepted_at"] = datetime.utcnow()
        elif status == OrderStatus.IN_PROGRESS:
            if apply_taximeter_start:
                update_data["started_at"] = datetime.utcnow()
                if trip_start_lat is not None and trip_start_lon is not None:
                    update_data["last_lat"] = trip_start_lat
                    update_data["last_lon"] = trip_start_lon
                    update_data["distance_km"] = 0.0
        elif status == OrderStatus.COMPLETED:
            update_data["finished_at"] = datetime.utcnow()
            if distance_km is not None:
                update_data["distance_km"] = 0.0 if distance_km > 1000 else distance_km
            if final_price is not None:
                update_data["final_price"] = final_price
            if tariff_snapshot_json is not None:
                update_data["tariff_snapshot_json"] = tariff_snapshot_json
        elif status == OrderStatus.CANCELLED:
            update_data["cancelled_at"] = datetime.utcnow()

        if updated_at is not None:
            update_data["updated_at"] = updated_at

        await db.execute(
            update(Order)
            .where(Order.id == order_id)
            .values(**update_data)
        )
        await db.commit()
        return await OrderCRUD.get_by_id(db, order_id)

    @staticmethod
    async def cancel_expired_orders(db: AsyncSession):
        """30 daqiqadan ko'proq PENDING holatida qolib ketgan buyurtmalarni avtomatik bekor qilish.
        PostgreSQL ENUM (orderstatus) va VARCHAR ustunlar bilan ham ishlaydi."""
        expiry_time = datetime.utcnow() - timedelta(minutes=30)
        pending = OrderStatus.PENDING.value
        cancelled = OrderStatus.CANCELLED.value

        try:
            # Avval ORM orqali urinamiz (VARCHAR ustunlar uchun)
            query = (
                update(Order)
                .where(Order.status == OrderStatus.PENDING)
                .where(Order.created_at < expiry_time)
                .values(status=OrderStatus.CANCELLED)
            )
            await db.execute(query)
        except Exception:
            await db.rollback()
            # orders.status endi VARCHAR - faqat eski orderstatus ENUM uchun raw SQL (fallback)
            await db.execute(
                text("""
                    UPDATE orders
                    SET status = CAST(:cancelled AS orderstatus)
                    WHERE status = CAST(:pending AS orderstatus)
                    AND created_at < :expiry
                """),
                {"cancelled": cancelled, "pending": pending, "expiry": expiry_time}
            )
        await db.commit()

    @staticmethod
    async def get_active_order_for_driver(db: AsyncSession, driver_id: int):
        """Haydovchining faol buyurtmasi (status accepted - mijozga yetib kelish bosqichi)."""
        result = await db.execute(
            select(Order)
            .where(Order.driver_id == driver_id)
            .where(Order.status == OrderStatus.ACCEPTED)
            .options(selectinload(Order.user))
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_ongoing_order_for_driver(db: AsyncSession, driver_id: int):
        """Haydovchining davom etayotgan buyurtmasi (accepted yoki in_progress)."""
        result = await db.execute(
            select(Order)
            .where(Order.driver_id == driver_id)
            .where(Order.status.in_([OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]))
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_near_notified(db: AsyncSession, order_id: int) -> None:
        """Buyurtmaga yaqinlashish xabari yuborilganini belgilash."""
        await db.execute(update(Order).where(Order.id == order_id).values(is_near_notified=True))
        await db.commit()

    @staticmethod
    async def get_active_orders(db: AsyncSession) -> List[Order]:
        """Hozirgi vaqtda faol bo'lgan barcha buyurtmalar ro'yxati"""
        result = await db.execute(
            select(Order).where(
                Order.status.in_([
                    OrderStatus.PENDING, 
                    OrderStatus.ACCEPTED, 
                    OrderStatus.IN_PROGRESS
                ])
            ).order_by(Order.created_at.desc())
        )
        return list(result.scalars().all())

# --- QO'SHIMCHA: Funksiya sifatida import qilish imkoniyati ---
# Masalan: from app.crud.order_crud import update_rating, get_order_by_id
get_order_by_id = OrderCRUD.get_by_id
update_rating = OrderCRUD.update_rating
cancel_expired_orders = OrderCRUD.cancel_expired_orders