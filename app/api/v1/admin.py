"""
API routes for trips and admin functionality.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.crud import trip_crud, user_crud, driver_crud, order_crud
from app.schemas.schemas import (
    TripResponse, RatingCreate, RatingResponse,
    PaymentResponse, AdminStats, SuccessResponse
)
from app.models.models import UserRole

# Trips router
trips_router = APIRouter(prefix="/trips", tags=["trips"])


@trips_router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(
    trip_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get trip by ID"""
    trip = await trip_crud.get_trip_by_id(db, trip_id)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )
    return trip


@trips_router.get("/driver/{driver_id}", response_model=List[TripResponse])
async def get_driver_trips(
    driver_id: int,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get all trips for a driver"""
    trips = await trip_crud.get_driver_trips(db, driver_id, skip, limit)
    return trips


@trips_router.post("/{trip_id}/rate", response_model=RatingResponse)
async def rate_trip(
    trip_id: int,
    rating_data: RatingCreate,
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Rate a completed trip"""
    # Verify trip exists
    trip = await trip_crud.get_trip_by_id(db, trip_id)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )
    
    # Check if already rated
    existing_rating = await trip_crud.get_rating_by_trip(db, trip_id)
    if existing_rating:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Trip already rated"
        )
    
    # Create rating
    rating = await trip_crud.create_rating(
        db,
        rating_data,
        user_id=user_id,
        driver_id=trip.driver_id
    )
    
    # Update driver's average rating
    avg_rating = await trip_crud.get_driver_average_rating(db, trip.driver_id)
    await driver_crud.update_driver_stats(
        db,
        trip.driver_id,
        trip_earnings=0,
        new_rating=rating.rating
    )
    
    return rating


@trips_router.get("/{trip_id}/payment", response_model=PaymentResponse)
async def get_trip_payment(
    trip_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get payment information for a trip"""
    from app.crud import payment_crud
    
    payment = await payment_crud.get_payment_by_trip(db, trip_id)
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    return payment


# Admin router
admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/stats", response_model=AdminStats)
async def get_admin_stats(db: AsyncSession = Depends(get_db)):
    """Get platform statistics"""
    # User stats
    total_users = await user_crud.get_user_count(db)
    total_drivers = await driver_crud.get_driver_count(db)
    active_drivers = await driver_crud.get_driver_count(db, available_only=True)
    
    # Order stats
    total_orders = await order_crud.get_order_count(db)
    active_orders = await order_crud.get_active_orders_count(db)
    
    # Trip and revenue stats
    completed_trips_today = await trip_crud.get_completed_trips_count(db, today_only=True)
    total_revenue = await trip_crud.get_total_revenue(db)
    revenue_today = await trip_crud.get_revenue_today(db)
    
    return AdminStats(
        total_users=total_users,
        total_drivers=total_drivers,
        active_drivers=active_drivers,
        total_orders=total_orders,
        active_orders=active_orders,
        completed_trips_today=completed_trips_today,
        total_revenue=total_revenue,
        revenue_today=revenue_today
    )


@admin_router.get("/drivers/active", response_model=List)
async def get_active_drivers(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get list of active drivers"""
    drivers = await driver_crud.get_drivers(
        db,
        skip=skip,
        limit=limit,
        available_only=True,
        verified_only=True
    )
    return drivers


@admin_router.get("/orders/active", response_model=List)
async def get_active_orders(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get list of active orders"""
    from app.models.models import OrderStatus
    
    orders = await order_crud.get_orders(
        db,
        skip=skip,
        limit=limit
    )
    
    # Filter active orders
    active = [
        o for o in orders
        if o.status in [OrderStatus.PENDING, OrderStatus.ACCEPTED, OrderStatus.STARTED]
    ]
    
    return active[:limit]
