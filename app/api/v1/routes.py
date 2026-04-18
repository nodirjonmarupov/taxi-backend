"""
Taxi Backend System API routerlari - To'liq to'g'irlangan variant.
Faqat mavjud bo'lgan Order, User va Driver modellaridan foydalanadi.
"""
import json
import logging
import secrets
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Date, text, or_
from pydantic import BaseModel, Field, field_validator

from app.core.database import get_db
from app.core.config import settings as config
from app.core.security import create_access_token, verify_password
from app.core.admin_login_rate_limit import (
    clear_admin_login_failures,
    client_ip_from_request,
    is_admin_login_locked,
    lockout_message,
    record_admin_login_failure,
)
from app.api.deps import get_current_admin
from app.crud.user import UserCRUD, DriverCRUD, RatingCRUD
from app.crud.order_crud import OrderCRUD
from app.schemas.user import (
    UserCreate, UserUpdate, UserResponse,
    DriverCreate, DriverUpdate, DriverResponse, DriverWithUser, DriverLocation,
    RatingCreate, RatingResponse,
)
from app.schemas.order import (
    OrderCreate, OrderResponse, OrderUpdate,
    DriverStats, AdminStats, TopDriverItem, TopUserItem,
    DailyStatItem, RecentOrderItem,
)
from app.services.matching import DriverMatchingService
from app.services.trip import TripService
from app.models.order import Order, OrderStatus
from app.models.user import User, Driver

# Routerlarni yaratish
user_router = APIRouter(prefix="/users", tags=["users"])
driver_router = APIRouter(prefix="/drivers", tags=["drivers"])
order_router = APIRouter(prefix="/orders", tags=["orders"])
trip_router = APIRouter(prefix="/trips", tags=["trips"]) # Safar logikasi uchun router saqlab qolindi
admin_router = APIRouter(prefix="/admin", tags=["admin"])


# ==================== USER ENDPOINTS ====================
@user_router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await UserCRUD.get_by_telegram_id(db, user_data.telegram_id)
    if existing:
        return existing # Agar foydalanuvchi bo'lsa, uni qaytaramiz
    return await UserCRUD.create(db, user_data)

@user_router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await UserCRUD.get_by_id(db, user_id)
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")
    return user

# ==================== DRIVER ENDPOINTS ====================
@driver_router.post("", response_model=DriverResponse, status_code=201)
async def create_driver(data: DriverCreate, db: AsyncSession = Depends(get_db)):
    existing = await DriverCRUD.get_by_user_id(db, data.user_id)
    if existing:
        raise HTTPException(400, "Haydovchi allaqachon ro'yxatdan o'tgan")
    return await DriverCRUD.create(db, data)

@driver_router.get("/{driver_id}/trips", response_model=List[OrderResponse])
async def get_driver_trips(
    driver_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    # TripCRUD o'rniga OrderCRUD ishlatamiz
    return await OrderCRUD.get_multi(db, skip=skip, limit=limit, driver_id=driver_id)

@driver_router.get("/{driver_id}/stats", response_model=DriverStats)
async def get_driver_stats(driver_id: int, db: AsyncSession = Depends(get_db)):
    driver = await DriverCRUD.get_by_id(db, driver_id)
    if not driver:
        raise HTTPException(404, "Haydovchi topilmadi")
    
    return DriverStats(
        total_trips=driver.total_trips,
        completed_trips=driver.completed_trips,
        total_earnings=float(driver.total_earnings),
        rating=driver.rating
    )

# ==================== ORDER ENDPOINTS ====================
@order_router.post("", response_model=OrderResponse, status_code=201)
async def create_order(user_id: int, data: OrderCreate, db: AsyncSession = Depends(get_db)):
    # OrderCRUD.create metodini chaqirish (schema mosligi tekshiriladi)
    order = await OrderCRUD.create(db, user_id, data)
    # Haydovchi qidirish xizmati (ixtiyoriy)
    # await DriverMatchingService.auto_match_order(db, order.id)
    return order

@order_router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int, db: AsyncSession = Depends(get_db)):
    order = await OrderCRUD.get_by_id(db, order_id)
    if not order:
        raise HTTPException(404, "Buyurtma topilmadi")
    return order

