from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
import asyncio
import os

# токен и айди канала нужно задать в Render в "Environment Variables"
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# --- клавиатура при /start ---
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


# --- команды ---
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
        "🦊 **Tales of Kitsune** — это команда, создающая качественные переводы и оформление манхв.\n\n"
        "Мы объединяем переводчиков, редакторов и дизайнеров, чтобы оживлять истории с атмосферой и вниманием к деталям."
    )


@dp.callback_query(F.data == "apply")
async def show_apply(call):
    await call.message.answer(
        "📨 Чтобы подать заявку, отправь сюда сообщение в формате:\n\n"
        "Имя / Никнейм\n"
        "Возраст (по желанию)\n"
        "Желаемая роль\n"
        "Небольшое описание опыта (если есть)\n\n"
        "После этого куратор свяжется с тобой для выдачи тестового задания."
    )


# --- запуск ---
async def main():
    print("Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
@dp.message()
async def get_thread_id(m: Message):
    if m.is_topic_message:
        await m.answer(f"🩶 ID этой темы: `{m.message_thread_id}`")
    else:
        await m.answer("🖤 Это не сообщение внутри темы.")
