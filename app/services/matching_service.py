"""
Order matching and assignment service.
Handles driver-order matching logic and reassignment.
"""
from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.models import Order, Driver, OrderStatus
from app.crud import driver_crud, order_crud
from app.core.config import settings
from app.core.redis import cache_set, cache_get, cache_delete
from app.utils.geo import calculate_distance


class OrderMatchingService:
    """Service for matching orders with drivers"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def find_driver_for_order(self, order: Order) -> Optional[Driver]:
        """
        Find the best available driver for an order.
        
        Algorithm:
        1. Find drivers within search radius
        2. Sort by distance
        3. Return nearest available driver
        
        Args:
            order: Order to match
        
        Returns:
            Matched driver or None
        """
        # Find nearby drivers
        drivers = await driver_crud.get_nearby_drivers(
            self.db,
            latitude=order.pickup_latitude,
            longitude=order.pickup_longitude,
            radius_km=settings.DRIVER_SEARCH_RADIUS_KM,
            limit=10
        )
        
        if not drivers:
            logger.warning(f"No drivers found for order {order.id}")
            return None
        
        # Get first (closest) available driver
        for driver in drivers:
            # Check if driver is currently assigned to another order
            if await self._is_driver_busy(driver.id):
                continue
            
            logger.info(
                f"Found driver {driver.id} for order {order.id}, "
                f"distance: {driver.distance:.2f} km"
            )
            return driver
        
        logger.warning(f"All nearby drivers are busy for order {order.id}")
        return None
    
    async def assign_order_to_driver(
        self,
        order_id: int,
        driver_id: int
    ) -> bool:
        """
        Assign an order to a driver.
        
        Args:
            order_id: Order ID
            driver_id: Driver ID
        
        Returns:
            True if assignment successful
        """
        try:
            # Update order status and assign driver
            order = await order_crud.assign_driver_to_order(
                self.db,
                order_id,
                driver_id
            )
            
            if not order:
                logger.error(f"Failed to assign order {order_id} to driver {driver_id}")
                return False
            
            # Cache the assignment
            await cache_set(
                f"driver:{driver_id}:current_order",
                order_id,
                ttl=3600  # 1 hour
            )
            
            logger.info(f"Order {order_id} assigned to driver {driver_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error assigning order: {e}")
            return False
    
    async def auto_assign_order(self, order_id: int) -> bool:
        """
        Automatically find and assign a driver to an order.
        
        Args:
            order_id: Order ID
        
        Returns:
            True if assignment successful
        """
        order = await order_crud.get_order_by_id(self.db, order_id)
        
        if not order:
            logger.error(f"Order {order_id} not found")
            return False
        
        if order.status != OrderStatus.PENDING:
            logger.warning(f"Order {order_id} is not pending")
            return False
        
        # Find driver
        driver = await self.find_driver_for_order(order)
        
        if not driver:
            logger.warning(f"No available driver for order {order_id}")
            return False
        
        # Assign driver
        return await self.assign_order_to_driver(order_id, driver.id)
    
    async def handle_driver_rejection(
        self,
        order_id: int,
        driver_id: int
    ) -> bool:
        """
        Handle when a driver rejects an order.
        Try to reassign to another driver.
        
        Args:
            order_id: Order ID
            driver_id: Driver who rejected
        
        Returns:
            True if reassignment successful
        """
        order = await order_crud.get_order_by_id(self.db, order_id)
        
        if not order:
            return False
        
        # Check reassignment limit
        if order.reassign_count >= settings.MAX_DRIVER_REASSIGN_ATTEMPTS:
            logger.warning(
                f"Order {order_id} exceeded reassignment limit, cancelling"
            )
            await order_crud.cancel_order(
                self.db,
                order_id,
                reason="No available drivers"
            )
            return False
        
        # Increment reassignment counter
        await order_crud.increment_reassign_count(self.db, order_id)
        
        # Clear current driver assignment
        await cache_delete(f"driver:{driver_id}:current_order")
        
        # Try to find another driver
        return await self.auto_assign_order(order_id)
    
    async def handle_timeout_orders(self) -> int:
        """
        Find and handle orders that have timed out.
        This should be called periodically (e.g., every minute).
        
        Returns:
            Number of orders processed
        """
        timeout_orders = await order_crud.get_pending_orders(
            self.db,
            timeout_seconds=settings.ORDER_TIMEOUT_SECONDS
        )
        
        processed = 0
        
        for order in timeout_orders:
            logger.info(f"Processing timeout order {order.id}")
            
            # Try to reassign
            success = await self.auto_assign_order(order.id)
            
            if not success:
                # Cancel if can't reassign
                await order_crud.cancel_order(
                    self.db,
                    order.id,
                    reason="Timeout - no available drivers"
                )
            
            processed += 1
        
        return processed
    
    async def _is_driver_busy(self, driver_id: int) -> bool:
        """Check if driver is currently assigned to an order"""
        current_order = await cache_get(f"driver:{driver_id}:current_order")
        return current_order is not None
    
    async def clear_driver_assignment(self, driver_id: int):
        """Clear driver's current order assignment"""
        await cache_delete(f"driver:{driver_id}:current_order")
