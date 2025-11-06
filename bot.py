# bot.py
import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiohttp import web

# ---- конфиг ----
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан. Добавь его в Environment Variables.")

# порт для "фиктивного" веб-сервера (Render назначает PORT автоматически)
PORT = int(os.getenv("PORT", "8000"))

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


# --- лёгкий веб-сервер для Render ---
async def start_webserver(port: int):
    app = web.Application()

    async def handle_ok(request):
        return web.Response(text="OK")

    async def handle_health(request):
        return web.json_response({"status": "ok"})

    app.add_routes([
        web.get("/", handle_ok),
        web.get("/healthz", handle_health),
    ])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server started on port {port}")
    # не блокируем: сайт запущен и будет работать параллельно
    return runner  # на случай, если захочешь чисто завершить


# --- запуск бота + веб-сервера ---
async def main():
    # 1) стартим веб-сервер (чтобы Render видел открытый порт)
    try:
        await start_webserver(PORT)
    except Exception as e:
        print("Не удалось стартовать веб-сервер:", e)

    # 2) стартим polling бота
    print("Запускаем Telegram bot polling...")
    await dp.start_polling(bot)
    # при остановке можно закрыть bot и т.д.


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopping...")
