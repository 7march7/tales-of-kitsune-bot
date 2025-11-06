# bot.py
import os
import asyncio
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

# --- конфиг ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан")

# Render может подставлять PORT сам; если нет, берём 10000 (мы задали его в env)
PORT = int(os.getenv("PORT", "10000"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- клавиатура ---
def start_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎨 Вакансии", callback_data="vacancies"),
            InlineKeyboardButton(text="🦊 О команде", callback_data="about")
        ],
        [
            InlineKeyboardButton(text="📨 Подать заявку", callback_data="apply")
        ]
    ])

# --- хэндлеры ---
@dp.message(Command("start"))
async def start_cmd(m: Message):
    text = (
        "Присоединяйся к команде Tales of Kitsune — магия начинается с первой главы.\n\n"
        "Выбери нужный раздел ниже:"
    )
    await m.answer(text, reply_markup=start_keyboard())

@dp.callback_query(F.data == "vacancies")
async def show_vacancies(call):
    await call.message.answer(
        "🌸 Доступные направления:\n\n"
        "• Переводчик (корейский / английский)\n"
        "• Редактор\n"
        "• Тайпер\n"
        "• Клинер\n"
        "• Корректор\n"
        "• Дизайнер обложек\n\n"
        "Если хочешь узнать подробнее — нажми «Подать заявку»."
    )

@dp.callback_query(F.data == "about")
async def show_about(call):
    await call.message.answer(
        "🦊 Tales of Kitsune — команда, создающая качественные переводы и оформление манхв.\n\n"
        "Мы объединяем переводчиков, редакторов и дизайнеров, чтобы оживлять истории с атмосферой и вниманием к деталям."
    )

@dp.callback_query(F.data == "apply")
async def show_apply(call):
    await call.message.answer(
        "📨 Чтобы подать заявку, отправь сюда сообщение в формате:\n\n"
        "Имя / Никнейм\n"
        "Возраст (по желанию)\n"
        "Желаемая роль\n"
        "Краткое описание опыта (если есть)\n\n"
        "После этого куратор свяжется с тобой для выдачи тестового задания."
    )

# --- простейший HTTP-сервер (чтобы Render видел открытый порт) ---
class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/healthz"):
            body = b"OK"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    # убираем спам в логи
    def log_message(self, fmt, *args): 
        return

def start_http_server():
    server = HTTPServer(("0.0.0.0", PORT), _Handler)
    print(f"HTTP server started on port {PORT}")
    server.serve_forever()

async def main():
    # поднимем HTTP-порт в отдельном потоке
    Thread(target=start_http_server, daemon=True).start()
    print("Starting Telegram bot polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopping...")
