"""
Real-time taximeter: haqiqiy yurilgan yo'l bo'yicha masofa (Haversine kesmalar).
"""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus
from app.utils.distance import haversine_distance

# GPS shovqinini kamaytirish (kesma qo'shmasdan last nuqtani yangilash)
MIN_SEGMENT_M = 3.0


async def accumulate_order_distance_for_driver(
    db: AsyncSession,
    driver_id: int,
    lat: float,
    lon: float,
) -> None:
    """
    Haydovchi in_progress buyurtmada bo'lsa: oldingi nuqtadan hozirgacha kesmani qo'shadi,
    last_lat/last_lon ni yangilaydi. flush — commit chaqiruvchi beradi.
    """
    result = await db.execute(
        select(Order)
        .where(Order.driver_id == driver_id)
        .where(Order.status == OrderStatus.IN_PROGRESS)
        .limit(1)
    )
    order = result.scalar_one_or_none()
    if not order:
        return

    oid = order.id
    last_lat = getattr(order, "last_lat", None)
    last_lon = getattr(order, "last_lon", None)

    if last_lat is None or last_lon is None:
        await db.execute(
            update(Order).where(Order.id == oid).values(last_lat=lat, last_lon=lon)
        )
        return

    seg_km = haversine_distance(float(last_lat), float(last_lon), lat, lon)
    if seg_km * 1000.0 < MIN_SEGMENT_M:
        await db.execute(
            update(Order).where(Order.id == oid).values(last_lat=lat, last_lon=lon)
        )
        return

    new_total = float(order.distance_km or 0) + seg_km
    if new_total > 1000:
        new_total = 0.0

    await db.execute(
        update(Order)
        .where(Order.id == oid)
        .values(distance_km=new_total, last_lat=lat, last_lon=lon)
    )
