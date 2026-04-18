"""
Ko'p tilli xabarlar - Multi-language translations
"""
from typing import Optional

MESSAGES = {
    "uz": {
        "choose_language": "Tilni tanlang / Выберите язык:",
        "main_menu_cta": "👇 <b>🚕 TAKSI CHAQRISH</b>",
        "welcome_driver": "👋 Xush kelibsiz, {name}!\n\nBirinchi qatordagi tugma — asosiy: 🚕 TAKSI CHAQRISH\n🚗 Haydovchi paneli: /driver",
        "welcome_user": "👋 Xush kelibsiz, {name}!\n\nBirinchi qatordagi tugma — asosiy: 🚕 TAKSI CHAQRISH",
        "order_taxi": "📍 <b>TAKSI CHAQIRISH</b>\n\nJoylashuvingizni yuboring:",
        "order_destination": "🎯 <b>MANZIL</b>\n\nQayerga yetkazish kerak? Manzilni yuboring:",
        "send_location": "📍 Lokatsiya yuborish",
        "btn_order": "🚕 TAKSI CHAQRISH",
        "btn_be_driver": "🚗 Haydovchi bo'lish",
        "btn_orders": "💰 Cashback ishlatish",
        "btn_info": "ℹ️ Ma'lumot",
        "error": "❌ Xatolik. Qaytadan /start bosing.",
        "order_cancelled": "❌ <b>BUYURTMA BEKOR QILINDI</b>\n\nYana buyurtma berish uchun '🚕 TAKSI CHAQRISH' bosing.",
        "order_cancel_fail": "❌ Bekor qilib bo'lmaydi",
        "order_not_found": "❌ Buyurtma topilmadi",
        "order_cancel_success": "Qayta buyurtma berishingiz mumkin:",
        "rated_thanks": "⭐️ <b>RAHMAT!</b>\n\nSiz {score}/5 ball berdingiz.\nFikringiz biz uchun muhim!",
        "already_rated": "Allaqachon bahladingiz",
        "info_text": "ℹ️ <b>TIMGO TAXI BOT</b>\n\n🚕 Tez va ishonchli taksi\n💰 Arzon narxlar\n⭐️ Professional haydovchilar\n📱 24/7 xizmat\n\nBuyurtma: '🚕 TAKSI CHAQRISH'",
        "no_orders": "📜 Sizda hali buyurtmalar yo'q",
        "my_orders_title": "📜 <b>SIZNING BUYURTMALARINGIZ</b>\n\n",
        "order_item": "{emoji} Buyurtma #{id}\n💰 {price:.0f} so'm\n📅 {date}\n━━━━━━━━━━━━━━\n",
        "driver_start": "Avval /start bosing",
        "loc_received": "Joylashuv qabul qilindi. Tasdiqlang.",
        "confirm_order_title": "🚖 Taksi chaqirishni tasdiqlaysizmi?",
        "confirm_order_price": "💰 Taxminiy narx: {price:.0f} so'm\n📏 Masofa: ~{distance:.1f} km",
        "confirm_order_taximeter": "📏 Yakuniy narx va masofa — haydovchi safarni boshlaganda taksometr bo'yicha hisoblanadi.",
        "timer_remaining": "⏳ Qolgan vaqt: {remaining:02d} soniya",
        "confirm_btn": "✅ Tasdiqlash",
        "cancel_btn": "❌ Bekor qilish",
        "time_expired": "❌ Vaqt tugadi. Buyurtma bekor qilindi.",
        "order_cancelled_timeout": "Siz yana qaytadan buyurtma berishingiz mumkin.",
        "no_taxi": "❌ <b>Hozir taxi yo'q.</b>\n\nKeyinroq urinib ko'ring.",
        "order_accepted": "✅ <b>BUYURTMA QABUL QILINDI!</b>\n\n📍 Qayerdan: {plat:.4f}, {plon:.4f}\n📍 Qayerga: {dlat:.4f}, {dlon:.4f}\n💰 Taxminiy narx: {price:.0f} so'm\n\n🔍 Haydovchi qidirilmoqda...",
        "order_accepted_taximeter": "✅ <b>BUYURTMA QABUL QILINDI!</b>\n\n📍 Chaqiriq nuqtasi: {plat:.4f}, {plon:.4f}\n\n🔍 Haydovchi qidirilmoqda...",
        "driver_no_response": "Haydovchi so'rovingizga javob bermadi, boshqa haydovchi qidirilmoqda...",
        "error_try_again": "❌ Xatolik yuz berdi.\n\nQaytadan urinib ko'ring.",
        "driver_found": "🚖 Haydovchi topildi.",
        "driver_arrived": "🚖 Haydovchi yetib keldi.",
        "trip_started": "🚀 Safar boshlandi.",
        "trip_completed": "🏁 Safar yakunlandi.",
        "order_finished": "🏁 Safar yakunlandi. Asosiy menyuga qaytdingiz.",
        "confirmed_short": "⏳ Tasdiqlandi.",
        "cancelled_short": "❌ Buyurtma bekor qilindi.",
        "data_error": "❌ Ma'lumot xato",
        "time_or_data_gone": "❌ Vaqt tugadi yoki ma'lumot yo'q",
        "help_text": "🚕 <b>TaxiBot yordam bo'limi</b>\n\n<b>Mijozlar uchun:</b>\n/order - Taksi chaqirish\n/history - Tarixni ko'rish\n\n<b>Haydovchilar uchun:</b>\n/available - Band emasman\n/unavailable - Bandman\n/location - Lokatsiyani yuborish\n\n<b>Muloqot:</b>\nSafar davomida haydovchi yoki mijozga bot orqali ovozli xabar yoki matn yuborishingiz mumkin.",
        "driver_found_title": "✅ <b>HAYDOVCHI TOPILDI!</b>",
        "taxi_arriving": "🚕 <b>Taksi yetib kelmoqda</b>",
        "track_driver": "🗺 Haydovchini kuzatish",
        "chat_via_bot": "💬 Bot orqali xabar yozishingiz mumkin.",
        "trip_completed_title": "✅ <b>SAFAR YAKUNLANDI!</b>",
        "arrived_at_dest": "🏁 <b>MANZILGA YETIB KELDIK!</b>",
        "trip_finished_thanks": "Safar yakunlandi. Xizmatimizdan foydalanganingiz uchun rahmat!",
        "payment_label": "💰 <b>To'lov:</b> {price} so'm",
        "user_final_bill": "💰 <b>To'lov:</b> {payable} so'm\n🎁 <b>Bonus ishlatildi:</b> {used} so'm\n✨ <b>Cashback berildi:</b> {earned} so'm",
        "driver_final_bill": "💰 <b>Mijoz to'lovi:</b> {payable} so'm\n🎁 <b>Bonus kompensatsiyasi:</b> {used} so'm",
        "rate_driver": "🌟 Iltimos, haydovchini baholang:",
        "driver_near": "🚖 Haydovchi yetib kelishiga juda oz qoldi (50 metrdan kam). Iltimos, chiqishga tayyor turing!",
        "order_rejected": "❌ Buyurtma rad etildi.",
        "trip_finished_driver": "✅ <b>SAFAR YAKUNLANDI!</b>\n\n📦 Buyurtma #{order_id} yopildi.\n💰 Narxi: {price} so'm\n\nSiz yana ONLINE holatdasiz.",
        "commission_label": "Komissiya to'lovi: {commission} so'm",
        "distance_label": "Masofa: {dist} km",
        "driver_fallback": "Haydovchi",
        "trip_completed_check": "✅ Safar yakunlandi",
        "driver_label": "👨‍✈️ <b>Haydovchi:</b>",
        "car_number_label": "Mashina raqami",
        "rating_label": "Reyting",
        "driver_accept_order_body": (
            "✅ <b>BUYURTMA QABUL QILINDI!</b>\n\n"
            "<code>━━━━━━━━━━━━━━━━━━━━</code>\n"
            "🔔 <b>CHAT FAOL</b>\n"
            "<code>━━━━━━━━━━━━━━━━━━━━</code>\n\n"
            "📍 <b>Buyurtma</b> #{order_id}\n\n"
            "💬 <b>Mijoz bilan yozishmalar yoqildi.</b>\n"
            "Taksometr va mijozga yozish — pastdagi tugmalar orqali."
        ),
        "driver_btn_online": "🟢 Online",
        "driver_btn_offline": "🔴 Offline",
        "driver_btn_link_card": "💳 Kartani bog'lash",
        "driver_btn_balance": "💰 Balans",
        "driver_btn_group": "👥 Guruhga qo'shilish",
        "driver_btn_open_taximeter": "🚖 Taksometrni ochish",
        "driver_btn_write_customer": "💬 Mijozga yozish",
        "driver_chat_tip_alert": "Bot orqali yozishingiz mumkin!",
        "taximeter_chat_banner": "💬 CHAT: BOTDA",
        "user_btn_write_driver": "💬 Haydovchiga yozish",
        "user_chat_tip_alert": "Xabar yozing, u haydovchiga yetkaziladi",
        "btn_bonus_request": "🎁 Bonusdan foydalanish",
        "bonus_request_success": "✅ Bonusdan foydalanish yoqildi. Safar tugaganda hisoblanadi.",
        "bonus_request_already": "🎁 Bonusdan foydalanish allaqachon so'ralgan.",
        "cashback_header": (
            "💰 <b>CASHBACK BALANSI</b>\n\n"
            "💎 Joriy bonus: <b>{balance} so'm</b>\n"
            "📊 Har safardan: <b>{earn_pct}% cashback</b>\n"
            "🎯 Maksimal ishlatish: <b>{max_pct}% (bir safardan)</b>\n\n"
            "Keyingi safaringizda bonusingizni ishlatmoqchimisiz?"
        ),
        "cashback_zero": (
            "💰 <b>CASHBACK</b>\n\n"
            "Hozircha bonusingiz yo'q: <b>0 so'm</b>\n\n"
            "✨ Har safardan <b>{earn_pct}%</b> cashback to'planadi!\n"
            "Keyingi safardan keyin bu yerdan foydalanishingiz mumkin."
        ),
        "cashback_activated": (
            "✅ <b>Cashback yoqildi!</b>\n\n"
            "Keyingi safaringizda <b>{balance} so'm</b> bonusingizdan "
            "maksimal <b>{max_allowed} so'm</b> ishlatiladi.\n\n"
            "🚕 Endi taksi chaqiring!"
        ),
        "cashback_deactivated": "❌ Cashback o'chirildi. Bonus saqlanib qoladi.",
        "cashback_already_on": (
            "✅ Cashback allaqachon <b>yoqilgan</b>.\n\n"
            "💎 Bonus: <b>{balance} so'm</b>\n\n"
            "O'chirmoqchimisiz?"
        ),
        "cashback_btn_yes": "✅ Ha, ishlataman",
        "cashback_btn_no": "❌ Yo'q, kerak emas",
        "cashback_btn_disable": "🔕 O'chirish",
        "lang_saved_toast": "✅",
        "driver_err_start_first": "❌ Avval /start bosing",
        "driver_err_generic_retry": "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.",
        "driver_err_generic_short": "❌ Xatolik. Keyinroq urinib ko'ring.",
        "driver_err_group_only_drivers": "❌ Bu tugma faqat haydovchilar uchun.",
        "driver_group_invite_html": '👥 <b>Haydovchilar guruhi:</b> <a href="{url}">Qo\'shilish</a>',
        "driver_not_registered_prompt": "👋 Siz hali haydovchi emassiz.\n\nRo'yxatdan o'tish uchun tugmani bosing:",
        "driver_blocked_full": "🚫 <b>Siz tizimdan chetlashtirilgansiz.</b>\n\nSavollar bo'lsa, adminga murojaat qiling.",
        "driver_panel_body": (
            "👨‍✈️ <b>HAYDOVCHI PANELI</b>\n\n"
            "📛 Ism: {name}\n"
            "🚗 Mashina: {car_model} ({car_number})\n\n"
            "🌟 <b>Reyting: {rating}/5.0</b> {stars}\n"
            "🚕 Safarlar: {trips} ta\n"
            "💰 Balans: {balance} so'm\n"
            "💰 Umumiy daromad: {earnings} so'm\n\n"
            "📡 Holat: {status}{warning}"
        ),
        "driver_already_registered_warn": (
            "⚠️ <b>Siz allaqachon haydovchisiz!</b>\n\n"
            "🚗 Mashina: {car_model}\n"
            "🔢 Raqam: {car_number}\n\n"
            "Quyidagi tugmalardan foydalaning."
        ),
        "driver_reg_phone_prompt": "📱 <b>RO'YXATDAN O'TISH</b>\n\nTelefon raqamingizni yuboring:",
        "driver_btn_send_phone": "📱 Telefon yuborish",
        "driver_phone_ok_next_plate": "✅ Qabul qilindi!\n\n🚗 Mashina raqamini kiriting (masalan: 01A777AA):",
        "driver_phone_use_button": '📱 Iltimos, <b>"Telefon yuborish"</b> tugmasini bosing:',
        "driver_car_accept_model": "✅ Qabul qilindi!\n\n🚙 Mashina modelini tanlang:",
        "driver_pick_car_color": "🎨 Mashina rangini tanlang:",
        "driver_license_prompt": "✅ Qabul qilindi!\n\n📄 Guvohnoma raqamini kiriting:",
        "driver_app_submitted": (
            "✅ <b>ARIZA QABUL QILINDI!</b>\n\n"
            "Ma'lumotlaringiz admin tomonidan tekshirilmoqda.\n"
            "Tasdiqlanganidan keyin xabar olasiz.\n\n"
            "⏳ Iltimos, kuting..."
        ),
        "driver_photo_license_only": (
            "⚠️ Iltimos, <b>faqat rasm</b> yuklang.\n\n"
            "Matn yoki fayl qabul qilinmaydi. Haydovchilik guvohnomasining fotosuratini yuboring:"
        ),
        "driver_err_user_missing": "❌ Xatolik: Foydalanuvchi topilmadi.",
        "driver_err_already_driver_cmd": "⚠️ Siz allaqachon haydovchisiz. /driver bosing.",
        "driver_save_failed": "❌ Ma'lumotlarni saqlashda xatolik yuz berdi.",
        "driver_cb_accept_ok": "✅ Qabul qilindi!",
        "driver_accept_err": "❌ Xato",
        "driver_accept_deactivated": "❌ Siz chetlashtirilgansiz",
        "driver_accept_order_missing": "❌ Buyurtma topilmadi",
        "driver_accept_order_taken": "❌ Buyurtma allaqachon qabul qilingan",
        "driver_accept_busy": "❌ Sizda allaqachon faol buyurtma bor",
        "driver_accept_ok_short": "✅ Qabul qilindi!",
        "driver_accept_fatal": "❌ Xato yuz berdi",
        "driver_reject_ok_toast": "Rad etildi",
        "driver_online_intro": (
            "✅ <b>Siz ONLINE holatdasiz.</b>\n\n"
            "📍 <b>Jonli lokatsiya yuborish:</b>\n"
            "📎 (Biriktirish) → Joylashuv → "
            "Jonli joylashuvimni ulashish → 8 soat\n\n"
            "⚡ Shunday qilib buyurtmalar avtomatik keladi!"
        ),
        "driver_offline_intro": (
            "🔴 <b>Siz OFFLINE holatdasiz.</b>\n\n"
            "📍 Telegram da Live Location ni to'xtating."
        ),
        "driver_location_ok": "✅ <b>Lokatsiya yangilandi!</b>",
        "driver_go_online_err_start": "❌ Xato: Avval /start bosing",
        "driver_go_online_not_driver": "❌ Xato: Siz haydovchi emassiz.\n\n🚗 Haydovchi bo'lish tugmasini bosing.",
        "driver_blocked_panel": "🚫 Siz tizimdan chetlashtirilgansiz. Adminga murojaat qiling.",
        "driver_blocked_short": "🚫 Siz chetlashtirilgansiz.",
        "driver_balance_body": "💰 <b>BALANS</b>\n\n💵 Mavjud: {amount} so'm\n🚕 Safarlar: {trips}",
        "driver_link_card_intro": (
            "💳 <b>KARTANI BOG'LASH</b>\n\n"
            "Karta raqamini kiriting (16 raqam):\n"
            "Masalan: 8600123456789012"
        ),
        "driver_card_wrong_16": "❌ Noto'g'ri format. 16 raqamli karta raqamini kiriting.",
        "driver_card_ok_expire": (
            "✅ Qabul qilindi!\n\n"
            "Amal qilish muddatini kiriting (MMYY):\n"
            "Masalan: 0327 (mart 2027)"
        ),
        "driver_card_wrong_mmyy": "❌ Noto'g'ri format. MMYY formatida kiriting (masalan: 0327)",
        "driver_payme_error": "❌ Payme xatosi.\n\nIltimos qaytadan urinib ko'ring.",
        "driver_payme_error_reason": "❌ Payme xatosi.\n\nSabab: {reason}\n\nIltimos qaytadan urinib ko'ring.",
        "driver_sms_prompt": "📱 <b>SMS KOD YUBORILDI</b>\n\nTelefon: {phone}\n\nSMS kodni kiriting:",
        "driver_generic_retry": "❌ Xatolik yuz berdi.\n\nIltimos qaytadan urinib ko'ring.",
        "driver_sms_wrong_format": "❌ Noto'g'ri format. 6 raqamli kodni kiriting.",
        "driver_card_linked_ok": (
            "✅ <b>KARTA MUVAFFAQIYATLI BOG'LANDI!</b>\n\n"
            "Endi har bir safardan keyin komissiya avtomatik yechiladi."
        ),
        "driver_verify_error_detail": "❌ Xatolik yuz berdi.\n\nSabab: {detail}",
        "driver_finish_order_closed": "⚠️ Buyurtma allaqachon yopilgan",
        "driver_finish_need_taximeter": "⚠️ Avval taksometrda safarni yakunlang (WebApp → SAFARNI YAKUNLASH).",
        "driver_finish_wrong_status": "⚠️ Safar hali boshlanmagan yoki holat noto'g'ri. Avval «Yo'lga chiqdik» bilan boshlang.",
        "driver_finish_not_driver": "⚠️ Bu buyurtmani faqat haydovchi yakunlay oladi.",
        "driver_finish_not_your_order": "⚠️ Bu buyurtma sizga biriktirilmagan.",
        "driver_finish_billing_failed": "❌ Yakuniy narx hisoblanmadi. Internetni tekshirib, qayta urinib ko'ring.",
        "driver_err_fatal_short": "❌ Xatolik yuz berdi",
        "driver_err_x": "❌ Xato",
    },
    "ru": {
        "choose_language": "Выберите язык / Tilni tanlang:",
        "main_menu_cta": "👇 <b>🚕 ЗАКАЗАТЬ ТАКСИ</b>",
        "welcome_driver": "👋 Добро пожаловать, {name}!\n\nПервая кнопка — главное действие: 🚕 ЗАКАЗАТЬ ТАКСИ\n🚗 Панель водителя: /driver",
        "welcome_user": "👋 Добро пожаловать, {name}!\n\nПервая кнопка — главное действие: 🚕 ЗАКАЗАТЬ ТАКСИ",
        "order_taxi": "📍 <b>ЗАКАЗ ТАКСИ</b>\n\nОтправьте ваше местоположение:",
        "order_destination": "🎯 <b>АДРЕС</b>\n\nКуда едем? Отправьте точку на карте:",
        "send_location": "📍 Отправить местоположение",
        "btn_order": "🚕 ЗАКАЗАТЬ ТАКСИ",
        "btn_be_driver": "🚗 Стать водителем",
        "btn_orders": "💰 Использовать кэшбэк",
        "btn_info": "ℹ️ Информация",
        "error": "❌ Ошибка. Нажмите /start снова.",
        "order_cancelled": "❌ <b>ЗАКАЗ ОТМЕНЁН</b>\n\nДля нового заказа нажмите '🚕 ЗАКАЗАТЬ ТАКСИ'.",
        "order_cancel_fail": "❌ Нельзя отменить",
        "order_not_found": "❌ Заказ не найден",
        "order_cancel_success": "Можете снова оформить заказ:",
        "rated_thanks": "⭐️ <b>СПАСИБО!</b>\n\nВы поставили {score}/5 баллов.\nВаше мнение важно для нас!",
        "already_rated": "Вы уже оценили",
        "info_text": "ℹ️ <b>TIMGO TAXI BOT</b>\n\n🚕 Быстрое и надёжное такси\n💰 Низкие цены\n⭐️ Профессиональные водители\n📱 24/7 сервис\n\nЗаказ: '🚕 ЗАКАЗАТЬ ТАКСИ'",
        "no_orders": "📜 У вас пока нет заказов",
        "my_orders_title": "📜 <b>ВАШИ ЗАКАЗЫ</b>\n\n",
        "order_item": "{emoji} Заказ #{id}\n💰 {price:.0f} сум\n📅 {date}\n━━━━━━━━━━━━━━\n",
        "driver_start": "Сначала нажмите /start",
        "loc_received": "Местоположение получено. Подтвердите.",
        "confirm_order_title": "🚖 Подтвердить заказ такси?",
        "confirm_order_price": "💰 Ориентировочная цена: {price:.0f} сум\n📏 Расстояние: ~{distance:.1f} км",
        "confirm_order_taximeter": "📏 Итоговая цена и расстояние — по таксометру после начала поездки.",
        "timer_remaining": "⏳ Осталось: {remaining:02d} сек",
        "confirm_btn": "✅ Подтвердить",
        "cancel_btn": "❌ Отмена",
        "time_expired": "❌ Время вышло. Заказ отменён.",
        "order_cancelled_timeout": "Можете снова оформить заказ.",
        "no_taxi": "❌ <b>Сейчас такси нет.</b>\n\nПопробуйте позже.",
        "order_accepted": "✅ <b>ЗАКАЗ ПРИНЯТ!</b>\n\n📍 Откуда: {plat:.4f}, {plon:.4f}\n📍 Куда: {dlat:.4f}, {dlon:.4f}\n💰 Ориентировочно: {price:.0f} сум\n\n🔍 Ищем водителя...",
        "order_accepted_taximeter": "✅ <b>ЗАКАЗ ПРИНЯТ!</b>\n\n📍 Точка вызова: {plat:.4f}, {plon:.4f}\n\n🔍 Ищем водителя...",
        "driver_no_response": "Водитель не ответил, ищем другого...",
        "error_try_again": "❌ Произошла ошибка.\n\nПопробуйте снова.",
        "driver_found": "🚖 Водитель найден.",
        "driver_arrived": "🚖 Водитель прибыл.",
        "trip_started": "🚀 Поездка началась.",
        "trip_completed": "🏁 Поездка завершена.",
        "order_finished": "🏁 Поездка завершена. Вы вернулись в главное меню.",
        "confirmed_short": "⏳ Подтверждено.",
        "cancelled_short": "❌ Заказ отменён.",
        "data_error": "❌ Ошибка данных",
        "time_or_data_gone": "❌ Время вышло или нет данных",
        "help_text": "🚕 <b>Справка TaxiBot</b>\n\n<b>Для клиентов:</b>\n/order - Заказать такси\n/history - История заказов\n\n<b>Для водителей:</b>\n/available - Свободен\n/unavailable - Занят\n/location - Отправить местоположение\n\n<b>Общение:</b>\nВо время поездки можно отправлять голосовые или текстовые сообщения.",
        "driver_found_title": "✅ <b>ВОДИТЕЛЬ НАЙДЕН!</b>",
        "taxi_arriving": "🚕 <b>Такси в пути</b>",
        "track_driver": "🗺 Отслеживать водителя",
        "chat_via_bot": "💬 Можно писать сообщения через бота.",
        "trip_completed_title": "✅ <b>ПОЕЗДКА ЗАВЕРШЕНА!</b>",
        "arrived_at_dest": "🏁 <b>МЫ НА МЕСТЕ!</b>",
        "trip_finished_thanks": "Поездка завершена. Спасибо, что воспользовались нашим сервисом!",
        "payment_label": "💰 <b>Оплата:</b> {price} сум",
        "user_final_bill": "💰 <b>Оплата:</b> {payable} сум\n🎁 <b>Использовано бонусов:</b> {used} сум\n✨ <b>Кэшбэк:</b> {earned} сум",
        "driver_final_bill": "💰 <b>Оплата от клиента:</b> {payable} сум\n🎁 <b>Компенсация бонусов:</b> {used} сум",
        "rate_driver": "🌟 Оцените водителя:",
        "driver_near": "🚖 Водитель уже почти приехал (меньше 50 метров). Пожалуйста, приготовьтесь выходить!",
        "order_rejected": "❌ Заказ отклонён.",
        "trip_finished_driver": "✅ <b>ПОЕЗДКА ЗАВЕРШЕНА!</b>\n\n📦 Заказ #{order_id} закрыт.\n💰 Стоимость: {price} сум\n\nВы снова ONLINE.",
        "commission_label": "Комиссия: {commission} сум",
        "distance_label": "Расстояние: {dist} км",
        "driver_fallback": "Водитель",
        "trip_completed_check": "✅ Поездка завершена",
        "driver_label": "👨‍✈️ <b>Водитель:</b>",
        "car_number_label": "Номер машины",
        "rating_label": "Рейтинг",
        "driver_accept_order_body": (
            "✅ <b>ЗАКАЗ ПРИНЯТ!</b>\n\n"
            "<code>━━━━━━━━━━━━━━━━━━━━</code>\n"
            "🔔 <b>ЧАТ ФАОЛ</b>\n"
            "<code>━━━━━━━━━━━━━━━━━━━━</code>\n\n"
            "📍 <b>Заказ</b> #{order_id}\n\n"
            "💬 <b>Чат с клиентом включён.</b>\n"
            "Таксометр и переписка — кнопками ниже."
        ),
        "driver_btn_online": "🟢 Онлайн",
        "driver_btn_offline": "🔴 Офлайн",
        "driver_btn_link_card": "💳 Привязать карту",
        "driver_btn_balance": "💰 Баланс",
        "driver_btn_group": "👥 Группа водителей",
        "driver_btn_open_taximeter": "🚖 Открыть таксометр",
        "driver_btn_write_customer": "💬 Написать клиенту",
        "driver_chat_tip_alert": "Можно писать через бота!",
        "taximeter_chat_banner": "💬 ЧАТ: В БОТЕ",
        "user_btn_write_driver": "💬 Написать водителю",
        "user_chat_tip_alert": "Напишите сообщение — оно будет доставлено водителю",
        "btn_bonus_request": "🎁 Использовать бонус",
        "bonus_request_success": "✅ Использование бонуса включено. Начисление/списание произойдёт после завершения поездки.",
        "bonus_request_already": "🎁 Бонус уже запрошен.",
        "cashback_header": (
            "💰 <b>КЭШБЭК БАЛАНС</b>\n\n"
            "💎 Текущий бонус: <b>{balance} сум</b>\n"
            "📊 С каждой поездки: <b>{earn_pct}% кэшбэк</b>\n"
            "🎯 Максимум за поездку: <b>{max_pct}%</b>\n\n"
            "Использовать бонус в следующей поездке?"
        ),
        "cashback_zero": (
            "💰 <b>КЭШБЭК</b>\n\n"
            "Бонусов пока нет: <b>0 сум</b>\n\n"
            "✨ С каждой поездки начисляется <b>{earn_pct}%</b> кэшбэка!\n"
            "После следующей поездки можно будет использовать."
        ),
        "cashback_activated": (
            "✅ <b>Кэшбэк включён!</b>\n\n"
            "В следующей поездке из <b>{balance} сум</b> "
            "будет использовано до <b>{max_allowed} сум</b>.\n\n"
            "🚕 Закажите такси!"
        ),
        "cashback_deactivated": "❌ Кэшбэк отключён. Бонус сохраняется.",
        "cashback_already_on": (
            "✅ Кэшбэк уже <b>включён</b>.\n\n"
            "💎 Бонус: <b>{balance} сум</b>\n\n"
            "Отключить?"
        ),
        "cashback_btn_yes": "✅ Да, использую",
        "cashback_btn_no": "❌ Нет, не нужно",
        "cashback_btn_disable": "🔕 Отключить",
        "lang_saved_toast": "✅",
        "driver_err_start_first": "❌ Сначала нажмите /start",
        "driver_err_generic_retry": "❌ Ошибка. Попробуйте снова.",
        "driver_err_generic_short": "❌ Ошибка. Попробуйте позже.",
        "driver_err_group_only_drivers": "❌ Кнопка только для водителей.",
        "driver_group_invite_html": '👥 <b>Группа водителей:</b> <a href="{url}">Вступить</a>',
        "driver_not_registered_prompt": "👋 Вы ещё не водитель.\n\nНажмите кнопку для регистрации:",
        "driver_blocked_full": "🚫 <b>Вы отстранены.</b>\n\nПо вопросам обратитесь к администратору.",
        "driver_panel_body": (
            "👨‍✈️ <b>ПАНЕЛЬ ВОДИТЕЛЯ</b>\n\n"
            "📛 Имя: {name}\n"
            "🚗 Машина: {car_model} ({car_number})\n\n"
            "🌟 <b>Рейтинг: {rating}/5.0</b> {stars}\n"
            "🚕 Поездок: {trips}\n"
            "💰 Баланс: {balance} сум\n"
            "💰 Всего заработано: {earnings} сум\n\n"
            "📡 Статус: {status}{warning}"
        ),
        "driver_already_registered_warn": (
            "⚠️ <b>Вы уже водитель!</b>\n\n"
            "🚗 Машина: {car_model}\n"
            "🔢 Номер: {car_number}\n\n"
            "Используйте кнопки ниже."
        ),
        "driver_reg_phone_prompt": "📱 <b>РЕГИСТРАЦИЯ</b>\n\nОтправьте номер телефона:",
        "driver_btn_send_phone": "📱 Отправить телефон",
        "driver_phone_ok_next_plate": "✅ Принято!\n\n🚗 Введите госномер (например: 01A777AA):",
        "driver_phone_use_button": '📱 Нажмите кнопку <b>«Отправить телефон»</b>:',
        "driver_car_accept_model": "✅ Принято!\n\n🚙 Выберите модель:",
        "driver_pick_car_color": "🎨 Выберите цвет:",
        "driver_license_prompt": "✅ Принято!\n\n📄 Введите номер удостоверения:",
        "driver_app_submitted": (
            "✅ <b>ЗАЯВКА ПРИНЯТА!</b>\n\n"
            "Данные проверяются администратором.\n"
            "После одобрения вы получите уведомление.\n\n"
            "⏳ Ожидайте..."
        ),
        "driver_photo_license_only": (
            "⚠️ Загрузите <b>только фото</b>.\n\n"
            "Текст и файлы не принимаются. Фото водительского удостоверения:"
        ),
        "driver_err_user_missing": "❌ Пользователь не найден.",
        "driver_err_already_driver_cmd": "⚠️ Вы уже водитель. Нажмите /driver.",
        "driver_save_failed": "❌ Ошибка сохранения данных.",
        "driver_cb_accept_ok": "✅ Принято!",
        "driver_accept_err": "❌ Ошибка",
        "driver_accept_deactivated": "❌ Вы отстранены",
        "driver_accept_order_missing": "❌ Заказ не найден",
        "driver_accept_order_taken": "❌ Заказ уже принят",
        "driver_accept_busy": "❌ У вас уже есть активный заказ",
        "driver_accept_ok_short": "✅ Принято!",
        "driver_accept_fatal": "❌ Произошла ошибка",
        "driver_reject_ok_toast": "Отклонено",
        "driver_online_intro": (
            "✅ <b>Вы ONLINE.</b>\n\n"
            "📍 <b>Живая геолокация:</b>\n"
            "📎 Прикрепить → Местоположение → Трансляция до 8 ч.\n\n"
            "⚡ Так вы будете получать заказы!"
        ),
        "driver_offline_intro": (
            "🔴 <b>Вы OFFLINE.</b>\n\n"
            "📍 Остановите трансляцию геолокации в Telegram."
        ),
        "driver_location_ok": "✅ <b>Местоположение обновлено!</b>",
        "driver_go_online_err_start": "❌ Сначала /start",
        "driver_go_online_not_driver": "❌ Вы не водитель.\n\n🚗 Нажмите «Стать водителем».",
        "driver_blocked_panel": "🚫 Вы отстранены. Обратитесь к администратору.",
        "driver_blocked_short": "🚫 Вы отстранены.",
        "driver_balance_body": "💰 <b>БАЛАНС</b>\n\n💵 Доступно: {amount} сум\n🚕 Поездок: {trips}",
        "driver_link_card_intro": (
            "💳 <b>ПРИВЯЗКА КАРТЫ</b>\n\n"
            "Введите номер карты (16 цифр):\n"
            "Например: 8600123456789012"
        ),
        "driver_card_wrong_16": "❌ Неверный формат. Введите 16 цифр.",
        "driver_card_ok_expire": (
            "✅ Принято!\n\n"
            "Срок действия (ММГГ):\n"
            "Например: 0327 (март 2027)"
        ),
        "driver_card_wrong_mmyy": "❌ Неверный формат. ММГГ (например: 0327)",
        "driver_payme_error": "❌ Ошибка Payme.\n\nПопробуйте снова.",
        "driver_payme_error_reason": "❌ Ошибка Payme.\n\nПричина: {reason}\n\nПопробуйте снова.",
        "driver_sms_prompt": "📱 <b>SMS ОТПРАВЛЕН</b>\n\nТелефон: {phone}\n\nВведите код из SMS:",
        "driver_generic_retry": "❌ Ошибка.\n\nПопробуйте снова.",
        "driver_sms_wrong_format": "❌ Неверный формат. Введите 6 цифр.",
        "driver_card_linked_ok": (
            "✅ <b>КАРТА ПРИВЯЗАНА!</b>\n\n"
            "Комиссия будет списываться автоматически после поездок."
        ),
        "driver_verify_error_detail": "❌ Ошибка.\n\nПричина: {detail}",
        "driver_finish_order_closed": "⚠️ Заказ уже закрыт",
        "driver_finish_need_taximeter": "⚠️ Сначала завершите поездку в таксометре (WebApp → ЗАВЕРШИТЬ).",
        "driver_finish_wrong_status": "⚠️ Поездка не начата. Сначала нажмите «Выехали».",
        "driver_finish_not_driver": "⚠️ Завершить заказ может только водитель.",
        "driver_finish_not_your_order": "⚠️ Этот заказ назначен не вам.",
        "driver_finish_billing_failed": "❌ Не удалось рассчитать итог. Проверьте сеть и повторите.",
        "driver_err_fatal_short": "❌ Ошибка",
        "driver_err_x": "❌ Ошибка",
    },
    "uz_cyrl": {
        "choose_language": "Тилни танланг / Выберите язык:",
        "main_menu_cta": "👇 <b>🚕 ТАКСИ ЧАҚИРИШ</b>",
        "welcome_driver": "👋 Хуш келибсиз, {name}!\n\nБиринчи қатордаги тугма — асосий: 🚕 ТАКСИ ЧАҚИРИШ\n🚗 Ҳайдовчи панели: /driver",
        "welcome_user": "👋 Хуш келибсиз, {name}!\n\nБиринчи қатордаги тугма — асосий: 🚕 ТАКСИ ЧАҚИРИШ",
        "order_taxi": "📍 <b>ТАКСИ ЧАҚИРИШ</b>\n\nЖойлашувингизни юборинг:",
        "order_destination": "🎯 <b>МАНЗИЛ</b>\n\nҚаерга бориш керак? Манзилни юборинг:",
        "send_location": "📍 Локация юбориш",
        "btn_order": "🚕 ТАКСИ ЧАҚИРИШ",
        "btn_be_driver": "🚗 Ҳайдовчи бўлиш",
        "btn_orders": "💰 Cashback ишлатиш",
        "btn_info": "ℹ️ Маълумот",
        "error": "❌ Хатолик. Қайтадан /start босинг.",
        "order_cancelled": "❌ <b>БУЮРТМА БЕКОР ҚИЛИНДИ</b>\n\nЯна буюртма бериш учун '🚕 ТАКСИ ЧАҚИРИШ' босинг.",
        "order_cancel_fail": "❌ Бекор қилиб бўлмайди",
        "order_not_found": "❌ Буюртма топилмади",
        "order_cancel_success": "Қайта буюртма беришингиз мумкин:",
        "rated_thanks": "⭐️ <b>РАҲМАТ!</b>\n\nСиз {score}/5 балл бердингиз.\nФикрингиз биз учун муҳим!",
        "already_rated": "Аллақачон баҳладингиз",
        "info_text": "ℹ️ <b>TIMGO TAXI BOT</b>\n\n🚕 Тез ва ишончли такси\n💰 Арзон нархлар\n⭐️ Профессионал ҳайдовчилар\n📱 24/7 хизмат\n\nБуюртма: '🚕 ТАКСИ ЧАҚИРИШ'",
        "no_orders": "📜 Сизда ҳали буюртмалар йўқ",
        "my_orders_title": "📜 <b>СИЗНИНГ БУЮРТМАЛАРИНГИЗ</b>\n\n",
        "order_item": "{emoji} Буюртма #{id}\n💰 {price:.0f} сўм\n📅 {date}\n━━━━━━━━━━━━━━\n",
        "driver_start": "Аввал /start босинг",
        "loc_received": "Жойлашув қабул қилинди. Тасдиқланг.",
        "confirm_order_title": "🚖 Такси чақиришни тасдиқлайсизми?",
        "confirm_order_price": "💰 Тахминий нарх: {price:.0f} сўм\n📏 Масофа: ~{distance:.1f} км",
        "confirm_order_taximeter": "📏 Якуний нарх ва масофа — ҳайдовчи сафарни бошлаганда таксометр бўйича ҳисобланади.",
        "timer_remaining": "⏳ Қолган вақт: {remaining:02d} сония",
        "confirm_btn": "✅ Тасдиқлаш",
        "cancel_btn": "❌ Бекор қилиш",
        "time_expired": "❌ Вақт тугади. Буюртма бекор қилинди.",
        "order_cancelled_timeout": "Сиз яна қайтадан буюртма беришингиз мумкин.",
        "no_taxi": "❌ <b>Ҳозир такси йўқ.</b>\n\nКейинроқ уриниб кўринг.",
        "order_accepted": "✅ <b>БУЮРТМА ҚАБУЛ ҚИЛИНДИ!</b>\n\n📍 Қаердан: {plat:.4f}, {plon:.4f}\n📍 Қаерга: {dlat:.4f}, {dlon:.4f}\n💰 Тахминий нарх: {price:.0f} сўм\n\n🔍 Ҳайдовчи қидирилмоқда...",
        "order_accepted_taximeter": "✅ <b>БУЮРТМА ҚАБУЛ ҚИЛИНДИ!</b>\n\n📍 Чақирув нуқтаси: {plat:.4f}, {plon:.4f}\n\n🔍 Ҳайдовчи қидирилмоқда...",
        "driver_no_response": "Ҳайдовчи сўровингизга жавоб бермади, бошқа ҳайдовчи қидирилмоқда...",
        "error_try_again": "❌ Хатолик юз берди.\n\nҚайтадан уриниб кўринг.",
        "driver_found": "🚖 Ҳайдовчи топилди.",
        "driver_arrived": "🚖 Ҳайдовчи етиб келди.",
        "trip_started": "🚀 Сафар бошланди.",
        "trip_completed": "🏁 Сафар якунланди.",
        "order_finished": "🏁 Сафар якунланди. Асосий менюга қайтдингиз.",
        "confirmed_short": "⏳ Тасдиқланди.",
        "cancelled_short": "❌ Буюртма бекор қилинди.",
        "data_error": "❌ Маълумот хато",
        "time_or_data_gone": "❌ Вақт тугади ёки маълумот йўқ",
        "help_text": "🚕 <b>TaxiBot ёрдам бўлими</b>\n\n<b>Мижозлар учун:</b>\n/order - Такси чақириш\n/history - Тарихни кўриш\n\n<b>Ҳайдовчилар учун:</b>\n/available - Банд эмасман\n/unavailable - Бандман\n/location - Локацияни юбориш\n\n<b>Мулоқот:</b>\nСафар давомида ҳайдовчи ёки мижозга бот орқали овозли хабар ёки матн юборишингиз мумкин.",
        "driver_found_title": "✅ <b>ҲАЙДОВЧИ ТОПИЛДИ!</b>",
        "taxi_arriving": "🚕 <b>Такси йўлда</b>",
        "track_driver": "🗺 Ҳайдовчини кузатиш",
        "chat_via_bot": "💬 Бот орқали хабар ёзишингиз мумкин.",
        "trip_completed_title": "✅ <b>САФАР ЯКУНЛАНДИ!</b>",
        "arrived_at_dest": "🏁 <b>МАНЗИЛГА ЕТИБ КЕЛДИК!</b>",
        "trip_finished_thanks": "Сафар якунланди. Хизматимиздан фойдаланганингиз учун раҳмат!",
        "payment_label": "💰 <b>Тўлов:</b> {price} сўм",
        "user_final_bill": "💰 <b>Тўлов:</b> {payable} сўм\n🎁 <b>Ишлатилган бонус:</b> {used} сўм\n✨ <b>Кэшбэк берилди:</b> {earned} сўм",
        "driver_final_bill": "💰 <b>Мижоз тўлови:</b> {payable} сўм\n🎁 <b>Бонус компенсацияси:</b> {used} сўм",
        "rate_driver": "🌟 Илтимос, ҳайдовчини баҳоланг:",
        "driver_near": "🚖 Ҳайдовчи етиб келишига жуда оз қолди (50 метрдан кам). Илтимос, чиқишга тайёр туринг!",
        "order_rejected": "❌ Буюртма рад этилди.",
        "trip_finished_driver": "✅ <b>САФАР ЯКУНЛАНДИ!</b>\n\n📦 Буюртма #{order_id} ёпилди.\n💰 Нархи: {price} сўм\n\nСиз яна ONLINE ҳолатдасиз.",
        "commission_label": "Комиссия тўлови: {commission} сўм",
        "distance_label": "Масофа: {dist} км",
        "driver_fallback": "Ҳайдовчи",
        "trip_completed_check": "✅ Сафар якунланди",
        "driver_label": "👨‍✈️ <b>Ҳайдовчи:</b>",
        "car_number_label": "Машина рақами",
        "rating_label": "Рейтинг",
        "driver_accept_order_body": (
            "✅ <b>БУЮРТМА ҚАБУЛ ҚИЛИНДИ!</b>\n\n"
            "<code>━━━━━━━━━━━━━━━━━━━━</code>\n"
            "🔔 <b>ЧАТ ФАОЛ</b>\n"
            "<code>━━━━━━━━━━━━━━━━━━━━</code>\n\n"
            "📍 <b>Буюртма</b> #{order_id}\n\n"
            "💬 <b>Мижоз билан ёзишмалар ёқилди.</b>\n"
            "Таксометр ва мижозга ёзиш — пастдаги тугмалар орқали."
        ),
        "driver_btn_online": "🟢 Online",
        "driver_btn_offline": "🔴 Offline",
        "driver_btn_link_card": "💳 Карта боғлаш",
        "driver_btn_balance": "💰 Баланс",
        "driver_btn_group": "👥 Гуруҳга қўшилиш",
        "driver_btn_open_taximeter": "🚖 Таксометрни очиш",
        "driver_btn_write_customer": "💬 Мижозга ёзиш",
        "driver_chat_tip_alert": "Бот орқали ёзишингиз мумкин!",
        "taximeter_chat_banner": "💬 ЧАТ: БОТДА",
        "user_btn_write_driver": "💬 Ҳайдовчига ёзиш",
        "user_chat_tip_alert": "Хабар ёзинг, у ҳайдовчига етказилади",
        "btn_bonus_request": "🎁 Бонусдан фойдаланиш",
        "bonus_request_success": "✅ Бонусдан фойдаланиш ёқилди. Сафари тугаганда ҳисобланади.",
        "bonus_request_already": "🎁 Бонусдан фойдаланиш аллақачон сўралган.",
        "cashback_header": (
            "💰 <b>CASHBACK БАЛАНСИ</b>\n\n"
            "💎 Жорий бонус: <b>{balance} сўм</b>\n"
            "📊 Ҳар сафардан: <b>{earn_pct}% cashback</b>\n"
            "🎯 Максимал ишлатиш: <b>{max_pct}%</b>\n\n"
            "Кейинги сафарингизда бонусингизни ишлатмоқчимисиз?"
        ),
        "cashback_zero": (
            "💰 <b>CASHBACK</b>\n\n"
            "Ҳозирча бонусингиз йўқ: <b>0 сўм</b>\n\n"
            "✨ Ҳар сафардан <b>{earn_pct}%</b> cashback тўпланади!\n"
            "Кейинги сафардан кейин бу ердан фойдаланишингиз мумкин."
        ),
        "cashback_activated": (
            "✅ <b>Cashback ёқилди!</b>\n\n"
            "Кейинги сафарингизда <b>{balance} сўм</b> бонусингиздан "
            "максимал <b>{max_allowed} сўм</b> ишлатилади.\n\n"
            "🚕 Энди такси чақиринг!"
        ),
        "cashback_deactivated": "❌ Cashback ўчирилди. Бонус сақланиб қолади.",
        "cashback_already_on": (
            "✅ Cashback аллақачон <b>ёқилган</b>.\n\n"
            "💎 Бонус: <b>{balance} сўм</b>\n\n"
            "Ўчирмоқчимисиз?"
        ),
        "cashback_btn_yes": "✅ Ҳа, ишлатаман",
        "cashback_btn_no": "❌ Йўқ, керак эмас",
        "cashback_btn_disable": "🔕 Ўчириш",
        "lang_saved_toast": "✅",
        "driver_err_start_first": "❌ Аввал /start босинг",
        "driver_err_generic_retry": "❌ Хатолик. Қайтадан уриниб кўринг.",
        "driver_err_generic_short": "❌ Хатолик. Кейинроқ уриниб кўринг.",
        "driver_err_group_only_drivers": "❌ Бу тугма фақат ҳайдовчилар учун.",
        "driver_group_invite_html": '👥 <b>Ҳайдовчилар гуруҳи:</b> <a href="{url}">Қўшилиш</a>',
        "driver_not_registered_prompt": "👋 Сиз ҳали ҳайдовчи эмассиз.\n\nРўйхатдан ўтиш учун тугмани босинг:",
        "driver_blocked_full": "🚫 <b>Сиз тизимдан четлатилгансиз.</b>\n\nСаволлар бўлса, админга мурожаат қилинг.",
        "driver_panel_body": (
            "👨‍✈️ <b>ҲАЙДОВЧИ ПАНЕЛИ</b>\n\n"
            "📛 Исм: {name}\n"
            "🚗 Машина: {car_model} ({car_number})\n\n"
            "🌟 <b>Рейтинг: {rating}/5.0</b> {stars}\n"
            "🚕 Сафарлар: {trips} та\n"
            "💰 Баланс: {balance} сўм\n"
            "💰 Умумий даромад: {earnings} сўм\n\n"
            "📡 Ҳолат: {status}{warning}"
        ),
        "driver_already_registered_warn": (
            "⚠️ <b>Сиз аллақачон ҳайдовчисиз!</b>\n\n"
            "🚗 Машина: {car_model}\n"
            "🔢 Рақам: {car_number}\n\n"
            "Қуйидаги тугмалардан фойдаланинг."
        ),
        "driver_reg_phone_prompt": "📱 <b>РЎЙХАТДАН ЎТИШ</b>\n\nТелефон рақамингизни юборинг:",
        "driver_btn_send_phone": "📱 Телефон юбориш",
        "driver_phone_ok_next_plate": "✅ Қабул қилинди!\n\n🚗 Машина рақамини киритинг (масалан: 01A777AA):",
        "driver_phone_use_button": '📱 Илтимос, <b>«Телефон юбориш»</b> тугмасини босинг:',
        "driver_car_accept_model": "✅ Қабул қилинди!\n\n🚙 Машина моделини танланг:",
        "driver_pick_car_color": "🎨 Машина рангини танланг:",
        "driver_license_prompt": "✅ Қабул қилинди!\n\n📄 Гувоҳнома рақамини киритинг:",
        "driver_app_submitted": (
            "✅ <b>АРИЗА ҚАБУЛ ҚИЛИНДИ!</b>\n\n"
            "Маълумотларингиз админ томонидан текширилмоқда.\n"
            "Тасдиқлангандан кейин хабар оласиз.\n\n"
            "⏳ Илтимос, кутинг..."
        ),
        "driver_photo_license_only": (
            "⚠️ Илтимос, <b>фақат расм</b> юкланг.\n\n"
            "Матн ёки файл қабул қилинмайди. Ҳайдовчилик гувоҳномасининг фотосурати:"
        ),
        "driver_err_user_missing": "❌ Хатолик: Фойдаланувчи топилмади.",
        "driver_err_already_driver_cmd": "⚠️ Сиз аллақачон ҳайдовчисиз. /driver босинг.",
        "driver_save_failed": "❌ Маълумотларни сақлашда хатолик юз берди.",
        "driver_cb_accept_ok": "✅ Қабул қилинди!",
        "driver_accept_err": "❌ Хато",
        "driver_accept_deactivated": "❌ Сиз четлатилгансиз",
        "driver_accept_order_missing": "❌ Буюртма топилмади",
        "driver_accept_order_taken": "❌ Буюртма аллақачон қабул қилинган",
        "driver_accept_busy": "❌ Сизда аллақачон фаол буюртма бор",
        "driver_accept_ok_short": "✅ Қабул қилинди!",
        "driver_accept_fatal": "❌ Хато юз берди",
        "driver_reject_ok_toast": "Рад этилди",
        "driver_online_intro": (
            "✅ <b>Сиз ONLINE ҳолатдасиз.</b>\n\n"
            "📍 <b>Жонли локация юбориш:</b>\n"
            "📎 (Бириктириш) → Жойлашув → "
            "Жонли жойлашувимни улашиш → 8 соат\n\n"
            "⚡ Шундай қилиб буюртмалар автоматик келади!"
        ),
        "driver_offline_intro": (
            "🔴 <b>Сиз OFFLINE ҳолатдасиз.</b>\n\n"
            "📍 Telegram да жонли жойлашувни тугатинг."
        ),
        "driver_location_ok": "✅ <b>Локация янгиланди!</b>",
        "driver_go_online_err_start": "❌ Хато: Аввал /start босинг",
        "driver_go_online_not_driver": "❌ Хато: Сиз ҳайдовчи эмассиз.\n\n🚗 Ҳайдовчи бўлиш тугмасини босинг.",
        "driver_blocked_panel": "🚫 Сиз тизимдан четлатилгансиз. Админга мурожаат қилинг.",
        "driver_blocked_short": "🚫 Сиз четлатилгансиз.",
        "driver_balance_body": "💰 <b>БАЛАНС</b>\n\n💵 Мавжуд: {amount} сўм\n🚕 Сафарлар: {trips}",
        "driver_link_card_intro": (
            "💳 <b>КАРТАНИ БОҒЛАШ</b>\n\n"
            "Карта рақамини киритинг (16 рақам):\n"
            "Масалан: 8600123456789012"
        ),
        "driver_card_wrong_16": "❌ Нотўғри формат. 16 рақамли карта рақамини киритинг.",
        "driver_card_ok_expire": (
            "✅ Қабул қилинди!\n\n"
            "Амал қилиш муддатини киритинг (MMYY):\n"
            "Масалан: 0327 (март 2027)"
        ),
        "driver_card_wrong_mmyy": "❌ Нотўғри формат. MMYY форматида киритинг (масалан: 0327)",
        "driver_payme_error": "❌ Payme хатоси.\n\nИлтимос қайтадан уриниб кўринг.",
        "driver_payme_error_reason": "❌ Payme хатоси.\n\nСабаб: {reason}\n\nИлтимос қайтадан уриниб кўринг.",
        "driver_sms_prompt": "📱 <b>SMS КОД ЮБОРИЛДИ</b>\n\nТелефон: {phone}\n\nSMS кодни киритинг:",
        "driver_generic_retry": "❌ Хатолик юз берди.\n\nИлтимос қайтадан уриниб кўринг.",
        "driver_sms_wrong_format": "❌ Нотўғри формат. 6 рақамли кодни киритинг.",
        "driver_card_linked_ok": (
            "✅ <b>КАРТА МУВАФФАҚИЯТЛИ БОҒЛАНДИ!</b>\n\n"
            "Энди ҳар бир сафардан кейин комиссия автоматик ечилади."
        ),
        "driver_verify_error_detail": "❌ Хатолик юз берди.\n\nСабаб: {detail}",
        "driver_finish_order_closed": "⚠️ Буюртма аллақачон ёпилган",
        "driver_finish_need_taximeter": "⚠️ Аввал таксометрда сафарни якунланг (WebApp → САФАРНИ ЯКУНЛАШ).",
        "driver_finish_wrong_status": "⚠️ Сафар бошланмаган. Аввал «Йўлга чиқдик» ни босинг.",
        "driver_finish_not_driver": "⚠️ Бу буюртмани фақат ҳайдовчи якунлай олади.",
        "driver_finish_not_your_order": "⚠️ Бу буюртма сизга бириктирилмаган.",
        "driver_finish_billing_failed": "❌ Якуний нарх ҳисобланмади. Интернетни текширинг.",
        "driver_err_fatal_short": "❌ Хатолик юз берди",
        "driver_err_x": "❌ Хато",
    },
}

