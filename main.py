import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # Adminingizning Telegram ID raqami

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    
    # Agar foydalanuvchi Admin bo'lsa
    if user_id == ADMIN_ID:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("➕ Yangi havola yaratish", callback_data="create_link"))
        markup.add(InlineKeyboardButton("✏️ Tahrirlash", callback_data="edit_link"))
        
        bot.send_message(
            message.chat.id, 
            "👋 Hush kelibsiz, Admin!\nKerakli amalni tanlang:", 
            reply_markup=markup
        )
    else:
        # Oddiy foydalanuvchi uchun
        markup = InlineKeyboardMarkup()
        # Mini App'ni ochish tugmasi (havolani o'zingizning botingiz va app nomingizga o'zgartirasiz)
        web_app_url = "https://t.me/AniXavolaBot/animanxwa?startapp=manhwa=1=1"
        markup.add(InlineKeyboardButton("🎬 Mini App'ni ochish", web_app=WebAppInfo(url=web_app_url)))
        
        bot.send_message(
            message.chat.id, 
            "Salom! Botdan foydalanishingiz mumkin. Quyidagi tugmani bosing:", 
            reply_markup=markup
        )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    if call.data == "create_link":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Yangi havola yaratish uchun parametr yuboring (masalan: manhwa=2=1):")
    elif call.data == "edit_link":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Tahrirlamoqchi bo'lgan havolangizni tanlang:")

if __name__ == '__main__':
    print("Mini App boshqaruv boti ishga tushdi...")
    bot.infinity_polling()
