"""
Order Matching Service - Buyurtmalarni avtomatik driver'ga biriktirish
O'zbek: Buyurtmani yaqin driver'ga avtomatik yuborish
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.services.geo_service import GeoService
from app.crud.order_crud import OrderCRUD
from app.crud.user import DriverCRUD
from app.models.order import OrderStatus

logger = get_logger(__name__)


class OrderMatchingService:
    """
    Buyurtmalarni driver'larga avtomatik biriktirish servisi.
    
    Features:
    - Eng yaqin driver'ni topish
    - Avtomatik notification yuborish
    - 15 soniya timeout
    - Keyingi driver'ga o'tish
    """
    
    TIMEOUT_SECONDS = 15  # Driver javob berish vaqti
    MAX_ATTEMPTS = 5  # Maksimal urinishlar soni
    
    def __init__(
        self,
        db: AsyncSession,
        geo_service: GeoService,
        notification_service
    ):
        """
        Args:
            db: Database session
            geo_service: GEO servis
            notification_service: Telegram notification servis
        """
        self.db = db
        self.geo = geo_service
        self.notifier = notification_service
    
    async def match_order(
        self,
        order_id: int,
        pickup_lat: float,
        pickup_lon: float,
        radius_km: float = 1.0
    ) -> bool:
        """
        Buyurtmani yaqin driver'ga biriktirish.
        
        Process:
        1. Yaqin driver'larni topish
        2. Birinchi driver'ga yuborish
        3. 15 soniya kutish
        4. Javob yo'q bo'lsa keyingi driver'ga o'tish
        5. 5 ta urinishdan keyin bekor qilish
        
        Args:
            order_id: Buyurtma ID
            pickup_lat: Olib ketish joyning kenglik
            pickup_lon: Olib ketish joyning uzunlik
            radius_km: Qidirish radiusi
            
        Returns:
            bool: Muvaffaqiyatli biriktrilsa True
        """
        logger.info(f"Buyurtma {order_id} uchun driver qidirilmoqda...")
        
        # Yaqin driver'larni topish
        nearby_drivers = await self.geo.find_nearest_drivers(
            pickup_lat,
            pickup_lon,
            radius_km,
            count=self.MAX_ATTEMPTS
        )
        
        if not nearby_drivers:
            logger.warning(f"Buyurtma {order_id} uchun yaqin driver topilmadi")
            await self._mark_order_failed(order_id, "Driver topilmadi")
            return False
        
        logger.info(f"Topildi {len(nearby_drivers)} ta driver")
        
        # Har bir driver'ga ketma-ket yuborish
        for attempt, driver_info in enumerate(nearby_drivers, 1):
            driver_id = driver_info['driver_id']
            distance = driver_info['distance']
            
            logger.info(
                f"Urinish {attempt}/{len(nearby_drivers)}: "
                f"Driver {driver_id}ga yuborilmoqda (masofa: {distance} km)"
            )
            
            # Driver'ga yuborish va javob kutish
            accepted = await self._send_to_driver_and_wait(
                order_id,
                driver_id,
                distance
            )
            
            if accepted:
                logger.info(f"✅ Driver {driver_id} buyurtmani qabul qildi!")
                return True
            
            logger.warning(
                f"❌ Driver {driver_id} javob bermadi yoki rad etdi. "
                f"Keyingi driver'ga o'tilmoqda..."
            )
        
        # Hech qaysi driver qabul qilmadi
        logger.error(
            f"Buyurtma {order_id} rad etildi: "
            f"{len(nearby_drivers)} ta driver javob bermadi"
        )
        await self._mark_order_failed(
            order_id,
            f"{len(nearby_drivers)} ta driver javob bermadi"
        )
        return False
    
    async def _send_to_driver_and_wait(
        self,
        order_id: int,
        driver_id: int,
        distance: float
    ) -> bool:
        """
        Driver'ga notification yuborish va javob kutish.
        
        Args:
            order_id: Buyurtma ID
            driver_id: Driver ID
            distance: Masofa (km)
            
        Returns:
            bool: Driver qabul qilsa True
        """
        # Database'dan buyurtma ma'lumotlarini olish
        order = await OrderCRUD.get_by_id(self.db, order_id)
        if not order:
            return False
        
        # Driver'ga notification yuborish
        await self.notifier.send_new_order_to_driver(
            driver_id=driver_id,
            order_id=order_id,
            distance=distance,
            pickup_address=order.pickup_address,
            destination_address=order.destination_address,
            estimated_price=order.estimated_price
        )
        
        # 15 soniya davomida javob kutish
        timeout = timedelta(seconds=self.TIMEOUT_SECONDS)
        deadline = datetime.utcnow() + timeout
        
        while datetime.utcnow() < deadline:
            # Buyurtma holatini tekshirish
            await self.db.refresh(order)
            
            if order.status == OrderStatus.ACCEPTED:
                if order.driver_id == driver_id:
                    return True
            
            elif order.status == OrderStatus.CANCELLED:
                return False
            
            # 0.5 soniya kutish
            await asyncio.sleep(0.5)
        
        # Timeout - javob yo'q
        return False
    
    async def _mark_order_failed(
        self,
        order_id: int,
        reason: str
    ) -> None:
        """
        Haydovchi topilmaganda buyurtmani bekor qilish va mijozga "taxi yo'q" xabarini yuborish.
        
        Args:
            order_id: Buyurtma ID
            reason: Sabab
        """
        try:
            order = await OrderCRUD.get_by_id(self.db, order_id)
            if order and order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CANCELLED
                order.notes = f"Avtomatik bekor qilindi: {reason}"
                await self.db.commit()
                await self.notifier.send_order_failed_to_user(
                    user_id=order.user_id,
                    reason="Hozir taxi yo'q. Keyinroq urinib ko'ring."
                )
                logger.info(f"Buyurtma {order_id} bekor qilindi: {reason}")
        except Exception as e:
            logger.error(f"Buyurtmani bekor qilishda xato: {e}")


async def start_matching_background_task(
    db: AsyncSession,
    geo_service: GeoService,
    notification_service,
    order_id: int,
    pickup_lat: float,
    pickup_lon: float
) -> None:
    """
    Background task - buyurtmani driver'ga biriktirish.
    
    Bu funksiya asinxron ravishda ishga tushiriladi.
    
    Args:
        db: Database session
        geo_service: GEO servis
        notification_service: Notification servis
        order_id: Buyurtma ID
        pickup_lat: Olib ketish joy - kenglik
        pickup_lon: Olib ketish joy - uzunlik
    """
    service = OrderMatchingService(db, geo_service, notification_service)
    
    try:
        await service.match_order(order_id, pickup_lat, pickup_lon)
    except Exception as e:
        logger.error(f"Matching background task xato: {e}")
        await service._mark_order_failed(order_id, f"Tizim xatosi: {str(e)}")