DRIVER_REG_BUTTON_TEXTS = frozenset(
    MESSAGES[ln]["btn_be_driver"] for ln in ("uz", "ru", "uz_cyrl")
)

DRIVER_ONLINE_TEXTS = frozenset(
    MESSAGES[ln]["driver_btn_online"] for ln in ("uz", "ru", "uz_cyrl")
)
DRIVER_OFFLINE_TEXTS = frozenset(
    MESSAGES[ln]["driver_btn_offline"] for ln in ("uz", "ru", "uz_cyrl")
)
DRIVER_LINK_CARD_TEXTS = frozenset(
    MESSAGES[ln]["driver_btn_link_card"] for ln in ("uz", "ru", "uz_cyrl")
)
DRIVER_BALANCE_TEXTS = frozenset(
    MESSAGES[ln]["driver_btn_balance"] for ln in ("uz", "ru", "uz_cyrl")
)
DRIVER_GROUP_TEXTS = frozenset(
    MESSAGES[ln]["driver_btn_group"] for ln in ("uz", "ru", "uz_cyrl")
)


def normalize_bot_lang(lang: Optional[str]) -> str:
    """Telegram language_code → MESSAGES kaliti (uz / ru / uz_cyrl)."""
    if not lang:
        return "uz"
    lc = lang.lower().replace("-", "_")
    if lc.startswith("ru"):
        return "ru"
    if lc in ("uz_cyrl", "uzcyrl"):
        return "uz_cyrl"
    return "uz"


def get_text(lang: str, key: str, **kwargs) -> str:
    """Til kodiga qarab matnni qaytaradi. Default: uz."""
    lang = normalize_bot_lang(lang) if lang else "uz"
    if lang not in MESSAGES:
        lang = "uz"
    msg = MESSAGES.get(lang, MESSAGES["uz"]).get(key, MESSAGES["uz"].get(key, key))
    return msg.format(**kwargs) if kwargs else msg
