"""
Trip service for managing trip lifecycle.
Handles starting, completing trips, and calculating prices.
"""
from typing import Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.models import Order, OrderStatus
from app.schemas.schemas import TripCreate
from app.crud import order_crud, trip_crud, driver_crud, payment_crud
from app.core.config import settings
from app.utils.geo import calculate_distance, calculate_price, calculate_commission
from app.services.matching_service import OrderMatchingService


class TripService:
    """Service for managing trip operations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def start_trip(self, order_id: int) -> bool:
        """
        Start a trip for an accepted order.
        
        Args:
            order_id: Order ID
        
        Returns:
            True if trip started successfully
        """
        order = await order_crud.get_order_by_id(self.db, order_id)
        
        if not order:
            logger.error(f"Order {order_id} not found")
            return False
        
        if order.status != OrderStatus.ACCEPTED:
            logger.error(f"Order {order_id} is not in accepted state")
            return False
        
        if not order.driver_id:
            logger.error(f"Order {order_id} has no assigned driver")
            return False
        
        # Update order status to started
        await order_crud.update_order_status(
            self.db,
            order_id,
            OrderStatus.STARTED
        )
        
        logger.info(f"Trip started for order {order_id}")
        return True
    
    async def complete_trip(
        self,
        order_id: int,
        end_latitude: float,
        end_longitude: float
    ) -> Optional[int]:
        """
        Complete a trip and create trip record.
        
        Args:
            order_id: Order ID
            end_latitude: End location latitude
            end_longitude: End location longitude
        
        Returns:
            Trip ID if successful, None otherwise
        """
        order = await order_crud.get_order_by_id(self.db, order_id)
        
        if not order:
            logger.error(f"Order {order_id} not found")
            return None
        
        if order.status != OrderStatus.STARTED:
            logger.error(f"Order {order_id} is not in started state")
            return None
        
        if not order.driver_id:
            logger.error(f"Order {order_id} has no assigned driver")
            return None
        
        # Calculate trip metrics
        distance = calculate_distance(
            order.pickup_latitude,
            order.pickup_longitude,
            end_latitude,
            end_longitude
        )
        
        total_price = calculate_price(
            distance,
            base_price=settings.BASE_PRICE,
            price_per_km=settings.BASE_PRICE_PER_KM
        )
        
        commission, driver_earnings = calculate_commission(
            total_price,
            commission_rate=settings.DEFAULT_COMMISSION_RATE
        )
        
        # Calculate duration (from acceptance to now)
        duration_minutes = None
        if order.accepted_at:
            duration = datetime.utcnow() - order.accepted_at
            duration_minutes = int(duration.total_seconds() / 60)
        
        # Create trip record
        trip_data = TripCreate(
            order_id=order_id,
            driver_id=order.driver_id,
            start_latitude=order.pickup_latitude,
            start_longitude=order.pickup_longitude,
            end_latitude=end_latitude,
            end_longitude=end_longitude,
            distance_km=distance,
            total_price=total_price,
            commission_amount=commission,
            driver_earnings=driver_earnings,
            commission_rate=settings.DEFAULT_COMMISSION_RATE,
            started_at=order.accepted_at or datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        
        trip = await trip_crud.create_trip(self.db, trip_data)
        
        # Update order status to completed
        await order_crud.update_order_status(
            self.db,
            order_id,
            OrderStatus.COMPLETED
        )
        
        # Create payment record
        await payment_crud.create_payment(
            self.db,
            trip_id=trip.id,
            amount=total_price,
            commission=commission,
            driver_payout=driver_earnings,
            payment_method="cash"
        )
        
        # Update driver statistics
        await driver_crud.update_driver_stats(
            self.db,
            order.driver_id,
            trip_earnings=driver_earnings
        )
        
        # Clear driver assignment cache
        matching_service = OrderMatchingService(self.db)
        await matching_service.clear_driver_assignment(order.driver_id)
        
        logger.info(
            f"Trip {trip.id} completed for order {order_id}, "
            f"distance: {distance:.2f} km, price: ${total_price:.2f}"
        )
        
        return trip.id
    
    async def cancel_trip(
        self,
        order_id: int,
        reason: Optional[str] = None
    ) -> bool:
        """
        Cancel an ongoing trip.
        
        Args:
            order_id: Order ID
            reason: Cancellation reason
        
        Returns:
            True if cancelled successfully
        """
        order = await order_crud.get_order_by_id(self.db, order_id)
        
        if not order:
            return False
        
        # Can only cancel if not completed
        if order.status == OrderStatus.COMPLETED:
            logger.error(f"Cannot cancel completed order {order_id}")
            return False
        
        # Cancel order
        await order_crud.cancel_order(self.db, order_id, reason)
        
        # Clear driver assignment if exists
        if order.driver_id:
            matching_service = OrderMatchingService(self.db)
            await matching_service.clear_driver_assignment(order.driver_id)
        
        logger.info(f"Order {order_id} cancelled: {reason}")
        return True
    
    async def estimate_price(
        self,
        pickup_lat: float,
        pickup_lon: float,
        dest_lat: float,
        dest_lon: float
    ) -> float:
        """
        Estimate trip price based on coordinates.
        
        Args:
            pickup_lat: Pickup latitude
            pickup_lon: Pickup longitude
            dest_lat: Destination latitude
            dest_lon: Destination longitude
        
        Returns:
            Estimated price
        """
        distance = calculate_distance(
            pickup_lat, pickup_lon,
            dest_lat, dest_lon
        )
        
        return calculate_price(
            distance,
            base_price=settings.BASE_PRICE,
            price_per_km=settings.BASE_PRICE_PER_KM
        )
