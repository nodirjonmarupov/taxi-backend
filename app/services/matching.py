"""
Driver matching service for finding nearest available drivers.
Implements distance-based matching algorithm.
"""
from typing import Optional, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models.user import Driver
from app.models.order import Order, OrderStatus
from app.crud.user import DriverCRUD
from app.crud.order_crud import OrderCRUD
from app.utils.distance import haversine_distance
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class DriverMatchingService:
    """Service for matching drivers to orders."""
    
    @staticmethod
    async def find_nearest_driver(
        db: AsyncSession,
        order: Order,
        max_distance_km: float = None
    ) -> Optional[Driver]:
        """
        Find the nearest available driver for an order.
        
        Args:
            db: Database session
            order: Order to match
            max_distance_km: Maximum search radius (uses config default if None)
            
        Returns:
            Nearest available driver or None
        """
        if max_distance_km is None:
            max_distance_km = settings.SEARCH_RADIUS_KM
        
        # Get all available drivers
        available_drivers = await DriverCRUD.get_available_drivers(db)
        
        if not available_drivers:
            logger.warning(f"No available drivers for order {order.id}")
            return None
        
        # Calculate distances and find nearest
        nearest_driver = None
        min_distance = float('inf')
        
        for driver in available_drivers:
            # Skip drivers without location
            if driver.current_latitude is None or driver.current_longitude is None:
                continue
            
            # Calculate distance
            distance = haversine_distance(
                order.pickup_latitude,
                order.pickup_longitude,
                driver.current_latitude,
                driver.current_longitude
            )
            
            # Check if within range and closer than current nearest
            if distance <= max_distance_km and distance < min_distance:
                min_distance = distance
                nearest_driver = driver
        
        if nearest_driver:
            logger.info(
                f"Found driver {nearest_driver.id} for order {order.id} "
                f"at distance {min_distance:.2f} km"
            )
        else:
            logger.warning(
                f"No drivers within {max_distance_km} km for order {order.id}"
            )
        
        return nearest_driver
    
    @staticmethod
    async def find_multiple_drivers(
        db: AsyncSession,
        order: Order,
        count: int = 5,
        max_distance_km: float = None
    ) -> List[tuple[Driver, float]]:
        """
        Find multiple nearest available drivers for an order.
        
        Args:
            db: Database session
            order: Order to match
            count: Number of drivers to return
            max_distance_km: Maximum search radius
            
        Returns:
            List of (driver, distance) tuples sorted by distance
        """
        if max_distance_km is None:
            max_distance_km = settings.SEARCH_RADIUS_KM
        
        # Get all available drivers
        available_drivers = await DriverCRUD.get_available_drivers(db)
        
        if not available_drivers:
            return []
        
        # Calculate distances
        driver_distances = []
        
        for driver in available_drivers:
            # Skip drivers without location
            if driver.current_latitude is None or driver.current_longitude is None:
                continue
            
            # Calculate distance
            distance = haversine_distance(
                order.pickup_latitude,
                order.pickup_longitude,
                driver.current_latitude,
                driver.current_longitude
            )
            
            # Add if within range
            if distance <= max_distance_km:
                driver_distances.append((driver, distance))
        
        # Sort by distance and return top N
        driver_distances.sort(key=lambda x: x[1])
        return driver_distances[:count]

    @staticmethod
    async def find_nearest_drivers_postgis(
        db: AsyncSession,
        pickup_lat: float,
        pickup_lon: float,
        *,
        radius_km: Optional[float] = None,
        count: int = 5,
        exclude_user_id: Optional[int] = None,
        location_age_seconds: int = 30,
    ) -> List[Tuple[Driver, float]]:
        """
        PostGIS orqali eng yaqin haydovchilarni topish.

        Filtrlash (doim):
          - status='active', is_available=True, is_active=True, location IS NOT NULL
        MATCHING_TEST_MODE=True bo'lsa:
          - location_updated_at va osilgan buyurtma (NOT EXISTS) filtrlari o'chiriladi.
        Aks holda:
          - location_updated_at yoshi va faol buyurtmasi yo'qligi qo'llanadi.
        Saralash: masofa bo'yicha ASC (ST_Distance).
        """
        if radius_km is None:
            radius_km = settings.SEARCH_RADIUS_KM

        radius_m = float(radius_km) * 1000.0
        location_age_seconds = int(location_age_seconds)

        relax_verified = getattr(settings, "RELAX_VERIFIED_FOR_MATCHING", True)
        # exclude_user_id SQL da vaqtincha o'chirilgan (bir akkaunt test)
        _ = exclude_user_id

        test_mode = getattr(settings, "MATCHING_TEST_MODE", False)
        if test_mode:
            # Lokatsiya "yoshi" va osilib qolgan buyurtma filtrlari o'chirilgan (faqat test)
            effective_age = int(getattr(settings, "MATCHING_LOCATION_AGE_SECONDS", 36000))
            freshness_sql = ""
            stuck_orders_sql = ""
            location_age_seconds = effective_age  # log uchun
        else:
            effective_age = int(location_age_seconds)
            freshness_sql = (
                "AND d.location_updated_at >= "
                "(NOW() - (:age_seconds * INTERVAL '1 second'))"
            )
            stuck_orders_sql = """
              AND NOT EXISTS (
                SELECT 1 FROM orders o
                WHERE o.driver_id = d.id
                  AND o.status IN ('accepted', 'in_progress')
              )"""

        # Driver id + distance_km (radius ichida). test_mode: faqat active/available + PostGIS masofa.
        sql = text(f"""
            SELECT
                d.id AS driver_id,
                (ST_Distance(
                    d.location,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                ) / 1000.0) AS distance_km
            FROM drivers d
            WHERE d.status = 'active'
              AND d.is_available = true
              AND d.is_active = true
              AND (d.is_verified = true OR CAST(:relax_verified AS BOOLEAN) = true)
              AND d.location IS NOT NULL
              {freshness_sql}
              AND ST_DWithin(
                    d.location,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    :radius_m
              )
              AND (1=1)
              {stuck_orders_sql}
            ORDER BY distance_km ASC
            LIMIT :limit
        """)

        params = {
            "lat": float(pickup_lat),
            "lon": float(pickup_lon),
            "radius_m": radius_m,
            "limit": int(count),
            "relax_verified": relax_verified,
        }
        if not test_mode:
            params["age_seconds"] = effective_age

        logger.info(
            f"PostGIS qidiruv: pickup=({pickup_lat:.4f},{pickup_lon:.4f}) "
            f"radius={radius_km}km "
            f"test_mode={test_mode} "
            + (
                f"age_filter=OFF stuck_filter=OFF"
                if test_mode
                else f"age<={effective_age}s stuck_filter=ON"
            )
        )
        try:
            rows = (await db.execute(sql, params)).all()
        except Exception as e:
            # asyncpg/Postgresda bitta statement xato bo'lsa session tranzaksiya "aborted" bo'lib qoladi.
            # Keyingi commit/update ishlashi uchun rollback shart.
            try:
                await db.rollback()
            except Exception:
                pass
            logger.error(f"PostGIS matching xato: {e}")
            return []

        if not rows:
            logger.warning(
                f"PostGIS 0 haydovchi: pickup=({pickup_lat:.4f},{pickup_lon:.4f}) "
                f"radius={radius_km}km test_mode={test_mode} "
                f"age_log={location_age_seconds}s"
            )
            return []

        driver_ids = [int(r.driver_id) for r in rows]

        # User — order_handlers da alohida batch yuklanadi (async + lazy load yo'q).
        q = select(Driver).where(Driver.id.in_(driver_ids))
        drivers = (await db.execute(q)).scalars().all()
        driver_by_id = {d.id: d for d in drivers}

        out: List[Tuple[Driver, float]] = []
        for r in rows:
            d = driver_by_id.get(int(r.driver_id))
            if d is not None:
                out.append((d, float(r.distance_km)))
        return out
    
    @staticmethod
    async def assign_driver_to_order(
        db: AsyncSession,
        order_id: int,
        driver_id: int
    ) -> Optional[Order]:
        """
        Assign a driver to an order.
        
        Args:
            db: Database session
            order_id: Order ID
            driver_id: Driver ID
            
        Returns:
            Updated order or None
        """
        # Update order
        from app.schemas.order import OrderUpdate
        order = await OrderCRUD.update(
            db,
            order_id,
            OrderUpdate(
                driver_id=driver_id,
                status=OrderStatus.ACCEPTED
            )
        )
        
        if order:
            # Mark driver as unavailable
            from app.schemas.user import DriverUpdate
            await DriverCRUD.update(
                db,
                driver_id,
                DriverUpdate(is_available=False)
            )
            
            logger.info(f"Assigned driver {driver_id} to order {order_id}")
        
        return order
    
    @staticmethod
    async def auto_match_order(
        db: AsyncSession,
        order_id: int
    ) -> bool:
        """
        Automatically find and assign nearest driver to order.
        
        Args:
            db: Database session
            order_id: Order ID
            
        Returns:
            True if driver assigned, False otherwise
        """
        # Get order
        order = await OrderCRUD.get_by_id(db, order_id)
        if not order or order.status != OrderStatus.PENDING:
            return False
        
        # Find nearest driver
        driver = await DriverMatchingService.find_nearest_driver(db, order)
        if not driver:
            return False
        
        # Assign driver
        assigned_order = await DriverMatchingService.assign_driver_to_order(
            db,
            order_id,
            driver.id
        )
        
        return assigned_order is not None
