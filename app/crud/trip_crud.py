"""
CRUD operations for Trip, Rating, and Payment models.
"""
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import Trip, Rating, Payment
from app.schemas.schemas import TripCreate, RatingCreate


# ============= Trip CRUD =============

async def create_trip(db: AsyncSession, trip_data: TripCreate) -> Trip:
    """Create a new trip record"""
    trip = Trip(**trip_data.model_dump())
    db.add(trip)
    await db.commit()
    await db.refresh(trip)
    return trip


async def get_trip_by_id(db: AsyncSession, trip_id: int) -> Optional[Trip]:
    """Get trip by ID"""
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id)
    )
    return result.scalar_one_or_none()


async def get_trip_by_order_id(db: AsyncSession, order_id: int) -> Optional[Trip]:
    """Get trip by order ID"""
    result = await db.execute(
        select(Trip).where(Trip.order_id == order_id)
    )
    return result.scalar_one_or_none()


async def get_driver_trips(
    db: AsyncSession,
    driver_id: int,
    skip: int = 0,
    limit: int = 100
) -> List[Trip]:
    """Get all trips for a driver"""
    result = await db.execute(
        select(Trip)
        .where(Trip.driver_id == driver_id)
        .order_by(Trip.completed_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_driver_trips_today(db: AsyncSession, driver_id: int) -> List[Trip]:
    """Get driver's trips completed today"""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    result = await db.execute(
        select(Trip)
        .where(
            Trip.driver_id == driver_id,
            Trip.completed_at >= today_start
        )
        .order_by(Trip.completed_at.desc())
    )
    return list(result.scalars().all())


async def get_driver_earnings_today(db: AsyncSession, driver_id: int) -> float:
    """Calculate driver's earnings for today"""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    result = await db.execute(
        select(func.sum(Trip.driver_earnings))
        .where(
            Trip.driver_id == driver_id,
            Trip.completed_at >= today_start
        )
    )
    return result.scalar() or 0.0


async def get_total_revenue(db: AsyncSession) -> float:
    """Get total platform revenue (all commissions)"""
    result = await db.execute(
        select(func.sum(Trip.commission_amount))
    )
    return result.scalar() or 0.0


async def get_revenue_today(db: AsyncSession) -> float:
    """Get today's platform revenue"""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    result = await db.execute(
        select(func.sum(Trip.commission_amount))
        .where(Trip.completed_at >= today_start)
    )
    return result.scalar() or 0.0


async def get_completed_trips_count(
    db: AsyncSession,
    today_only: bool = False
) -> int:
    """Get count of completed trips"""
    query = select(func.count(Trip.id))
    
    if today_only:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        query = query.where(Trip.completed_at >= today_start)
    
    result = await db.execute(query)
    return result.scalar() or 0


# ============= Rating CRUD =============

async def create_rating(
    db: AsyncSession,
    rating_data: RatingCreate,
    user_id: int,
    driver_id: int
) -> Rating:
    """Create a new rating"""
    rating = Rating(
        **rating_data.model_dump(),
        user_id=user_id,
        driver_id=driver_id
    )
    db.add(rating)
    await db.commit()
    await db.refresh(rating)
    return rating


async def get_rating_by_trip(db: AsyncSession, trip_id: int) -> Optional[Rating]:
    """Get rating for a specific trip"""
    result = await db.execute(
        select(Rating).where(Rating.trip_id == trip_id)
    )
    return result.scalar_one_or_none()


async def get_driver_ratings(
    db: AsyncSession,
    driver_id: int,
    skip: int = 0,
    limit: int = 100
) -> List[Rating]:
    """Get all ratings for a driver"""
    result = await db.execute(
        select(Rating)
        .where(Rating.driver_id == driver_id)
        .order_by(Rating.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_driver_average_rating(db: AsyncSession, driver_id: int) -> float:
    """Calculate driver's average rating"""
    result = await db.execute(
        select(func.avg(Rating.rating))
        .where(Rating.driver_id == driver_id)
    )
    return result.scalar() or 0.0


# ============= Payment CRUD =============

async def create_payment(
    db: AsyncSession,
    trip_id: int,
    amount: float,
    commission: float,
    driver_payout: float,
    payment_method: str = "cash"
) -> Payment:
    """Create a payment record"""
    payment = Payment(
        trip_id=trip_id,
        amount=amount,
        commission=commission,
        driver_payout=driver_payout,
        payment_method=payment_method
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return payment


async def get_payment_by_trip(db: AsyncSession, trip_id: int) -> Optional[Payment]:
    """Get payment for a trip"""
    result = await db.execute(
        select(Payment).where(Payment.trip_id == trip_id)
    )
    return result.scalar_one_or_none()


async def mark_payment_paid(
    db: AsyncSession,
    payment_id: int,
    transaction_id: Optional[str] = None
) -> Optional[Payment]:
    """Mark a payment as paid"""
    from sqlalchemy import update
    
    await db.execute(
        update(Payment)
        .where(Payment.id == payment_id)
        .values(
            is_paid=True,
            paid_at=datetime.utcnow(),
            transaction_id=transaction_id
        )
    )
    await db.commit()
    
    result = await db.execute(
        select(Payment).where(Payment.id == payment_id)
    )
    return result.scalar_one_or_none()
