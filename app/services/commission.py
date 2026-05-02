"""
Komissiya hisoblash va haydovchi balansidan ayirish.
Barcha pul hisob-kitoblari Decimal bilan amalga oshiriladi.
Yakuniy DB/UI qiymatlari butun songa (100 so'mga) yaxlitlanadi.
"""
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.core.config import settings as config
from app.core.database import AsyncSessionLocal
from app.core.logger import get_logger
from app.services.settings_service import get_settings
from app.utils.money_rounding import round_to_100_half_up
from app.models.bonus import BonusTransaction
from app.models.order import Order

logger = get_logger(__name__)

FIXED_COMMISSION = Decimal(str(getattr(config, "FIXED_COMMISSION", 0.0)))
MIN_BALANCE = Decimal(str(getattr(config, "MIN_BALANCE", -5000.0)))

def _to_dec(val) -> Decimal:
    """Har qanday turdagi qiymatni Decimal ga o'girish."""
    if val is None:
        return Decimal("0")
    return Decimal(str(val))


def _calc_commission(fare: Decimal, commission_rate: Decimal) -> Decimal:
    """Komissiya = FIXED_COMMISSION (agar >0) yoki fare × rate/100."""
    if FIXED_COMMISSION > 0:
        return FIXED_COMMISSION
    return Decimal(
        round_to_100_half_up(fare * commission_rate / Decimal("100"))
    )


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
    order,
) -> dict[str, Any]:
    """
    Safar yakunlanganda hisob-kitob:
      1. Haydovchi balansidan komissiya ayirish.
      2. frozen_bonus ni used_bonus sifatida tasdiqlash.
      3. driver.virtual_balance yangilash (used_bonus - commission).
      4. Foydalanuvchiga cashback EARN qo'shish.

    Sessiyanı boshqarish strategiyasi
    ──────────────────────────────────
    • `async with session.begin():` ISHLATILMAYDI. Sababi:
        – begin() context manager exception bo'lganda rollback() chaqiradi,
          so'ng tashqi except bloki yana rollback() chaqirsa
          "Can't operate on closed transaction" xatosi chiqadi.
        – begin() ichida chaqirilgan get_settings(session) ham ichkarida
          db.rollback() chaqirishi mumkin — bu bizning tranzaksiyamizni yopib qo'yadi.
    • O'rniga: await session.begin() → ... → await session.commit()
      va xatolikda finally ichida await session.rollback() + await session.close().
    • get_settings() (ichki sessiya) — faqat DB id=1, keshbek foizi shu yerdan.
    • Telegram xabari commit VA session.close() dan KEYIN yuboriladi (committed flag orqali).
    """
    # ── 0. Primitive IDlarni sessiya ochilishidan OLDIN olamiz ──
    # order detached bo'lishi mumkin; faqat int ustunlarni o'qish xavfsiz
    # (expire_on_commit=False AsyncSessionLocal da o'rnatilgan).
    if not order or not getattr(order, "driver_id", None):
        return {"success": False}

    driver_id = int(getattr(order, "driver_id", 0))
    order_id  = int(getattr(order, "id", 0))
    if not order_id:
        return {"success": False}

    logger.info(
        f"🔄 deduct_commission: order={order_id} driver={driver_id} — dedicated session"
    )

    # ── 1. Settings — DB singleton (alohida sessiya, komissiya tranzaksiyasiga aralashmaydi) ──
    tariff = await get_settings()
    cashback_percent = _to_dec(tariff.cashback_percent)

    # ── 2. Sessiya — manual boshqaruv ──
    session = AsyncSessionLocal()
    committed = False
    # Telegram ogohlantirishni commit + close dan keyin yuborish uchun
    _warn_telegram_id: int | None = None
    _warn_balance: Decimal = Decimal("0")

    try:
        await session.begin()

        from app.crud.user import DriverCRUD, UserCRUD
        from app.models.user import User, BalanceTransaction

        # ── 3. Order lock (idempotent himoya) ──
        res = await session.execute(
            select(Order).where(Order.id == order_id).with_for_update()
        )
        order_db = res.scalar_one_or_none()
        if not order_db:
            await session.rollback()
            return {"success": False}

        # ── 4. Idempotent: allaqachon hisoblangan bo'lsa ──
        if getattr(order_db, "commission_deducted_at", None) is not None:
            logger.info(f"Commission allaqachon yechilgan: order={order_id}")
            used_r = await session.execute(
                select(func.coalesce(func.sum(BonusTransaction.amount), 0)).where(
                    BonusTransaction.order_id == order_id,
                    BonusTransaction.transaction_type == "SPEND",
                )
            )
            earn_r = await session.execute(
                select(func.coalesce(func.sum(BonusTransaction.amount), 0)).where(
                    BonusTransaction.order_id == order_id,
                    BonusTransaction.transaction_type == "EARN",
                )
            )
            prev_used     = _to_dec(used_r.scalar_one())
            prev_earned   = _to_dec(earn_r.scalar_one())
            fare_val      = (getattr(order_db, "final_price", None)
                             or getattr(order_db, "estimated_price", None) or 0)
            prev_payable  = max(_to_dec(fare_val) - prev_used, Decimal("0"))
            await session.rollback()   # hech narsa o'zgarmadi — toza yopish
            setattr(order, "used_bonus",    prev_used)
            setattr(order, "cashback_earned", prev_earned)
            setattr(order, "payable_amount", prev_payable)
            return {
                "success": True,
                "used_bonus":     int(prev_used),
                "earned_cashback": int(prev_earned),
                "payable_amount":  int(prev_payable),
                "commission": 0,
            }

        # ── 5. Yakuniy narx ──
        fare_val = (getattr(order_db, "final_price", None)
                    or getattr(order_db, "estimated_price", None))
        if fare_val is None:
            logger.warning(
                f"[PRICE CALCULATED] order={order_id} has no final_price/estimated_price — using 0"
            )
            fare_val = 0
        total_price_dec = Decimal(round_to_100_half_up(_to_dec(fare_val)))
        logger.info(
            f"[PRICE CALCULATED] order={order_id} final_price_basis={int(total_price_dec)} "
            f"cashback_percent={float(cashback_percent)}"
        )

        # ── 6. Driver ──
        driver = await DriverCRUD.get_by_id(session, driver_id)
        if not driver:
            await session.rollback()
            return {"success": False}

        driver_rate = _to_dec(getattr(driver, "commission_rate", None) or tariff.commission_rate)
        commission  = _calc_commission(total_price_dec, driver_rate)

        # ── 7. Bonus SPEND — balans hisoblashdan OLDIN (MIN_BALANCE to'g'ri ishlashi uchun) ──
        actual_used    = Decimal("0")
        earned_cashback = Decimal("0")

        user_res = await session.execute(
            select(User).where(User.id == order_db.user_id).with_for_update()
        )
        user   = user_res.scalar_one_or_none()
        frozen = _to_dec(getattr(order_db, "frozen_bonus", 0))

        if bool(getattr(order_db, "is_bonus_requested", False)) and frozen > 0 and user is not None:
            actual_used = min(frozen, total_price_dec)
            excess      = frozen - actual_used
            if excess > 0:
                user.bonus_balance = float(_to_dec(user.bonus_balance) + excess)
                logger.info(f"♻️ Ortiqcha frozen qaytarildi: order={order_id} excess={excess}")
            order_db.used_bonus   = actual_used
            order_db.frozen_bonus = Decimal("0")
            session.add(BonusTransaction(
                user_id=user.id, order_id=order_id,
                amount=actual_used, transaction_type="SPEND",
            ))
        else:
            order_db.used_bonus = Decimal("0")
            if frozen > 0 and user is not None:
                user.bonus_balance    = float(_to_dec(user.bonus_balance) + frozen)
                order_db.frozen_bonus = Decimal("0")

        # ── 8. Haydovchi balansi: kompensatsiya + komissiya (bitta operatsiya) ──
        balance_before = _to_dec(driver.balance)
        new_balance    = balance_before + actual_used - commission
        net_change     = actual_used - commission

        driver.balance              = float(new_balance)
        driver.total_commission_paid = float(_to_dec(driver.total_commission_paid) + commission)
        driver.total_earnings        = float(_to_dec(driver.total_earnings) + total_price_dec)
        driver.completed_trips       = (driver.completed_trips or 0) + 1
        driver.virtual_balance       = float(_to_dec(driver.virtual_balance) + net_change)

        logger.info(
            f"✅ Driver {driver_id} | order={order_id} | "
            f"balance: {float(balance_before):.0f} → {float(new_balance):.0f} | "
            f"+{float(actual_used):.0f} bonus | -{float(commission):.0f} comm"
        )

        session.add(BalanceTransaction(
            driver_id=driver.id,
            transaction_type="trip_settlement",
            amount=float(net_change),
            balance_before=float(balance_before),
            balance_after=float(new_balance),
            order_id=order_id,
            description=f"Safar #{order_id}: +{int(actual_used)} bonus, -{int(commission)} kom",
        ))

        if new_balance < MIN_BALANCE:
            driver.is_available = False
            logger.warning(
                f"Driver {driver.id} balansi past "
                f"({float(new_balance):.0f} < {float(MIN_BALANCE):.0f}), Offline"
            )
            # Telegram ID ni shu erda olamiz (commit oldida, session ochiq),
            # lekin xabarni commit + close dan KEYIN yuboramiz.
            try:
                drv_user_res = await session.execute(
                    select(User).where(User.id == driver.user_id)
                )
                drv_user = drv_user_res.scalar_one_or_none()
                _warn_telegram_id = getattr(drv_user, "telegram_id", None) if drv_user else None
                _warn_balance     = new_balance
            except Exception:
                pass

        # ── 9. Payable amount ──
        payable_amount = Decimal(
            round_to_100_half_up(max(total_price_dec - actual_used, Decimal("0")))
        )

        # ── 10. Cashback EARN (sozlamalar: yakuniy narx foizi) ──
        if cashback_percent > 0 and total_price_dec > 0:
            earned_cashback = Decimal(
                int(total_price_dec * cashback_percent / Decimal("100"))
            )
        logger.info(
            f"[CASHBACK_DEBUG] total_price={total_price_dec} percent={cashback_percent} earned={earned_cashback}"
        )
        if user is not None and earned_cashback > 0:
            user.bonus_balance = float(_to_dec(user.bonus_balance) + earned_cashback)
            session.add(BonusTransaction(
                user_id=user.id, order_id=order_id,
                amount=earned_cashback, transaction_type="EARN",
            ))
            logger.info(
                f"[CASHBACK APPLIED] order={order_id} user_id={user.id} "
                f"earned_cashback={int(earned_cashback)} basis_fare={int(total_price_dec)}"
            )

        # ── 11. Caller order ob'ektiga qiymatlarni yozamiz ──
        setattr(order, "used_bonus",      actual_used)
        setattr(order, "cashback_earned", earned_cashback)
        setattr(order, "payable_amount",  payable_amount)
        setattr(order, "_commission",     commission)

        # ── 12. Idempotent flag ──
        order_db.commission_deducted_at = func.now()

        await session.commit()
        committed = True

        return {
            "success": True,
            "used_bonus":      int(actual_used),
            "earned_cashback": int(earned_cashback),
            "payable_amount":  int(payable_amount),
            "commission":      int(commission),
        }

    except Exception as e:
        logger.error(f"deduct_commission xato: {e}", exc_info=True)
        try:
            await session.rollback()
        except Exception:
            pass
        raise

    finally:
        await session.close()
        # Telegram xabari faqat muvaffaqiyatli commit dan keyin yuboriladi
        if committed and _warn_telegram_id:
            try:
                from app.bot.telegram_bot import bot
                await bot.send_message(
                    chat_id=_warn_telegram_id,
                    text=(
                        f"⚠️ <b>BALANS YETARLI EMAS</b>\n\n"
                        f"Balansingiz: <b>{int(_warn_balance):,} so'm</b>\n"
                        f"Minimal talab: <b>{int(MIN_BALANCE):,} so'm</b>\n\n"
                        f"Balansni to'ldiring."
                    ).replace(",", " "),
                    parse_mode="HTML",
                )
            except Exception as tg_err:
                logger.error(f"Haydovchiga balans ogohlantirish xato: {tg_err}")
