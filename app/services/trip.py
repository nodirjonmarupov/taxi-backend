from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.core.logger import get_logger
from app.core.redis import delete_trip_state, get_redis, get_trip_state
from app.crud.order_crud import OrderCRUD
from app.crud.user import DriverCRUD
from app.models.order import Order, OrderStatus
from app.services.commission import deduct_commission_on_trip_complete
from app.services.settings_service import SettingsLoadError
from app.services.trip_billing import compute_server_final_price_for_completion

logger = get_logger(__name__)


def _status_str(order: Order) -> str:
    s = order.status.value if hasattr(order.status, "value") else order.status
    return str(s or "").lower()


class TripService:
    @staticmethod
    async def start_trip(db: AsyncSession, order_id: int, driver_id: int) -> Order:
        """Safar/Buyurtmani boshlash — taksometr: haydovchi joriy nuqtasi last_lat/lon."""
        order = await OrderCRUD.get_by_id(db, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if order.driver_id != driver_id:
            logger.warning(
                "start_trip denied: order_id=%s order_driver=%s caller_driver=%s",
                order_id,
                getattr(order, "driver_id", None),
                driver_id,
            )
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
    ) -> Order:
        """
        Safarni yakunlash — WebApp / Telegram bilan bir xil:
        yakuniy narx faqat server compute_server_final_price_for_completion,
        tariff_snapshot_json + masofa + narx DB ga, Redis trip_state tozalash,
        komissiya/keshbek deduct_commission_on_trip_complete (idempotent).
        """
        order = await OrderCRUD.get_by_id(db, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order.driver_id != driver_id:
            logger.warning(
                "complete_trip denied: order_id=%s order_driver=%s caller_driver=%s",
                order_id,
                getattr(order, "driver_id", None),
                driver_id,
            )
            raise HTTPException(status_code=403, detail="Not your order")

        cur = _status_str(order)
        if cur == "completed":
            logger.info(
                "REST complete: order=%s allaqachon completed — idempotent javob",
                order_id,
            )
            return order

        if cur != "in_progress":
            raise HTTPException(
                status_code=400,
                detail="Trip must be in progress to complete",
            )

        r = get_redis()
        trip_st = get_trip_state(r, order_id) if r else None

        try:
            fp, tariff_snap, d_km = await compute_server_final_price_for_completion(
                db,
                order_id,
                order,
                trip_st=trip_st,
            )
        except SettingsLoadError as e:
            logger.error("complete_trip SettingsLoadError: %s", e)
            raise HTTPException(
                status_code=503,
                detail="Billing configuration unavailable",
            ) from e
        except Exception as e:
            logger.exception("complete_trip compute_server_final_price: %s", e)
            raise HTTPException(
                status_code=500,
                detail="Failed to compute trip price",
            ) from e

        logger.info(
            "[SERVER RECOMPUTE] REST order_id=%s final_price=%s distance_km=%s",
            order_id,
            fp,
            d_km,
        )

        updated_order = await OrderCRUD.update_status(
            db,
            order_id,
            OrderStatus.COMPLETED,
            distance_km=d_km,
            final_price=fp,
            tariff_snapshot_json=tariff_snap,
        )
        if not updated_order:
            raise HTTPException(status_code=500, detail="Failed to complete order")

        if r is not None:
            try:
                delete_trip_state(r, order_id)
            except Exception as del_e:
                logger.warning("delete_trip_state order=%s: %s", order_id, del_e)

        if updated_order.driver_id:
            driver = await DriverCRUD.get_by_id(db, updated_order.driver_id)
            if driver:
                driver.is_available = True
                await db.commit()

        await deduct_commission_on_trip_complete(updated_order)
        return updated_order

    @staticmethod
    async def cancel_trip(db: AsyncSession, order_id: int, user_id: int) -> Order:
        """Buyurtmani bekor qilish"""
        order = await OrderCRUD.get_by_id(db, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        return await OrderCRUD.update_status(db, order_id, OrderStatus.CANCELLED)
