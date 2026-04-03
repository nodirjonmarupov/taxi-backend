"""
Redis GEO Service - Driver location real-time tracking
"""
from typing import List, Optional, Tuple
from redis import Redis
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

class GeoService:
    """
    Redis GEO orqali driver'lar lokatsiyasini boshqarish.
    """
    
    DRIVERS_GEO_KEY = "drivers:locations" 
    DRIVER_STATUS_KEY = "driver:status:{driver_id}" 

    def __init__(self, redis_client: Redis):
        self.redis = redis_client

    async def set_driver_location(
        self,
        driver_id: int,
        latitude: float,
        longitude: float
    ) -> bool:
        try:
            # Redis GEO ga qo'shish (longitude, latitude tartibida)
            self.redis.geoadd(
                self.DRIVERS_GEO_KEY,
                (longitude, latitude, f"driver:{driver_id}")
            )
            
            # Driver'ni online qilish
            await self.set_driver_online(driver_id)
            
            logger.info(f"Driver {driver_id} lokatsiya yangilandi: {latitude}, {longitude}")
            return True
        except Exception as e:
            logger.error(f"Driver lokatsiya saqlashda xato: {e}")
            return False

    async def find_nearest_drivers(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 100.0,
        count: int = 20
    ) -> List[dict]:
        """
        Eng yaqin driver'larni topish (100km radiusda).
        """
        try:
            results = self.redis.georadius(
                self.DRIVERS_GEO_KEY,
                longitude,
                latitude,
                radius_km,
                unit='km',
                withdist=True,
                withcoord=True,
                sort='ASC',
                count=count
            )
            
            drivers = []
            for result in results:
                member, distance, coords = result
                driver_id_str = member.decode('utf-8').split(':')[1]
                driver_id = int(driver_id_str)
                
                # Faqat online bo'lganlarni saralash
                if await self.is_driver_online(driver_id):
                    drivers.append({
                        'driver_id': driver_id,
                        'distance': round(distance, 2),
                        'latitude': coords[1],
                        'longitude': coords[0]
                    })
            
            logger.info(f"Topildi {len(drivers)} ta yaqin driver (Radius: {radius_km}km)")
            return drivers
        except Exception as e:
            logger.error(f"Driver qidirishda xato: {e}")
            return []

    async def set_driver_online(self, driver_id: int) -> bool:
        try:
            key = self.DRIVER_STATUS_KEY.format(driver_id=driver_id)
            # 10 daqiqa davomida online (600 soniya)
            self.redis.setex(key, 600, "online")
            return True
        except Exception as e:
            logger.error(f"Driver online qilishda xato: {e}")
            return False

    async def is_driver_online(self, driver_id: int) -> bool:
        try:
            key = self.DRIVER_STATUS_KEY.format(driver_id=driver_id)
            status = self.redis.get(key)
            return status is not None and status.decode('utf-8') == "online"
        except Exception as e:
            logger.error(f"Driver status tekshirishda xato: {e}")
            return False

    async def set_driver_offline(self, driver_id: int) -> bool:
        try:
            self.redis.zrem(self.DRIVERS_GEO_KEY, f"driver:{driver_id}")
            key = self.DRIVER_STATUS_KEY.format(driver_id=driver_id)
            self.redis.delete(key)
            logger.info(f"Driver {driver_id} offline qilindi")
            return True
        except Exception as e:
            logger.error(f"Driver offline qilishda xato: {e}")
            return False