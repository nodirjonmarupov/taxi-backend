"""
Komissiya hisoblash va haydovchi balansidan ayirish.
Barcha pul hisob-kitoblari Decimal bilan amalga oshiriladi.
Yakuniy DB/UI qiymatlari butun songa (100 so'mga) yaxlitlanadi.
"""
from decimal import Decimal, ROUND_DOWN
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.core.config import settings as config
from app.core.database import AsyncSessionLocal
from app.core.logger import get_logger
from app.services.settings_service import get_settings
from app.models.bonus import BonusTransaction
from app.models.order import Order

logger = get_logger(__name__)

FIXED_COMMISSION = Decimal(str(getattr(config, "FIXED_COMMISSION", 0.0)))
MIN_BALANCE = Decimal(str(getattr(config, "MIN_BALANCE", 5000.0)))

# Yaxlitlash birligi: yakuniy qiymatlar 100 so'mga yaxlitlanadi
_ROUND_UNIT = Decimal("100")


def _to_dec(val) -> Decimal:
    """Har qanday turdagi qiymatni Decimal ga o'girish."""
    if val is None:
        return Decimal("0")
    return Decimal(str(val))


def _round_to_100(val: Decimal) -> Decimal:
    """Pastga 100 so'mga yaxlitlash (100 so'm ≈ eng kichik tiyin birligi)."""
    return (val // _ROUND_UNIT) * _ROUND_UNIT


def _calc_commission(fare: Decimal, commission_rate: Decimal) -> Decimal:
    """Komissiya = FIXED_COMMISSION (agar >0) yoki fare × rate/100."""
    if FIXED_COMMISSION > 0:
        return FIXED_COMMISSION
    return _round_to_100(fare * commission_rate / Decimal("100"))


async def release_frozen_bonus(order_id: int) -> None:
    """
    Buyurtma bekor bo'lganda (order_service orqali) muzlatilgan bonusni qaytarish.
    Faqat commission.py ichidan chaqirilmaydi — cancel_order_user da ishlatiladi.
    Bu funksiya faqat zapas sifatida qoldirilgan (cancel handlerida to'g'ridan-to'g'ri qilinadi).
    """
    async with AsyncSessionLocal() as session:
        try:
            async with session.begin():
                from app.models.user import User
                order_db = await session.execute(
                    select(Order).where(Order.id == order_id).with_for_update()
                )
                order_db = order_db.scalar_one_or_none()
                if not order_db:
                    return
                frozen = _to_dec(getattr(order_db, "frozen_bonus", 0))
                if frozen <= 0:
                    return
                user_row = await session.execute(
                    select(User).where(User.id == order_db.user_id).with_for_update()
                )
                user = user_row.scalar_one_or_none()
                if user:
                    user.bonus_balance = float(_to_dec(user.bonus_balance) + frozen)
                    order_db.frozen_bonus = Decimal("0")
                    logger.info(f"♻️ release_frozen_bonus: order={order_id} frozen={frozen} qaytarildi")
        except Exception as e:
            logger.error(f"release_frozen_bonus xato: {e}")
            try:
                await session.rollback()
            except Exception:
                pass


async def deduct_commission_on_trip_complete(
    db: AsyncSession,
    order,
) -> dict[str, Any]:
    """
    Safar yakunlanganda:
      1. Haydovchi balansidan komissiya ayirish.
      2. Muzlatilgan bonusni (frozen_bonus) used_bonus sifatida tasdiqlash.
      3. Haydovchi virtual_balance'ga: used_bonus - commission neti qo'shish.
      4. Foydalanuvchiga cashback EARN qo'shish.

    Barcha hisob-kitoblar Decimal.
    Idempotent: commission_deducted_at bo'lsa qayta ishlamaydi.
    O'z sessiyasida ishlaydi (MissingGreenlet dan himoya).
    """
    if not order or not getattr(order, "driver_id", None):
        return {"success": False}

    driver_id = int(getattr(order, "driver_id", 0))
    order_id = int(getattr(order, "id", 0))
    if not order_id:
        return {"success": False}

    async with AsyncSessionLocal() as session:
        try:
            async with session.begin():
                from app.crud.user import DriverCRUD, UserCRUD
                from app.models.user import User, BalanceTransaction

                # ── 1. Order row'ni lock qilish (idempotent himoya) ──
                order_db = await session.execute(
                    select(Order).where(Order.id == order_id).with_for_update()
                )
                order_db = order_db.scalar_one_or_none()
                if not order_db:
                    return {"success": False}

                # ── Idempotent: ikki marta ishlamasin ──
                if getattr(order_db, "commission_deducted_at", None) is not None:
                    logger.info(
                        f"Commission allaqachon yechilgan: order_id={order_id}"
                    )
                    # Avvalgi tranzaksiyalardan qiymatlarni qaytaramiz
                    used_sum = await session.execute(
                        select(func.coalesce(func.sum(BonusTransaction.amount), 0)).where(
                            BonusTransaction.order_id == order_id,
                            BonusTransaction.transaction_type == "SPEND",
                        )
                    )
                    earned_sum = await session.execute(
                        select(func.coalesce(func.sum(BonusTransaction.amount), 0)).where(
                            BonusTransaction.order_id == order_id,
                            BonusTransaction.transaction_type == "EARN",
                        )
                    )
                    used_bonus = _to_dec(used_sum.scalar_one())
                    earned_cashback = _to_dec(earned_sum.scalar_one())
                    fare_val = (
                        getattr(order_db, "final_price", None)
                        or getattr(order_db, "estimated_price", None)
                        or 50000
                    )
                    total_price_dec = _to_dec(fare_val)
                    payable_amount = max(total_price_dec - used_bonus, Decimal("0"))

                    setattr(order, "used_bonus", used_bonus)
                    setattr(order, "cashback_earned", earned_cashback)
                    setattr(order, "payable_amount", payable_amount)
                    return {
                        "success": True,
                        "used_bonus": int(used_bonus),
                        "earned_cashback": int(earned_cashback),
                        "payable_amount": int(payable_amount),
                    }

                # ── 2. Yakuniy narx ──
                fare_val = (
                    getattr(order_db, "final_price", None)
                    or getattr(order_db, "estimated_price", None)
                    or 50000
                )
                total_price_dec = _round_to_100(_to_dec(fare_val))

                # ── 3. Driver va tariff ──
                driver = await DriverCRUD.get_by_id(session, driver_id)
                if not driver:
                    return {"success": False}

                tariff = await get_settings(session)
                driver_rate = _to_dec(getattr(driver, "commission_rate", None) or tariff.commission_rate)
                commission = _calc_commission(total_price_dec, driver_rate)
                cashback_percent = _to_dec(tariff.cashback_percent)

                # ── 4. Bonus SPEND — avval aniqlanadi (balans hisoblashdan OLDIN) ──
                # Sabab: kompensatsiya va komissiyan bitta operatsiyada qo'llanadi,
                # MIN_BALANCE tekshiruvi to'g'ri natijaga asoslanishi uchun.
                actual_used = Decimal("0")
                earned_cashback = Decimal("0")

                user_row = await session.execute(
                    select(User).where(User.id == getattr(order_db, "user_id")).with_for_update()
                )
                user = user_row.scalar_one_or_none()

                frozen = _to_dec(getattr(order_db, "frozen_bonus", 0))

                if bool(getattr(order_db, "is_bonus_requested", False)) and frozen > 0 and user is not None:
                    # Taximetr real narxi estimated_price dan farq qilishi mumkin —
                    # shuning uchun final price ga qarab qisqartiramiz.
                    actual_used = min(frozen, total_price_dec)

                    excess = frozen - actual_used
                    if excess > 0:
                        user.bonus_balance = float(_to_dec(user.bonus_balance) + excess)
                        logger.info(
                            f"♻️ Ortiqcha frozen qaytarildi: order={order_id} "
                            f"frozen={frozen} actual={actual_used} excess={excess}"
                        )

                    order_db.used_bonus = actual_used
                    order_db.frozen_bonus = Decimal("0")

                    session.add(
                        BonusTransaction(
                            user_id=user.id,
                            order_id=order_id,
                            amount=actual_used,
                            transaction_type="SPEND",
                        )
                    )
                else:
                    order_db.used_bonus = Decimal("0")
                    if frozen > 0 and user is not None:
                        user.bonus_balance = float(_to_dec(user.bonus_balance) + frozen)
                        order_db.frozen_bonus = Decimal("0")

                # ── 5. Haydovchi balansi: kompensatsiya + komissiyan (bitta hisob) ──
                # Formula: new_balance = balance_before + actual_used - commission
                # Bu tartib muhim: BalanceTransaction ham, MIN_BALANCE tekshiruvi ham
                # to'g'ri (yakuniy) balans asosida ishlaydi.
                balance_before = _to_dec(driver.balance)
                new_balance = balance_before + actual_used - commission
                driver.balance = float(new_balance)
                driver.total_commission_paid = float(_to_dec(driver.total_commission_paid) + commission)
                driver.total_earnings = float(_to_dec(driver.total_earnings) + total_price_dec)
                driver.completed_trips = (driver.completed_trips or 0) + 1

                # virtual_balance: safar bo'yicha net o'zgarish (driver statistikasi uchun)
                net_change = actual_used - commission
                driver.virtual_balance = float(_to_dec(driver.virtual_balance) + net_change)

                logger.info(
                    f"✅ Driver {driver_id} | order={order_id} | "
                    f"balance: {float(balance_before):.0f} → {float(new_balance):.0f} | "
                    f"+{float(actual_used):.0f} bonus comp | -{float(commission):.0f} commission"
                )

                session.add(
                    BalanceTransaction(
                        driver_id=driver.id,
                        transaction_type="trip_settlement",
                        amount=float(net_change),
                        balance_before=float(balance_before),
                        balance_after=float(new_balance),
                        order_id=order_id,
                        description=(
                            f"Safar #{order_id}: "
                            f"+{int(actual_used)} bonus, -{int(commission)} kom"
                        ),
                    )
                )

                if new_balance < MIN_BALANCE:
                    driver.is_available = False
                    logger.warning(
                        f"Driver {driver.id} balansi past ({float(new_balance):.0f} < {float(MIN_BALANCE):.0f}), Offline"
                    )
                    try:
                        from app.bot.telegram_bot import bot
                        driver_user = await UserCRUD.get_by_id(session, driver.user_id)
                        if driver_user and getattr(driver_user, "telegram_id", None):
                            await bot.send_message(
                                chat_id=driver_user.telegram_id,
                                text=(
                                    f"⚠️ <b>BALANS YETARLI EMAS</b>\n\n"
                                    f"Balansingiz: <b>{int(new_balance):,} so'm</b>\n"
                                    f"Minimal talab: <b>{int(MIN_BALANCE):,} so'm</b>\n\n"
                                    f"Balansni to'ldiring."
                                ).replace(",", " "),
                                parse_mode="HTML",
                            )
                    except Exception as e:
                        logger.error(f"Haydovchiga balans ogohlantirish xato: {e}")

                # ── 6. Payable amount ──
                payable_amount = _round_to_100(
                    max(total_price_dec - actual_used, Decimal("0"))
                )

                # ── 7. Cashback EARN ──
                if cashback_percent > 0 and payable_amount > 0:
                    earned_cashback = _round_to_100(
                        payable_amount * cashback_percent / Decimal("100")
                    )

                if user is not None and earned_cashback > 0:
                    user.bonus_balance = float(
                        _to_dec(user.bonus_balance) + earned_cashback
                    )
                    session.add(
                        BonusTransaction(
                            user_id=user.id,
                            order_id=order_id,
                            amount=earned_cashback,
                            transaction_type="EARN",
                        )
                    )

                # ── 8. Caller uchun qiymatlarni order ob'ektiga qo'shamiz ──
                setattr(order, "used_bonus", actual_used)
                setattr(order, "cashback_earned", earned_cashback)
                setattr(order, "payable_amount", payable_amount)
                setattr(order, "_commission", commission)

                # ── 9. Idempotent flag ──
                order_db.commission_deducted_at = func.now()

            return {
                "success": True,
                "used_bonus": int(actual_used),
                "earned_cashback": int(earned_cashback),
                "payable_amount": int(payable_amount),
                "commission": int(commission),
            }
        except Exception as e:
            logger.error(f"deduct_commission xato: {e}")
            try:
                await session.rollback()
            except Exception:
                pass
            raise
