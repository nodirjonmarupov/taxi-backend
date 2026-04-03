"""API v1 router initialization."""
from fastapi import APIRouter
from app.api.v1.routes import (
    user_router,
    driver_router,
    order_router,
    trip_router,
    admin_router,
)

api_router = APIRouter()

# Include all routers
api_router.include_router(user_router)
api_router.include_router(driver_router)
api_router.include_router(order_router)
api_router.include_router(trip_router)
api_router.include_router(admin_router)
