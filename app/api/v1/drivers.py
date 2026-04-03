"""
API routes for driver management.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.crud import driver_crud, user_crud
from app.schemas.schemas import (
    DriverCreate, DriverUpdate, DriverResponse, DriverWithUser,
    LocationUpdate, DriverStats, SuccessResponse
)
from app.models.models import UserRole

router = APIRouter(prefix="/drivers", tags=["drivers"])


@router.post("/", response_model=DriverResponse, status_code=status.HTTP_201_CREATED)
async def create_driver(
    driver_data: DriverCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new driver profile"""
    # Verify user exists and is a driver
    user = await user_crud.get_user_by_id(db, driver_data.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.role != UserRole.DRIVER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not registered as a driver"
        )
    
    # Check if driver profile already exists
    existing = await driver_crud.get_driver_by_user_id(db, driver_data.user_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Driver profile already exists for this user"
        )
    
    driver = await driver_crud.create_driver(db, driver_data)
    return driver


@router.get("/{driver_id}", response_model=DriverWithUser)
async def get_driver(
    driver_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get driver by ID"""
    driver = await driver_crud.get_driver_by_id(db, driver_id)
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver not found"
        )
    return driver


@router.get("/user/{user_id}", response_model=DriverWithUser)
async def get_driver_by_user(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get driver profile by user ID"""
    driver = await driver_crud.get_driver_by_user_id(db, user_id)
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver profile not found"
        )
    return driver


@router.get("/", response_model=List[DriverWithUser])
async def list_drivers(
    skip: int = 0,
    limit: int = 100,
    available_only: bool = False,
    verified_only: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """List all drivers"""
    drivers = await driver_crud.get_drivers(
        db,
        skip=skip,
        limit=limit,
        available_only=available_only,
        verified_only=verified_only
    )
    return drivers


@router.patch("/{driver_id}", response_model=DriverResponse)
async def update_driver(
    driver_id: int,
    driver_data: DriverUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update driver information"""
    driver = await driver_crud.update_driver(db, driver_id, driver_data)
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver not found"
        )
    return driver


@router.post("/{driver_id}/location", response_model=DriverResponse)
async def update_driver_location(
    driver_id: int,
    location: LocationUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update driver's current location"""
    driver = await driver_crud.update_driver_location(db, driver_id, location)
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver not found"
        )
    return driver


@router.post("/{driver_id}/availability", response_model=DriverResponse)
async def set_driver_availability(
    driver_id: int,
    is_available: bool,
    db: AsyncSession = Depends(get_db)
):
    """Set driver availability status"""
    driver = await driver_crud.set_driver_availability(db, driver_id, is_available)
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver not found"
        )
    return driver


@router.get("/{driver_id}/stats", response_model=DriverStats)
async def get_driver_stats(
    driver_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get driver statistics"""
    from app.crud import trip_crud
    
    driver = await driver_crud.get_driver_by_id(db, driver_id)
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver not found"
        )
    
    # Get today's stats
    trips_today = await trip_crud.get_driver_trips_today(db, driver_id)
    earnings_today = await trip_crud.get_driver_earnings_today(db, driver_id)
    
    return DriverStats(
        total_trips=driver.total_trips,
        total_earnings=driver.total_earnings,
        average_rating=driver.rating,
        completed_today=len(trips_today),
        earnings_today=earnings_today
    )
