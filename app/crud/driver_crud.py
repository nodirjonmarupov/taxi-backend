"""
CRUD operations for Driver model.
"""
from typing import Optional, List
from datetime import datetime
from sqlalchemy import select, update, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import Driver, UserRole
from app.core.config import settings
from app.schemas.schemas import DriverCreate, DriverUpdate, LocationUpdate


async def create_driver(db: AsyncSession, driver_data: DriverCreate) -> Driver:
    """Create a new driver profile"""
    driver = Driver(**driver_data.model_dump())
    db.add(driver)
    await db.commit()
    await db.refresh(driver)
    return driver


async def get_driver_by_id(db: AsyncSession, driver_id: int) -> Optional[Driver]:
    """Get driver by ID with user relationship"""
    result = await db.execute(
        select(Driver)
        .options(selectinload(Driver.user))
        .where(Driver.id == driver_id)
    )
    return result.scalar_one_or_none()


async def get_driver_by_user_id(db: AsyncSession, user_id: int) -> Optional[Driver]:
    """Get driver profile by user ID"""
    result = await db.execute(
        select(Driver)
        .options(selectinload(Driver.user))
        .where(Driver.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_drivers(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    available_only: bool = False,
    verified_only: bool = True
) -> List[Driver]:
    """Get list of drivers with filters"""
    query = select(Driver).options(selectinload(Driver.user))
    
    if available_only:
        query = query.where(Driver.is_available == True)
    
    if verified_only:
        query = query.where(Driver.is_verified == True)
    query = query.where(Driver.is_active == True)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_driver(
    db: AsyncSession,
    driver_id: int,
    driver_data: DriverUpdate
) -> Optional[Driver]:
    """Update driver information"""
    await db.execute(
        update(Driver)
        .where(Driver.id == driver_id)
        .values(**driver_data.model_dump(exclude_unset=True))
    )
    await db.commit()
    return await get_driver_by_id(db, driver_id)


async def update_driver_location(
    db: AsyncSession,
    driver_id: int,
    location: LocationUpdate
) -> Optional[Driver]:
    """Update driver's current location"""
    # PostGIS location + location_updated_at ham yangilanadi
    await db.execute(
        text("""
            UPDATE drivers
            SET
                current_latitude = :lat,
                current_longitude = :lon,
                location = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                location_updated_at = NOW(),
                last_location_update = NOW()
            WHERE id = :driver_id
        """),
        {
            "driver_id": driver_id,
            "lat": location.latitude,
            "lon": location.longitude,
        },
    )
    await db.commit()
    return await get_driver_by_id(db, driver_id)


async def set_driver_availability(
    db: AsyncSession,
    driver_id: int,
    is_available: bool
) -> Optional[Driver]:
    """Set driver availability status"""
    await db.execute(
        update(Driver)
        .where(Driver.id == driver_id)
        .values(is_available=is_available)
    )
    await db.commit()
    return await get_driver_by_id(db, driver_id)


async def get_nearby_drivers(
    db: AsyncSession,
    latitude: float,
    longitude: float,
    radius_km: float = 10.0,
    limit: int = 10,
    exclude_user_id: Optional[int] = None  # Yangi parametr
) -> List[Driver]:
    """
    Find nearby available drivers excluding the customer themselves.
    """
    # 1. So'rovni shakllantiramiz (card_linked, balance vaqtinchalik o'chirilgan)
    # from app.core.config import settings
    # min_balance = getattr(settings, "MIN_BALANCE", 5000.0)
    query = select(Driver).options(selectinload(Driver.user)).where(
        Driver.is_active == True,
        Driver.is_available == True,
        Driver.is_verified == True,
        # Driver.has_active_card == True,
        # Driver.balance >= min_balance,
        Driver.current_latitude.isnot(None),
        Driver.current_longitude.isnot(None)
    )
    
    # 2. AGAR EXCLUDE_USER_ID BERILSA, UNI CHIQARIB TASHLAYMIZ
    if exclude_user_id:
        query = query.where(Driver.user_id != exclude_user_id)
    
    result = await db.execute(query)
    all_drivers = list(result.scalars().all())

    # Adminlarni chiqarish (ADMIN_CAN_RECEIVE_ORDERS=False bo'lganda)
    if not getattr(settings, "ADMIN_CAN_RECEIVE_ORDERS", False):
        admin_ids = set(getattr(settings, "ADMIN_IDS", []))
        all_drivers = [
            d
            for d in all_drivers
            if d.user
            and d.user.role != UserRole.ADMIN
            and getattr(d.user, "telegram_id", None) not in admin_ids
        ]
    
    # 3. Masofani hisoblash va filterlash
    from app.utils.geo import calculate_distance
    nearby = []
    
    for driver in all_drivers:
        distance = calculate_distance(
            latitude, longitude,
            driver.current_latitude, driver.current_longitude
        )
        if distance <= radius_km:
            driver.distance = distance  
            nearby.append(driver)
    
    # Masofa bo'yicha saralash
    nearby.sort(key=lambda d: d.distance)
    return nearby[:limit]

async def update_driver_stats(
    db: AsyncSession,
    driver_id: int,
    trip_earnings: float,
    new_rating: Optional[float] = None
) -> None:
    """Update driver statistics after a trip"""
    driver = await get_driver_by_id(db, driver_id)
    if not driver:
        return
    
    new_total_trips = driver.total_trips + 1
    new_total_earnings = driver.total_earnings + trip_earnings
    
    # Update rating if provided (use rating and total_ratings)
    if new_rating is not None:
        current_total = driver.rating * driver.total_ratings
        new_total_ratings = driver.total_ratings + 1
        new_rating_value = (current_total + new_rating) / new_total_ratings
    else:
        new_rating_value = driver.rating
        new_total_ratings = driver.total_ratings
    
    await db.execute(
        update(Driver)
        .where(Driver.id == driver_id)
        .values(
            total_trips=new_total_trips,
            total_earnings=new_total_earnings,
            rating=new_rating_value,
            total_ratings=new_total_ratings
        )
    )
    await db.commit()


async def get_driver_count(
    db: AsyncSession,
    available_only: bool = False
) -> int:
    """Get total driver count"""
    query = select(func.count(Driver.id))
    if available_only:
        query = query.where(Driver.is_available == True, Driver.is_verified == True)
    result = await db.execute(query)
    return result.scalar() or 0