# ==================== TRIP (SAFAR) LOGIKASI ====================
# Bu yerda nomlar Trip deb qolsa ham, ichida Order modelidan foydalanadi


class TripCompleteBody(BaseModel):
    """Yakuniy narx va masofa — taksometr (client) manbai."""
    final_price: float = Field(..., gt=0, description="Taksometr yakuniy narxi")
    distance_km: float = Field(0.0, ge=0, le=1000, description="Yakuniy masofa (km)")


@trip_router.post("/{order_id}/start", response_model=OrderResponse)
async def start_trip(order_id: int, driver_id: int, db: AsyncSession = Depends(get_db)):
    """Safar boshlanishi (Botdagi 'Yo'lga chiqdik' tugmasi)"""
    return await TripService.start_trip(db, order_id, driver_id)


@trip_router.post("/{order_id}/complete", response_model=OrderResponse)
async def complete_trip(
    order_id: int,
    driver_id: int,
    body: TripCompleteBody,
    db: AsyncSession = Depends(get_db),
):
    """Safar yakunlanishi — narx/masofa client (taksometr) dan; server qayta hisoblamaydi."""
    return await TripService.complete_trip(
        db,
        order_id,
        driver_id,
        final_price=body.final_price,
        distance_km=body.distance_km,
    )

