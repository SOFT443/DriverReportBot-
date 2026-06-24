import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
import threading
import time
import requests
from flask import Flask
from threading import Thread

TOKEN = "7920382185:AAHhvz3nLpE_6y3ByIDCF7u_9jYAmiUxD3k"
ADMIN_IDS = [6272133492, 8082904812]
PLATE, SCHEDULE = range(2)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask приложение для keep-alive
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def ping_self():
    """Каждые 3 минуты пингует самого себя"""
    while True:
        try:
            # Пингуем localhost:8080 (самого себя через Flask)
            response = requests.get('http://localhost:8080/')
            logger.info(f"Self-ping успешен: {response.status_code}")
        except Exception as e:
            logger.error(f"Self-ping ошибка: {e}")
        time.sleep(180)  # 3 минуты

def keep_alive():
    """Запускает Flask сервер и пинг в отдельных потоках"""
    # Запускаем Flask
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    logger.info("Keep-alive сервер запущен на порту 8080")
    
    # Запускаем пинг
    p = Thread(target=ping_self)
    p.daemon = True
    p.start()
    logger.info("Self-ping запущен (каждые 3 минуты)")

def load_plates():
    try:
        with open("valid_plates.txt", "r", encoding="utf-8") as f:
            return [line.strip().upper() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error("Файл valid_plates.txt не найден")
        return []

VALID_PLATES = load_plates()

def normalize_plate(plate: str) -> str:
    return plate.upper().replace(" ", "").replace("-", "")

def is_valid_plate(plate: str) -> bool:
    norm = normalize_plate(plate)
    if norm in VALID_PLATES:
        return True
    if len(norm) > 6:
        without_region = norm[:-3]
    else:
        without_region = norm
    for valid in VALID_PLATES:
        if valid.startswith(without_region) and len(valid) == len(without_region) + 3:
            return True
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Введите государственный номер вашего автомобиля (например, А445ВК797 или А445ВК):"
    )
    return PLATE

async def handle_plate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    plate = update.message.text.strip()
    if not is_valid_plate(plate):
        await update.message.reply_text("Указан неверный номер ТС. Попробуйте снова:")
        return PLATE
    context.user_data["plate"] = normalize_plate(plate)
    await update.message.reply_text(
        "Введите ваш график работы в формате ЧЧ:ММ - ЧЧ:ММ (например, 16:00 - 00:00):"
    )
    return SCHEDULE

async def handle_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    schedule = update.message.text.strip()
    plate = context.user_data.get("plate", "неизвестен")
    user = update.effective_user
    username = user.username if user.username else f"{user.first_name} {user.last_name or ''}"
    user_id = user.id

    msg = (
        f"Новое обращение от водителя:\n"
        f"ID: {user_id}\n"
        f"Имя: {username}\n"
        f"Номер ТС: {plate}\n"
        f"График работы: {schedule}\n"
        f"Время отправки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    await update.message.reply_text(
        f"Ваше обращение принято. Номер ТС: {plate}, график: {schedule}."
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=msg)
        except Exception as e:
            logger.error(f"Не удалось отправить админу {admin_id}: {e}")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning(f"Update {update} caused error {context.error}")

def main() -> None:
    # Запускаем keep-alive с пингом
    keep_alive()
    
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_plate)],
            SCHEDULE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_schedule)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
