"""
Admin Handlers - Statistika, Tasdiqlash, Xabar yuborish
"""
from aiogram import Router, F
from aiogram.filters import Command, Filter
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta

from app.core.database import AsyncSessionLocal
from app.crud.user import UserCRUD, DriverCRUD
from app.models.user import User, UserRole, Driver
from app.models.order import Order, OrderStatus
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

admin_router = Router()


# ================================
# ADMIN FILTER
# ================================
# Parol kutish holati (state)
class AdminAuth(StatesGroup):
    waiting_for_password = State()

class AdminFilter(Filter):
    """Faqat admin'lar uchun filter"""
    
    async def __call__(self, message: Message) -> bool:
        # ADMIN_IDS settings'dan olinadi
        admin_ids = getattr(settings, 'ADMIN_IDS', [])
        
        # Agar ADMIN_IDS yo'q bo'lsa, hech kim admin emas
        if not admin_ids:
            return False
        
        return message.from_user.id in admin_ids


# ================================
# FSM STATES
# ================================

class AdminStates(StatesGroup):
    """Admin broadcast uchun"""
    waiting_for_broadcast_message = State()


class AdminRejectDriverState(StatesGroup):
    """Haydovchini rad etishda sabab so'rash"""
    waiting_for_reject_reason = State()


# ================================
# ADMIN MENU
# ================================

def get_admin_keyboard():
    """Admin asosiy menyusi"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="🚕 Tasdiqlash kutayotganlar")],
            [KeyboardButton(text="📢 Xabar yuborish")],
            [KeyboardButton(text="👥 Foydalanuvchilar"), KeyboardButton(text="🚗 Haydovchilar")],
            [KeyboardButton(text="📋 Buyurtmalar")]
        ],
        resize_keyboard=True
    )
    return keyboard


from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# 1. Holatni (state) funksiyadan tashqarida, teparoqda aniqlab olamiz
class AdminAuth(StatesGroup):
    waiting_for_password = State()

# 2. Birinchi funksiya: /admin yozilganda parol so'raydi
@admin_router.message(Command("admin"), AdminFilter())
async def admin_auth_start(message: Message, state: FSMContext):
    """Admin panelga kirish uchun parol so'rash"""
    await message.answer("🔐 <b>ADMIN PANEL</b>\n\nIltimos, kirish parolini kiriting:", parse_mode="HTML")
    await state.set_state(AdminAuth.waiting_for_password)