# ==================== ADMIN ENDPOINTS ====================
class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, description="Panel admin username (create_admin script)")
    password: str = Field(..., min_length=1)
    admin_token: Optional[str] = Field(
        default=None,
        description="ADMIN_LOGIN_TOKEN (second secret); omit if not configured",
    )


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@admin_router.post("/login", response_model=AdminLoginResponse)
async def admin_login(
    request: Request,
    body: AdminLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Admin login: username + password (bcrypt); optional ADMIN_LOGIN_TOKEN. Rate-limited per client IP."""
    ip = client_ip_from_request(request)
    if is_admin_login_locked(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=lockout_message(),
        )

    has_panel_admin = await db.execute(
        select(func.count())
        .select_from(User)
        .where(User.is_admin == True, User.hashed_password.isnot(None))
    )
    if (has_panel_admin.scalar() or 0) == 0:
        raise HTTPException(
            status_code=503,
            detail="No admin user. Run: python -m app.scripts.create_admin",
        )

    raw_tok = body.admin_token
    if raw_tok is None or (isinstance(raw_tok, str) and not raw_tok.strip()):
        tok_ok = True
    else:
        tok_ok = secrets.compare_digest(
            raw_tok.strip().encode("utf-8"),
            config.ADMIN_LOGIN_TOKEN.encode("utf-8"),
        )
    if not tok_ok:
        record_admin_login_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    uname = body.username.strip()
    result = await db.execute(
        select(User).where(
            User.username == uname,
            User.is_admin == True,
            User.hashed_password.isnot(None),
        )
    )
    user = result.scalar_one_or_none()
    if not user or not user.hashed_password:
        record_admin_login_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(body.password, user.hashed_password):
        record_admin_login_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    clear_admin_login_failures(ip)

    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=403, detail="User is inactive")
    if getattr(user, "is_blocked", False):
        raise HTTPException(status_code=403, detail="User is blocked")
    token = create_access_token(data={"sub": str(user.id)})
    return AdminLoginResponse(access_token=token)


@admin_router.get("/stats", response_model=AdminStats)
async def get_admin_stats(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    # Combined queries for order and driver stats
    order_result = await db.execute(text("""
        SELECT
            COUNT(*)::int AS total_orders,
            COUNT(*) FILTER (WHERE status IN ('pending', 'accepted', 'in_progress'))::int AS active_orders,
            COALESCE(SUM(final_price) FILTER (WHERE status = 'completed'), 0)::float AS revenue
        FROM orders
    """))
    order_row = order_result.fetchone()
    total_orders = order_row[0] if order_row else 0
    active_orders = order_row[1] if order_row else 0
    revenue = float(order_row[2]) if order_row and order_row[2] else 0.0

    driver_result = await db.execute(text("""
        SELECT
            COUNT(*)::int AS total_drivers,
            COUNT(*) FILTER (WHERE is_active = true AND is_available = true)::int AS active_drivers,
            COALESCE(SUM(total_commission_paid), 0)::float AS profit
        FROM drivers
    """))
    driver_row = driver_result.fetchone()
    total_drivers = driver_row[0] if driver_row else 0
    active_drivers = driver_row[1] if driver_row else 0
    profit = float(driver_row[2]) if driver_row and driver_row[2] else 0.0

    user_result = await db.execute(text("SELECT COUNT(*)::int FROM users"))
    total_users = user_result.scalar() or 0

    # Top Drivers: eng ko'p completed order bajargan 5 ta haydovchi
    top_drivers_stmt = (
        select(Driver, User)
        .join(User, Driver.user_id == User.id)
        .order_by(Driver.completed_trips.desc())
        .limit(5)
    )
    top_drivers_rows = (await db.execute(top_drivers_stmt)).all()
    top_drivers = [
        TopDriverItem(
            name=(f"{u.first_name or ''} {u.last_name or ''}".strip()) or "-",
            phone=u.phone,
            completed_orders=d.completed_trips,
            rating=float(d.rating) if d.rating else 5.0,
        )
        for d, u in top_drivers_rows
    ]

    # Top Users: eng ko'p sarflagan 5 ta mijoz (completed buyurtmalar bo'yicha)
    top_users_stmt = (
        select(User, func.coalesce(func.sum(Order.final_price), 0).label("total_spent"))
        .select_from(Order)
        .join(User, Order.user_id == User.id)
        .where(Order.status == OrderStatus.COMPLETED)
        .group_by(User.id)
        .order_by(func.sum(Order.final_price).desc())
        .limit(5)
    )
    top_users_rows = (await db.execute(top_users_stmt)).all()
    top_users = [
        TopUserItem(
            name=(f"{u.first_name or ''} {u.last_name or ''}".strip()) or "-",
            phone=u.phone,
            total_spent=float(total_spent),
        )
        for u, total_spent in top_users_rows
    ]

    # Daily stats: oxirgi 7 kun - daromad va buyurtmalar soni (completed)
    from datetime import timedelta
    today = datetime.utcnow().date()
    dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
    daily_stmt = (
        select(
            cast(Order.completed_at, Date).label("d"),
            func.coalesce(func.sum(Order.final_price), 0).label("rev"),
            func.count(Order.id).label("cnt"),
        )
        .where(
            Order.status == OrderStatus.COMPLETED,
            Order.completed_at.isnot(None),
            cast(Order.completed_at, Date) >= today - timedelta(days=6),
        )
        .group_by(cast(Order.completed_at, Date))
    )
    daily_rows = (await db.execute(daily_stmt)).all()
    daily_map = {str(r.d): {"revenue": float(r.rev), "order_count": r.cnt} for r in daily_rows}
    daily_stats = [
        DailyStatItem(
            date=d,
            revenue=daily_map.get(d, {}).get("revenue", 0.0),
            order_count=int(daily_map.get(d, {}).get("order_count", 0)),
        )
        for d in dates
    ]

    # Recent orders: oxirgi 5 ta buyurtma
    from sqlalchemy.orm import aliased
    DriverUser = aliased(User)
    recent_stmt = (
        select(Order, User, Driver, DriverUser)
        .join(User, Order.user_id == User.id)
        .outerjoin(Driver, Order.driver_id == Driver.id)
        .outerjoin(DriverUser, Driver.user_id == DriverUser.id)
        .order_by(Order.created_at.desc())
        .limit(5)
    )
    recent_rows = (await db.execute(recent_stmt)).all()
    recent_orders = [
        RecentOrderItem(
            client_name=(f"{u.first_name or ''} {u.last_name or ''}".strip()) or "-",
            driver_name=(f"{du.first_name or ''} {du.last_name or ''}".strip() if du else "") or "-",
            price=float(o.final_price) if o.final_price else None,
            status=o.status or "pending",
        )
        for o, u, d, du in recent_rows
    ]

    return AdminStats(
        total_users=total_users or 0,
        total_drivers=total_drivers or 0,
        total_orders=total_orders or 0,
        active_orders=active_orders or 0,
        active_drivers=active_drivers,
        revenue=float(revenue),
        profit=float(profit),
        top_drivers=top_drivers,
        top_users=top_users,
        daily_stats=daily_stats,
        recent_orders=recent_orders,
    )


# --- Admin Settings ---
class SettingsResponse(BaseModel):
    min_price: float
    price_per_km: float
    commission_rate: float
    surge_multiplier: float
    is_surge_active: bool
    cashback_percent: float
    max_bonus_usage_percent: float
    max_bonus_cap: float
    price_per_min_waiting: float


class SettingsUpdateRequest(BaseModel):
    min_price: Optional[float] = Field(None, ge=0)
    price_per_km: Optional[float] = Field(None, ge=0)
    commission_rate: Optional[float] = Field(None, ge=0, le=100)
    surge_multiplier: Optional[float] = Field(None, ge=1.0, le=2.0)
    is_surge_active: Optional[bool] = None
    cashback_percent: Optional[float] = Field(None, ge=0, le=100)
    max_bonus_usage_percent: Optional[float] = Field(None, ge=0, le=100)
    max_bonus_cap: Optional[float] = Field(None, ge=0)
    price_per_min_waiting: Optional[float] = Field(None, ge=0)


@admin_router.get("/settings", response_model=SettingsResponse)
async def admin_get_settings(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    try:
        from app.services.settings_service import get_settings
        s = await get_settings(db)
        return SettingsResponse(**s.to_dict())
    except Exception as e:
        logging.getLogger(__name__).warning("admin_get_settings xato: %s", e)
        return SettingsResponse(
            min_price=5000,
            price_per_km=2500,
            commission_rate=10.0,
            surge_multiplier=1.5,
            is_surge_active=False,
            cashback_percent=0.0,
            max_bonus_usage_percent=0.0,
            max_bonus_cap=5000.0,
            price_per_min_waiting=500.0,
        )


@admin_router.put("/settings", response_model=SettingsResponse)
async def admin_update_settings(
    body: SettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    try:
        from app.services.settings_service import update_settings
        s = await update_settings(
            db,
            min_price=body.min_price,
            price_per_km=body.price_per_km,
            commission_rate=body.commission_rate,
            surge_multiplier=body.surge_multiplier,
            is_surge_active=body.is_surge_active,
            cashback_percent=body.cashback_percent,
            max_bonus_usage_percent=body.max_bonus_usage_percent,
            max_bonus_cap=body.max_bonus_cap,
            price_per_min_waiting=body.price_per_min_waiting,
            admin_user_id=admin.id,
        )
        return SettingsResponse(**s.to_dict())
    except Exception as e:
        try:
            await db.rollback()
        except Exception:
            pass
        logging.getLogger(__name__).error("admin_update_settings xato: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# --- Admin Drivers ---
class AdminDriverItem(BaseModel):
    id: int
    user_id: int
    car_number: str
    car_model: str
    status: str
    is_active: bool
    is_verified: bool = False
    balance: float
    completed_trips: int
    first_name: Optional[str] = None
    phone: Optional[str] = None
    commission_rate: Optional[float] = None


class AdminDriverDetail(BaseModel):
    id: int
    user_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    telegram_id: Optional[int] = None
    car_number: str
    car_model: str
    status: str
    is_active: bool
    is_verified: bool
    is_available: bool
    rating: float
    total_trips: int
    completed_trips: int
    total_earnings: float
    balance: float
    commission_rate: Optional[float] = None
    admin_notes: Optional[str] = None
    blocked_reason: Optional[str] = None


class AdminDriverUpdateRequest(BaseModel):
    commission_rate: Optional[float] = None
    admin_notes: Optional[str] = None


@admin_router.get("/drivers", response_model=List[AdminDriverItem])
async def admin_list_drivers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None, min_length=1),
    phone: Optional[str] = Query(None, min_length=1),
    car_number: Optional[str] = Query(None, min_length=1),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    from sqlalchemy.orm import selectinload

    q = (
        select(Driver)
        .join(User, Driver.user_id == User.id)
        .options(selectinload(Driver.user))
    )
    if car_number:
        q = q.where(Driver.car_number.ilike(f"%{car_number.strip()}%"))
    if phone:
        q = q.where(User.phone.ilike(f"%{phone.strip()}%"))
    if search:
        s = search.strip()
        q = q.where(or_(
            User.first_name.ilike(f"%{s}%"),
            User.phone.ilike(f"%{s}%"),
            Driver.car_number.ilike(f"%{s}%"),
            Driver.car_model.ilike(f"%{s}%"),
        ))

    q = q.order_by(Driver.id.desc()).offset(skip).limit(limit)
    drivers = (await db.execute(q)).scalars().all()
    return [
        AdminDriverItem(
            id=d.id,
            user_id=d.user_id,
            car_number=d.car_number,
            car_model=d.car_model or "",
            status=d.status,
            is_active=d.is_active,
            is_verified=bool(getattr(d, "is_verified", False)),
            balance=float(d.balance or 0),
            completed_trips=d.completed_trips or 0,
            first_name=d.user.first_name if d.user else None,
            phone=d.user.phone if d.user else None,
            commission_rate=getattr(d, "commission_rate", None),
        )
        for d in drivers
    ]


@admin_router.get("/drivers/{driver_id}", response_model=AdminDriverDetail)
async def admin_get_driver_detail(
    driver_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    from sqlalchemy.orm import selectinload
    q = (
        select(Driver)
        .options(selectinload(Driver.user))
        .where(Driver.id == driver_id)
    )
    d = (await db.execute(q)).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "Haydovchi topilmadi")
    u = d.user
    return AdminDriverDetail(
        id=d.id,
        user_id=d.user_id,
        first_name=getattr(u, "first_name", None),
        last_name=getattr(u, "last_name", None),
        phone=getattr(u, "phone", None),
        telegram_id=getattr(u, "telegram_id", None),
        car_number=d.car_number or "",
        car_model=d.car_model or "",
        status=d.status,
        is_active=bool(d.is_active),
        is_verified=bool(d.is_verified),
        is_available=bool(d.is_available),
        rating=float(d.rating or 5.0),
        total_trips=int(d.total_trips or 0),
        completed_trips=int(d.completed_trips or 0),
        total_earnings=float(d.total_earnings or 0),
        balance=float(d.balance or 0),
        commission_rate=getattr(d, "commission_rate", None),
        admin_notes=getattr(d, "admin_notes", None),
        blocked_reason=getattr(d, "blocked_reason", None),
    )


@admin_router.patch("/drivers/{driver_id}")
async def admin_update_driver(
    driver_id: int,
    body: AdminDriverUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    driver = await DriverCRUD.get_by_id(db, driver_id)
    if not driver:
        raise HTTPException(404, "Haydovchi topilmadi")
    if body.commission_rate is not None:
        driver.commission_rate = float(body.commission_rate)
    if body.admin_notes is not None:
        driver.admin_notes = body.admin_notes
    await db.execute(
        text("""INSERT INTO admin_logs 
            (admin_user_id, action, details) 
            VALUES (:uid, 'driver_update', 
            CAST(:details AS JSONB))"""),
        {"uid": admin.id, "details": json.dumps({"driver_id": driver_id, **body.model_dump(exclude_none=True)})},
    )
    await db.commit()
    return {"ok": True, "driver_id": driver_id}


@admin_router.post("/drivers/{driver_id}/verify")
async def admin_verify_driver(
    driver_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    driver = await DriverCRUD.get_by_id(db, driver_id)
    if not driver:
        raise HTTPException(404, "Haydovchi topilmadi")
    driver.is_verified = True
    await db.commit()
    return {"ok": True}


@admin_router.post("/drivers/{driver_id}/unverify")
async def admin_unverify_driver(
    driver_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    driver = await DriverCRUD.get_by_id(db, driver_id)
    if not driver:
        raise HTTPException(404, "Haydovchi topilmadi")
    driver.is_verified = False
    await db.commit()
    return {"ok": True}


@admin_router.post("/drivers/{driver_id}/block")
async def admin_block_driver(
    driver_id: int,
    reason: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    driver = await DriverCRUD.get_by_id(db, driver_id)
    if not driver:
        raise HTTPException(404, "Haydovchi topilmadi")
    driver.is_active = False
    driver.status = "blocked"
    driver.blocked_reason = reason or "Blocked by admin"
    try:
        await db.execute(
            text("INSERT INTO admin_logs (admin_user_id, action, details) VALUES (:uid, 'driver_block', CAST(:details AS JSONB))"),
            {"uid": admin.id, "details": json.dumps({"driver_id": driver_id, "reason": reason or "Blocked by admin"})},
        )
    except Exception as e:
        logging.getLogger(__name__).warning("Admin log yozilmadi (driver_block): %s", e)
    await db.commit()
    return {"ok": True, "driver_id": driver_id}


@admin_router.post("/drivers/{driver_id}/activate")
async def admin_activate_driver(
    driver_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    driver = await DriverCRUD.get_by_id(db, driver_id)
    if not driver:
        raise HTTPException(404, "Haydovchi topilmadi")
    driver.is_active = True
    driver.status = "active"
    driver.blocked_reason = None
    try:
        await db.execute(
            text("INSERT INTO admin_logs (admin_user_id, action, details) VALUES (:uid, 'driver_activate', CAST(:details AS JSONB))"),
            {"uid": admin.id, "details": json.dumps({"driver_id": driver_id})},
        )
    except Exception as e:
        logging.getLogger(__name__).warning("Admin log yozilmadi (driver_activate): %s", e)
    await db.commit()
    return {"ok": True, "driver_id": driver_id}


# --- Admin Users ---
class AdminUserItem(BaseModel):
    id: int
    telegram_id: int
    first_name: Optional[str] = None
    phone: Optional[str] = None
    role: str
    language_code: Optional[str] = None
    is_blocked: bool
    is_admin: bool


@admin_router.get("/users", response_model=List[AdminUserItem])
async def admin_list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    q = select(User).offset(skip).limit(limit)
    result = await db.execute(q)
    users = result.scalars().all()
    return [
        AdminUserItem(
            id=u.id,
            telegram_id=u.telegram_id,
            first_name=u.first_name,
            phone=u.phone,
            role=u.role,
            language_code=getattr(u, "language_code", None),
            is_blocked=getattr(u, "is_blocked", False),
            is_admin=getattr(u, "is_admin", False),
        )
        for u in users
    ]


# --- Admin Logs ---
class AdminLogItem(BaseModel):
    id: int
    admin_user_id: Optional[int]
    action: str
    details: Optional[dict]
    created_at: Optional[datetime]


@admin_router.get("/logs", response_model=List[AdminLogItem])
async def admin_list_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    import json
    r = await db.execute(
        text("SELECT id, admin_user_id, action, details, created_at FROM admin_logs ORDER BY id DESC OFFSET :sk LIMIT :lim"),
        {"sk": skip, "lim": limit},
    )
    rows = r.fetchall()
    out = []
    for row in rows:
        det = row[3]
        if isinstance(det, str):
            try:
                det = json.loads(det)
            except Exception:
                det = None
        out.append(AdminLogItem(
            id=row[0],
            admin_user_id=row[1],
            action=row[2] or "",
            details=det,
            created_at=row[4],
        ))
    return out


# --- Send message to driver ---
class SendMessageRequest(BaseModel):
    driver_id: int
    message: str


@admin_router.post("/send-message")
async def admin_send_message(
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    driver = await DriverCRUD.get_by_id(db, body.driver_id)
    if not driver:
        raise HTTPException(404, "Haydovchi topilmadi")
    user = await UserCRUD.get_by_id(db, driver.user_id)
    if not user or not user.telegram_id:
        raise HTTPException(400, "Haydovchining Telegram ID topilmadi")
    try:
        from app.bot.telegram_bot import bot
        await bot.send_message(
            chat_id=user.telegram_id,
            text=body.message,
            parse_mode="HTML",
        )
        return {"ok": True, "driver_id": body.driver_id}
    except Exception as e:
        raise HTTPException(500, detail=f"Xabar yuborishda xato: {str(e)}")
