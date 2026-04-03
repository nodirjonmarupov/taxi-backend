"""
Orders API V2 - Real-time matching bilan
Professional Taximeter Integration
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.core.database import get_db
from app.core.redis import get_redis
from app.crud.order_crud import OrderCRUD
from app.crud.user import DriverCRUD
from app.schemas.order import OrderCreate, OrderResponse
from app.services.geo_service import GeoService
from app.services.order_matching import start_matching_background_task
from app.services.telegram_notifications import TelegramNotificationService
from app.services.pricing_service import PricingService
from app.core.logger import get_logger
from app.models.order import OrderStatus

logger = get_logger(__name__)

router = APIRouter(prefix="/orders", tags=["orders"])

@router.post("", response_model=OrderResponse)
async def create_order_with_matching(
    order_data: OrderCreate,
    user_id: int = Query(..., description="User ID (from auth context)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Buyurtma yaratish va avtomatik haydovchi qidirish.
    """
    dest_lat = order_data.destination_latitude if order_data.destination_latitude is not None else order_data.pickup_latitude
    dest_lon = order_data.destination_longitude if order_data.destination_longitude is not None else order_data.pickup_longitude
    distance_km, estimated_price = await PricingService.estimate_trip_price(
        db,
        order_data.pickup_latitude,
        order_data.pickup_longitude,
        dest_lat,
        dest_lon,
    )
    order_data.estimated_price = estimated_price
    order_data.distance_km = distance_km
    
    # Buyurtmani bazada yaratish
    order = await OrderCRUD.create(db, user_id, order_data)
    logger.info(f"Yangi buyurtma yaratildi ID: {order.id}")
    
    # Background task - haydovchi qidirishni boshlash (Redis mavjud bo'lsa)
    redis = get_redis()
    if redis is not None:
        geo_service = GeoService(redis)
        from app.bot.telegram_bot_v2 import bot
        notification_service = TelegramNotificationService(bot)
        asyncio.create_task(
            start_matching_background_task(
                db=db,
                geo_service=geo_service,
                notification_service=notification_service,
                order_id=order.id,
                pickup_lat=order_data.pickup_latitude,
                pickup_lon=order_data.pickup_longitude
            )
        )
    
    return order

@router.post("/{order_id}/accept")
async def accept_order(
    order_id: int,
    driver_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Haydovchi buyurtmani qabul qilishi.
    SELECT FOR UPDATE bilan race condition oldini olinadi.
    """
    order = await OrderCRUD.get_by_id_for_update(db, order_id)

    if not order:
        raise HTTPException(404, "Buyurtma topilmadi")

    if order.status != OrderStatus.PENDING:
        raise HTTPException(400, "Buyurtma allaqachon qabul qilingan yoki bekor qilingan")

    driver = await DriverCRUD.get_by_id(db, driver_id)
    if not driver:
        raise HTTPException(404, "Haydovchi topilmadi")

    existing = await OrderCRUD.get_ongoing_order_for_driver(db, driver_id)
    if existing and existing.id != order_id:
        raise HTTPException(400, "Haydovchida allaqachon faol buyurtma bor")

    order.status = OrderStatus.ACCEPTED
    order.driver_id = driver_id
    await db.commit()
    
    # Mijozga Telegram orqali xabar yuborish
    from app.bot.telegram_bot_v2 import bot
    notification_service = TelegramNotificationService(bot)
    
    await notification_service.send_order_accepted_to_user(
        user_id=order.user_id,
        order_id=order.id,
        driver_name=f"{driver.user.first_name} {driver.user.last_name or ''}",
        driver_phone=driver.user.phone or "Noma'lum",
        car_model=driver.car_model,
        car_number=driver.car_number,
        rating=driver.rating # Haydovchining joriy reytingini yuboramiz
    )
    
    logger.info(f"Order {order_id} haydovchi {driver_id} tomonidan qabul qilindi")
    return {"status": "accepted", "order_id": order_id, "driver_id": driver_id}

@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Buyurtma haqida to'liq ma'lumot olish"""
    order = await OrderCRUD.get_by_id(db, order_id)
    if not order:
        raise HTTPException(404, "Buyurtma topilmadi")
    return order

@router.get("/{order_id}/status")
async def get_order_status(
    order_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Haydovchi uchun maxsus: Safar yakunida ball (rating) ni ko'rish.
    """
    order = await OrderCRUD.get_by_id(db, order_id)
    if not order:
        raise HTTPException(404, "Buyurtma topilmadi")
    
    return {
        "id": order.id,
        "status": order.status,
        "estimated_price": order.estimated_price,
        "finished_at": order.finished_at
    }

@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Buyurtmani bekor qilish"""
    order = await OrderCRUD.get_by_id(db, order_id)
    
    if not order:
        raise HTTPException(404, "Buyurtma topilmadi")
    
    if order.status in [OrderStatus.COMPLETED, OrderStatus.CANCELLED]:
        raise HTTPException(400, "Yakunlangan buyurtmani bekor qilib bo'lmaydi")
    
    order.status = OrderStatus.CANCELLED
    await db.commit()
    
    logger.info(f"Order {order_id} bekor qilindi")
    return {"status": "cancelled", "order_id": order_id}

@router.get("/user/{user_id}")
async def get_user_orders(
    user_id: int,
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    """Foydalanuvchining oxirgi buyurtmalari ro'yxati"""
    orders = await OrderCRUD.get_user_orders(db, user_id, limit)
    return orders