# 3. Ikkinchi funksiya: Parol kiritilganda uni tekshiradi
@admin_router.message(AdminAuth.waiting_for_password)
async def check_admin_password(message: Message, state: FSMContext):
    """Parolni tekshirish va menyuni ochish"""
    if message.text == settings.ADMIN_PASSWORD:
        await state.clear() # Holatni yakunlaymiz
        await message.delete() # Xavfsizlik uchun kiritilgan parolni chatdan o'chiramiz
        
        # Parol to'g'ri bo'lsa, siz ko'rsatgan menyu ochiladi
        await message.answer(
            "✅ <b>Xush kelibsiz!</b>\n\n"
            "Quyidagi bo'limlardan birini tanlang:",
            reply_markup=get_admin_keyboard(),
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Parol noto'g'ri! Qayta urinib ko'ring yoki bekor qilish uchun /start bosing.")


# ================================
# STATISTIKA
# ================================

@admin_router.message(F.text == "📊 Statistika", AdminFilter())
async def admin_stats(message: Message):
    """Umumiy statistika"""
    async with AsyncSessionLocal() as db:
        # Jami foydalanuvchilar
        total_users_result = await db.execute(
            select(func.count(User.id))
        )
        total_users = total_users_result.scalar()
        
        # Jami haydovchilar
        total_drivers_result = await db.execute(
            select(func.count(Driver.id))
        )
        total_drivers = total_drivers_result.scalar()
        
        # Tasdiqlangan haydovchilar
        verified_drivers_result = await db.execute(
            select(func.count(Driver.id)).where(Driver.is_verified == True)
        )
        verified_drivers = verified_drivers_result.scalar()
        
        # Tasdiqlash kutayotganlar
        pending_drivers_result = await db.execute(
            select(func.count(Driver.id)).where(Driver.is_verified == False)
        )
        pending_drivers = pending_drivers_result.scalar()
        
        # Jami buyurtmalar
        total_orders_result = await db.execute(
            select(func.count(Order.id))
        )
        total_orders = total_orders_result.scalar()
        
        # Bugungi buyurtmalar
        today = datetime.utcnow().date()
        today_orders_result = await db.execute(
            select(func.count(Order.id)).where(
                func.date(Order.created_at) == today
            )
        )
        today_orders = today_orders_result.scalar()
        
        # Bugungi yakunlangan buyurtmalar
        today_completed_result = await db.execute(
            select(func.count(Order.id)).where(
                func.date(Order.created_at) == today,
                Order.status == OrderStatus.COMPLETED
            )
        )
        today_completed = today_completed_result.scalar()
        
        # Online haydovchilar
        online_drivers_result = await db.execute(
            select(func.count(Driver.id)).where(
                Driver.is_available == True
            )
        )
        online_drivers = online_drivers_result.scalar()
        
        await message.answer(
            f"📊 <b>UMUMIY STATISTIKA</b>\n\n"
            f"👥 <b>Foydalanuvchilar:</b>\n"
            f"   • Jami: {total_users}\n\n"
            f"🚗 <b>Haydovchilar:</b>\n"
            f"   • Jami: {total_drivers}\n"
            f"   • Tasdiqlangan: {verified_drivers}\n"
            f"   • Kutayotgan: {pending_drivers}\n"
            f"   • Online: {online_drivers}\n\n"
            f"📋 <b>Buyurtmalar:</b>\n"
            f"   • Jami: {total_orders}\n"
            f"   • Bugun: {today_orders}\n"
            f"   • Bugun yakunlangan: {today_completed}",
            parse_mode="HTML"
        )


# ================================
# TASDIQLASH KUTAYOTGANLAR
# ================================

@admin_router.message(F.text == "🚕 Tasdiqlash kutayotganlar", AdminFilter())
async def pending_drivers_list(message: Message):
    """Tasdiqlash kutayotgan haydovchilar"""
    async with AsyncSessionLocal() as db:
        # Tasdiqlash kutayotganlarni olish
        result = await db.execute(
            select(Driver).where(
                Driver.is_verified == False
            ).order_by(Driver.created_at.desc()).limit(1)
        )
        driver = result.scalar_one_or_none()
        
        if not driver:
            await message.answer(
                "✅ <b>Barcha haydovchilar tasdiqlangan!</b>\n\n"
                "Tasdiqlash kutayotgan haydovchi yo'q.",
                parse_mode="HTML"
            )
            return
        
        # Driver user ma'lumotlari
        driver_user = await UserCRUD.get_by_id(db, driver.user_id)
        
        if not driver_user:
            await message.answer("❌ Xato: User topilmadi")
            return
        
        # Tasdiqlash tugmalari
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Tasdiqlash",
                    callback_data=f"approve_driver:{driver.id}"
                ),
                InlineKeyboardButton(
                    text="❌ Rad etish",
                    callback_data=f"reject_driver:{driver.id}"
                )
            ]
        ])
        
        await message.answer(
            f"🚕 <b>YANGI HAYDOVCHI</b>\n\n"
            f"👤 Ism: {driver_user.first_name} {driver_user.last_name or ''}\n"
            f"📱 Telefon: {driver_user.phone or 'N/A'}\n"
            f"📞 Telegram: @{driver_user.username or 'yoq'}\n\n"
            f"🚗 Mashina: {driver.car_model}\n"
            f"🔢 Raqam: {driver.car_number}\n"
            f"🎨 Rang: {driver.car_color}\n"
            f"📄 Guvohnoma: {driver.license_number}\n\n"
            f"📅 Ro'yxat: {driver.created_at.strftime('%d.%m.%Y %H:%M')}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )


@admin_router.callback_query(F.data.startswith("approve_driver:"), AdminFilter())
async def approve_driver(callback: CallbackQuery):
    """Haydovchini tasdiqlash"""
    try:
        driver_id = int(callback.data.split(":")[1])
        
        async with AsyncSessionLocal() as db:
            driver = await DriverCRUD.get_by_id(db, driver_id)
            
            if not driver:
                await callback.answer("❌ Haydovchi topilmadi", show_alert=True)
                return
            
            if driver.is_verified:
                await callback.answer("✅ Allaqachon tasdiqlangan", show_alert=True)
                return
            
            # Tasdiqlash
            driver.is_verified = True
            driver.is_available = True
            await db.commit()
            
            # Xabarni yangilash
            await callback.message.edit_text(
                f"{callback.message.text}\n\n"
                f"✅ <b>TASDIQLANDI!</b>",
                parse_mode="HTML"
            )
            
            await callback.answer("✅ Haydovchi tasdiqlandi!")
            
            # Haydovchiga xabar yuborish
            from app.bot.telegram_bot import bot
            driver_user = await UserCRUD.get_by_id(db, driver.user_id)
            
            if driver_user:
                try:
                    await bot.send_message(
                        chat_id=driver_user.telegram_id,
                        text=(
                            f"✅ <b>Siz tasdiqlandingiz!</b>\n\n"
                            f"Endi buyurtma olishingiz mumkin.\n\n"
                            f"Ishlashni boshlash uchun:\n"
                            f"1. /driver buyrug'ini yuboring\n"
                            f"2. 'Online' tugmasini bosing\n"
                            f"3. Lokatsiyangizni yuboring\n\n"
                            f"Omad!"
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Haydovchiga xabar yuborishda xato: {e}")
            
            logger.info(f"Driver {driver_id} tasdiqlandi")
            
    except Exception as e:
        logger.error(f"Tasdiqlashda xato: {e}")
        await callback.answer("❌ Xato yuz berdi", show_alert=True)


@admin_router.callback_query(F.data.startswith("reject_driver:"), AdminFilter())
async def reject_driver_start(callback: CallbackQuery, state: FSMContext):
    """Haydovchini rad etish - sabab so'rash"""
    try:
        driver_id = int(callback.data.split(":")[1])

        async with AsyncSessionLocal() as db:
            driver = await DriverCRUD.get_by_id(db, driver_id)
            if not driver:
                await callback.answer("❌ Haydovchi topilmadi", show_alert=True)
                return

        await callback.answer()
        await state.update_data(reject_driver_id=driver_id)
        await state.set_state(AdminRejectDriverState.waiting_for_reject_reason)
        await callback.message.answer("📝 Rad etish sababini yozing (haydovchiga yuboriladi):")
    except Exception as e:
        logger.error(f"Rad etishda xato: {e}")
        await callback.answer("❌ Xato", show_alert=True)


@admin_router.message(AdminRejectDriverState.waiting_for_reject_reason, F.text, AdminFilter())
async def reject_driver_confirm(message: Message, state: FSMContext):
    """Rad etish sababini qabul qilish va haydovchiga yuborish"""
    data = await state.get_data()
    driver_id = data.get("reject_driver_id")
    reason = message.text or "Admin tomonidan rad etildi"
    await state.clear()

    try:
        async with AsyncSessionLocal() as db:
            driver = await DriverCRUD.get_by_id(db, driver_id)
            if not driver:
                await message.answer("❌ Haydovchi topilmadi")
                return

            driver_user = await UserCRUD.get_by_id(db, driver.user_id)
            user_id_for_msg = driver.user_id

            await db.delete(driver)
            await db.commit()

            from app.bot.telegram_bot import bot
            if driver_user:
                try:
                    await bot.send_message(
                        chat_id=driver_user.telegram_id,
                        text=(
                            f"❌ <b>ARIZANGIZ RAD ETILDI</b>\n\n"
                            f"Sabab: {reason}\n\n"
                            f"Qo'shimcha ma'lumot uchun qo'llab-quvvatlash bilan bog'laning."
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Haydovchiga xabar yuborishda xato: {e}")

            await message.answer(f"❌ Haydovchi rad etildi. Sabab yuborildi.")
            logger.info(f"Driver {driver_id} rad etildi: {reason}")
    except Exception as e:
        logger.error(f"Rad etishda xato: {e}")
        await message.answer("❌ Xato yuz berdi")


@admin_router.callback_query(F.data.startswith("deactivate_driver:"), AdminFilter())
async def deactivate_driver(callback: CallbackQuery):
    """Haydovchini chetlashtirish (ishdan bo'shatish)"""
    try:
        driver_id = int(callback.data.split(":")[1])
        async with AsyncSessionLocal() as db:
            driver = await DriverCRUD.get_by_id(db, driver_id)
            if not driver:
                await callback.answer("❌ Haydovchi topilmadi", show_alert=True)
                return
            driver.is_active = False
            driver.is_verified = False
            driver.is_available = False
            await db.commit()
            driver_user = await UserCRUD.get_by_id(db, driver.user_id)
            await callback.message.edit_text(
                f"{callback.message.text}\n\n🚫 <b>CHETLASHTIRILDI</b>",
                parse_mode="HTML"
            )
            await callback.answer("Haydovchi chetlashtirildi")
            if driver_user:
                try:
                    from app.bot.telegram_bot import bot
                    await bot.send_message(
                        chat_id=driver_user.telegram_id,
                        text=(
                            "🚫 <b>Siz ma'muriyat tomonidan tizimdan chetlashtirildingiz.</b>\n\n"
                            "Savollar bo'lsa, adminga murojaat qiling."
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Haydovchiga xabar yuborishda xato: {e}")
            logger.info(f"Driver {driver_id} chetlashtirildi")
    except Exception as e:
        logger.error(f"Chetlashtirishda xato: {e}")
        await callback.answer("❌ Xato", show_alert=True)


@admin_router.callback_query(F.data.startswith("reactivate_driver:"), AdminFilter())
async def reactivate_driver(callback: CallbackQuery):
    """Haydovchini qayta tiklash"""
    try:
        driver_id = int(callback.data.split(":")[1])
        async with AsyncSessionLocal() as db:
            driver = await DriverCRUD.get_by_id(db, driver_id)
            if not driver:
                await callback.answer("❌ Haydovchi topilmadi", show_alert=True)
                return
            driver.is_active = True
            driver.is_verified = True
            await db.commit()
            driver_user = await UserCRUD.get_by_id(db, driver.user_id)
            await callback.message.edit_text(
                f"{callback.message.text}\n\n✅ <b>QAYTA TIKLANDI</b>",
                parse_mode="HTML"
            )
            await callback.answer("Haydovchi qayta tiklandi")
            if driver_user:
                try:
                    from app.bot.telegram_bot import bot
                    await bot.send_message(
                        chat_id=driver_user.telegram_id,
                        text="✅ <b>Siz qayta tiklandingiz!</b>\n\nEndi buyurtma olishingiz mumkin.",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Haydovchiga xabar yuborishda xato: {e}")
            logger.info(f"Driver {driver_id} qayta tiklandi")
    except Exception as e:
        logger.error(f"Qayta tiklashda xato: {e}")
        await callback.answer("❌ Xato", show_alert=True)


# ================================
# XABAR YUBORISH (BROADCAST)
# ================================

@admin_router.message(F.text == "📢 Xabar yuborish", AdminFilter())
async def broadcast_start(message: Message, state: FSMContext):
    """Broadcast boshlash"""
    await message.answer(
        "📢 <b>BARCHA FOYDALANUVCHILARGA XABAR</b>\n\n"
        "Yubormoqchi bo'lgan xabaringizni yozing:",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_broadcast_message)


@admin_router.message(AdminStates.waiting_for_broadcast_message, AdminFilter())
async def broadcast_send(message: Message, state: FSMContext):
    """Xabarni barcha foydalanuvchilarga yuborish"""
    await state.clear()
    
    broadcast_text = message.text
    
    async with AsyncSessionLocal() as db:
        # Barcha foydalanuvchilarni olish
        result = await db.execute(select(User))
        users = result.scalars().all()
        
        success_count = 0
        fail_count = 0
        
        status_msg = await message.answer(
            f"📤 Xabar yuborilmoqda...\n"
            f"Jami: {len(users)} ta foydalanuvchi"
        )
        
        from app.bot.telegram_bot import bot
        
        for user in users:
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"📢 <b>ADMIN XABARI</b>\n\n{broadcast_text}",
                    parse_mode="HTML"
                )
                success_count += 1
            except Exception as e:
                logger.error(f"User {user.id}ga xabar yuborishda xato: {e}")
                fail_count += 1
        
        await status_msg.edit_text(
            f"✅ <b>XABAR YUBORILDI!</b>\n\n"
            f"✅ Yuborildi: {success_count}\n"
            f"❌ Xato: {fail_count}\n"
            f"📊 Jami: {len(users)}",
            parse_mode="HTML"
        )
        
        logger.info(f"Broadcast: {success_count} success, {fail_count} failed")


# ================================
# FOYDALANUVCHILAR
# ================================

@admin_router.message(F.text == "👥 Foydalanuvchilar", AdminFilter())
async def users_list(message: Message):
    """Oxirgi 10 ta foydalanuvchi"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).order_by(User.created_at.desc()).limit(10)
        )
        users = result.scalars().all()
        
        if not users:
            await message.answer("❌ Foydalanuvchilar yo'q")
            return
        
        text = "👥 <b>OXIRGI FOYDALANUVCHILAR</b>\n\n"
        
        for user in users:
            role_emoji = {"user": "👤", "driver": "🚗", "admin": "🔐"}
            text += (
                f"{role_emoji.get(user.role, '👤')} <b>{user.first_name}</b>\n"
                f"   @{user.username or 'yoq'} | {user.role}\n"
                f"   📅 {user.created_at.strftime('%d.%m.%Y')}\n\n"
            )
        
        await message.answer(text, parse_mode="HTML")


# ================================
# HAYDOVCHILAR
# ================================

@admin_router.message(F.text == "🚗 Haydovchilar", AdminFilter())
async def drivers_list(message: Message):
    """Top 10 haydovchi (reyting bo'yicha) - Chetlashtirish/Qayta tiklash tugmalari bilan"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Driver).order_by(Driver.rating.desc()).limit(10)
        )
        drivers = result.scalars().all()
        
        if not drivers:
            await message.answer("❌ Haydovchilar yo'q")
            return
        
        await message.answer("🚗 <b>TOP HAYDOVCHILAR</b>\n\nQuyida boshqarish tugmalari:", parse_mode="HTML")
        
        for idx, driver in enumerate(drivers, 1):
            driver_user = await UserCRUD.get_by_id(db, driver.user_id)
            is_active = getattr(driver, "is_active", True)
            status_txt = "🟢 Faol" if is_active else "🚫 Chetlashtirilgan"
            text = (
                f"{idx}. <b>{driver_user.first_name if driver_user else 'N/A'}</b> ({status_txt})\n"
                f"   🚗 {driver.car_model} ({driver.car_number})\n"
                f"   ⭐️ {driver.rating:.1f} | 🚕 {driver.total_trips} safar\n"
                f"   💰 {driver.total_earnings:.0f} so'm\n"
            )
            if is_active:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🚫 Chetlashtirish", callback_data=f"deactivate_driver:{driver.id}")]
                ])
            else:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Qayta tiklash", callback_data=f"reactivate_driver:{driver.id}")]
                ])
            await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ================================
# BUYURTMALAR
# ================================

@admin_router.message(F.text == "📋 Buyurtmalar", AdminFilter())
async def orders_list(message: Message):
    """Oxirgi 10 ta buyurtma"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Order).order_by(Order.created_at.desc()).limit(10)
        )
        orders = result.scalars().all()
        
        if not orders:
            await message.answer("❌ Buyurtmalar yo'q")
            return
        
        text = "📋 <b>OXIRGI BUYURTMALAR</b>\n\n"
        
        status_emoji = {
            OrderStatus.PENDING: "⏳",
            OrderStatus.ACCEPTED: "✅",
            OrderStatus.STARTED: "🚗",
            OrderStatus.COMPLETED: "🏁",
            OrderStatus.CANCELLED: "❌"
        }
        
        for order in orders:
            text += (
                f"{status_emoji.get(order.status, '❓')} "
                f"<b>#{order.id}</b> | {order.status}\n"
                f"   💰 {order.estimated_price or 0:.0f} so'm\n"
                f"   📅 {order.created_at.strftime('%d.%m %H:%M')}\n\n"
            )
        
        await message.answer(text, parse_mode="HTML")