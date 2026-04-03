from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.crud.order_crud import OrderCRUD
from app.crud.user import DriverCRUD
from app.models.order import Order, OrderStatus
from app.utils.trip_finish import sanitize_distance_km, parse_client_final_price


class TripService:
    @staticmethod
    async def start_trip(db: AsyncSession, order_id: int, driver_id: int) -> Order:
        """Safar/Buyurtmani boshlash — taksometr: haydovchi joriy nuqtasi last_lat/lon."""
        order = await OrderCRUD.get_by_id(db, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if order.driver_id != driver_id:
            raise HTTPException(status_code=403, detail="Not your order")

        apply_start = order.status == OrderStatus.ACCEPTED
        trip_lat = None
        trip_lon = None
        if apply_start:
            drv = await DriverCRUD.get_by_id(db, driver_id)
            if drv:
                trip_lat = getattr(drv, "current_latitude", None)
                trip_lon = getattr(drv, "current_longitude", None)
            if trip_lat is not None:
                trip_lat = float(trip_lat)
            if trip_lon is not None:
                trip_lon = float(trip_lon)

        return await OrderCRUD.update_status(
            db,
            order_id,
            OrderStatus.STARTED,
            apply_taximeter_start=apply_start,
            trip_start_lat=trip_lat,
            trip_start_lon=trip_lon,
        )

    @staticmethod
    async def complete_trip(
        db: AsyncSession,
        order_id: int,
        driver_id: int,
        *,
        final_price: float,
        distance_km: float = 0.0,
    ) -> Order:
        """Safarni yakunlash — narx va masofa client (taksometr) dan; server qayta hisoblamaydi."""
        order = await OrderCRUD.get_by_id(db, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order.driver_id != driver_id:
            raise HTTPException(status_code=403, detail="Not your order")

        fp = parse_client_final_price(final_price)
        if fp is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="final_price musbat bo'lishi kerak (taksometr qiymati).",
            )
        dk = sanitize_distance_km(distance_km)
        return await OrderCRUD.update_status(
            db, order_id, OrderStatus.COMPLETED, distance_km=dk, final_price=fp
        )

    @staticmethod
    async def cancel_trip(db: AsyncSession, order_id: int, user_id: int) -> Order:
        """Buyurtmani bekor qilish"""
        order = await OrderCRUD.get_by_id(db, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        return await OrderCRUD.update_status(db, order_id, OrderStatus.CANCELLED)
