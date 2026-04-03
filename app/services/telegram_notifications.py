"""
Telegram Notification Service - Driver va user'larga xabar yuborish
O'zbek: Buyurtma xabarlari yuborish tizimi
"""
from typing import Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.core.config import settings
from app.core.logger import get_logger
from app.bot.messages import get_text

logger = get_logger(__name__)


class TelegramNotificationService:
    """
    Telegram orqali driver va user'larga xabar yuborish servisi.
    """
    
    def __init__(self, bot: Bot):
        """
        Args:
            bot: Aiogram Bot instance
        """
        self.bot = bot
    
    async def send_new_order_to_driver(
        self,
        driver_id: int,
        order_id: int,
        distance: float,
        pickup_address: Optional[str],
        destination_address: Optional[str],
        estimated_price: Optional[float]
    ) -> bool:
        """
        Driver'ga yangi buyurtma xabari yuborish.
        
        Args:
            driver_id: Driver ID
            order_id: Buyurtma ID
            distance: Masofa (km)
            pickup_address: Olib ketish manzil
            destination_address: Yetkazish manzil
            estimated_price: Taxminiy narx
            
        Returns:
            bool: Yuborilsa True
        """
        try:
            # Driver telegram_id ni olish kerak
            # Bu yerda oddiy qilib driver_id = telegram_id deb olamiz
            # Real kodda database'dan olish kerak
            telegram_id = await self._get_driver_telegram_id(driver_id)
            
            if not telegram_id:
                logger.warning(f"Driver {driver_id} telegram_id topilmadi")
                return False
            
            # Xabar matni
            text = f"""
🚕 <b>YANGI BUYURTMA!</b>

📍 <b>Olib ketish:</b> {pickup_address or "Manzil ko'rsatilmagan"}
📍 <b>Yetkazish:</b> {destination_address or "Manzil ko'rsatilmagan"}

📏 <b>Masofa:</b> {distance} km
💰 <b>Narx:</b> {estimated_price or 0} so'm

⏱ Javob berish uchun 15 soniya vaqtingiz bor!
"""
            
            # Tugmalar
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Qabul qilish",
                        callback_data=f"accept_order:{order_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Rad etish",
                        callback_data=f"reject_order:{order_id}"
                    )
                ]
            ])
            
            # Yuborish
            await self.bot.send_message(
                chat_id=telegram_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"Driver {driver_id}ga buyurtma {order_id} yuborildi")
            return True
            
        except Exception as e:
            logger.error(f"Driver'ga xabar yuborishda xato: {e}")
            return False
    
    async def send_order_accepted_to_user(
        self,
        user_id: int,
        order_id: int,
        driver_name: str,
        driver_phone: str,
        car_model: str,
        car_number: str,
        rating: float
    ) -> bool:
        """
        User'ga buyurtma qabul qilinganligi haqida xabar.
        
        Args:
            user_id: User ID
            order_id: Buyurtma ID
            driver_name: Driver ismi
            driver_phone: Driver telefon
            car_model: Mashina modeli
            car_number: Mashina raqami
            rating: Reyting
            
        Returns:
            bool: Yuborilsa True
        """
        try:
            telegram_id = await self._get_user_telegram_id(user_id)
            
            if not telegram_id:
                return False
            
            text = f"""
✅ <b>BUYURTMA QABUL QILINDI!</b>

👨‍✈️ <b>Haydovchi:</b> {driver_name}
📞 <b>Telefon:</b> {driver_phone}
🚗 <b>Mashina:</b> {car_model}
🔢 <b>Raqam:</b> {car_number}
⭐️ <b>Reyting:</b> {rating}/5.0

Haydovchi yaqinlashmoqda...
"""
            
            await self.bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode="HTML"
            )
            
            logger.info(f"User {user_id}ga buyurtma qabul xabari yuborildi")
            return True
            
        except Exception as e:
            logger.error(f"User'ga xabar yuborishda xato: {e}")
            return False
    
    async def send_order_failed_to_user(
        self,
        user_id: int,
        reason: str
    ) -> bool:
        """
        User'ga buyurtma bekor qilinganligi haqida xabar.
        
        Args:
            user_id: User ID
            reason: Sabab
            
        Returns:
            bool: Yuborilsa True
        """
        try:
            telegram_id = await self._get_user_telegram_id(user_id)
            
            if not telegram_id:
                return False
            
            text = f"""
❌ <b>BUYURTMA BEKOR QILINDI</b>

Sabab: {reason}

Iltimos qaytadan urinib ko'ring yoki qo'llab-quvvatlash xizmatiga murojaat qiling.
"""
            
            await self.bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode="HTML"
            )
            
            logger.info(f"User {user_id}ga bekor qilish xabari yuborildi")
            return True
            
        except Exception as e:
            logger.error(f"User'ga xabar yuborishda xato: {e}")
            return False
    
    async def send_trip_started_to_user(
        self,
        user_id: int,
        driver_name: str
    ) -> bool:
        """
        User'ga safar boshlanganligini bildirish.
        
        Args:
            user_id: User ID
            driver_name: Driver ismi
            
        Returns:
            bool: Yuborilsa True
        """
        try:
            telegram_id = await self._get_user_telegram_id(user_id)
            
            if not telegram_id:
                return False
            
            text = f"""
🚀 <b>SAFAR BOSHLANDI!</b>

Haydovchi <b>{driver_name}</b> yo'lga tushdi.
Yetib borguncha xavfsiz yo'l tilaymiz! 🙏
"""
            
            await self.bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode="HTML"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Trip started xabari yuborishda xato: {e}")
            return False

    async def send_driver_arrived_to_user(
        self,
        user_id: int,
        driver_name: str,
        car_number: str,
        lang: str = "uz",
    ) -> bool:
        """
        User'ga haydovchi manzilga yetib kelganligi haqida xabar.

        Tilga qarab matnlar:
        - uz: "Haydovchi yetib keldi, iltimos chiqing!"
        - ru: "Водитель прибыл, пожалуйста, выходите!"
        - uz_cyrl: "Ҳайдовчи етиб келди, илтимос чиқинг!"
        """
        try:
            telegram_id = await self._get_user_telegram_id(user_id)
            if not telegram_id:
                return False

            lang = (lang or "uz").lower()
            if lang not in ("uz", "ru", "uz_cyrl"):
                lang = "uz"

            if lang == "ru":
                base_text = "🚖 Водитель прибыл, пожалуйста, выходите!"
            elif lang == "uz_cyrl":
                base_text = "🚖 Ҳайдовчи етиб келди, илтимос чиқинг!"
            else:
                base_text = "🚖 Haydovchi yetib keldi, iltimos chiqing!"

            car_info = f"\n\n🚗 Mashina raqami: <b>{car_number}</b>" if car_number else ""

            text = f"""{base_text}

👨‍✈️ Haydovchi: {driver_name}{car_info}
"""

            chat_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=get_text(lang, "user_btn_write_driver"),
                            callback_data="user_chat_tip",
                        )
                    ]
                ]
            )

            await self.bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode="HTML",
                reply_markup=chat_kb,
            )
            logger.info(f"User {user_id}ga haydovchi yetib kelgani haqida xabar yuborildi")
            return True
        except Exception as e:
            logger.error(f"Driver arrived xabari yuborishda xato: {e}")
            return False
    
    async def send_trip_completed_to_user(
        self,
        user_id: int,
        total_price: float,
        distance_km: float,
        duration_minutes: int,
        lang: str = "uz",
    ) -> bool:
        """
        User'ga safar yakunlanganligini bildirish.
        
        Args:
            user_id: User ID
            total_price: Umumiy narx
            distance_km: Masofa
            duration_minutes: Davomiyligi
            lang: Til kodi (uz, ru, uz_cyrl)
            
        Returns:
            bool: Yuborilsa True
        """
        try:
            telegram_id = await self._get_user_telegram_id(user_id)
            
            if not telegram_id:
                return False
            
            lang = (lang or "uz").lower()
            if lang not in ("uz", "ru", "uz_cyrl"):
                lang = "uz"
            
            price_str = f"{int(total_price):,}".replace(",", " ")
            dist_str = f"{distance_km:.1f}" if distance_km else "0"
            text = f"""{get_text(lang, "trip_completed_title")}

📏 <b>Masofa:</b> {dist_str} km
⏱ <b>Vaqt:</b> {duration_minutes} daqiqa
💰 <b>Narx:</b> {price_str} so'm

{get_text(lang, "rate_driver")} ⭐️⭐️⭐️⭐️⭐️
"""
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="⭐️", callback_data="rate:1"),
                    InlineKeyboardButton(text="⭐️⭐️", callback_data="rate:2"),
                    InlineKeyboardButton(text="⭐️⭐️⭐️", callback_data="rate:3"),
                ],
                [
                    InlineKeyboardButton(text="⭐️⭐️⭐️⭐️", callback_data="rate:4"),
                    InlineKeyboardButton(text="⭐️⭐️⭐️⭐️⭐️", callback_data="rate:5"),
                ]
            ])
            
            await self.bot.send_message(
                chat_id=telegram_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Trip completed xabari yuborishda xato: {e}")
            return False
    
    async def _get_driver_telegram_id(self, driver_id: int) -> Optional[int]:
        """
        Driver telegram_id ni olish.
        
        TODO: Database'dan olish kerak!
        Hozircha oddiy qilib driver_id = telegram_id deb qabul qilamiz.
        
        Args:
            driver_id: Driver ID
            
        Returns:
            Optional[int]: Telegram ID
        """
        # Real kodda database'dan olish kerak:
        # driver = await DriverCRUD.get_by_id(db, driver_id)
        # return driver.user.telegram_id
        
        return driver_id  # Vaqtinchalik
    
    async def _get_user_telegram_id(self, user_id: int) -> Optional[int]:
        """
        User telegram_id ni olish.
        
        TODO: Database'dan olish kerak!
        
        Args:
            user_id: User ID
            
        Returns:
            Optional[int]: Telegram ID
        """
        # Real kodda database'dan olish kerak:
        # user = await UserCRUD.get_by_id(db, user_id)
        # return user.telegram_id
        
        return user_id  # Vaqtinchalik
