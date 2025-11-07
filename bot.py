import os
import re
import asyncio
from datetime import datetime, timedelta, timezone
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery
)

# ============ CONFIG ============

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

GROUP_ID = int(os.getenv("GROUP_ID", "0"))  # пример: -1001234567890
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}

ROLE_TOPICS = {
    "translator": int(os.getenv("THREAD_TRANSLATOR_ID", "0")),
    "editor":     int(os.getenv("THREAD_EDITOR_ID", "0")),
    "cleaner":    int(os.getenv("THREAD_CLEAN_ID", "0")),
    "typesetter": int(os.getenv("THREAD_TYPES_ID", "0")),
    "gluer":      int(os.getenv("THREAD_GLUE_ID", "0")),
    "curator":    int(os.getenv("THREAD_CURATOR_ID", "0")),
    "beta":       int(os.getenv("THREAD_BETA_ID", "0")),
    "typecheck":  int(os.getenv("THREAD_TYPECHECK_ID", "0")),
}

ROLE_INFO = {
    "translator": {
        "title": "Переводчик",
        "desc": "Переводит реплики и онимы, соблюдая контекст и тон.",
        "guide": "https://example.com/translator_guide",
        "test_folder": "https://drive.google.com/translator_test"
    },
    "editor": {
        "title": "Редактор",
        "desc": "Правит текст после перевода, следит за стилистикой и логикой.",
        "guide": "https://example.com/editor_guide",
        "test_folder": "https://drive.google.com/editor_test"
    },
    "cleaner": {
        "title": "Клинер",
        "desc": "Чистит фон и пузырей, готовит страницу к тайпу.",
        "guide": "https://example.com/cleaner_guide",
        "test_folder": "https://drive.google.com/cleaner_test"
    },
    "typesetter": {
        "title": "Тайпер",
        "desc": "Ставит текст, шрифты и эффекты по гайдам.",
        "guide": "https://example.com/typesetter_guide",
        "test_folder": "https://drive.google.com/typesetter_test"
    },
    "gluer": {
        "title": "Склейщик",
        "desc": "Собирает длинные вертикальные главы/панорамы из кусков.",
        "guide": "https://example.com/gluer_guide",
        "test_folder": "https://drive.google.com/gluer_test"
    },
    "curator": {
        "title": "Куратор",
        "desc": "Ведет процесс, раздает задачи, сверяет дедлайны.",
        "guide": "https://example.com/curator_guide",
        "test_folder": "https://drive.google.com/curator_test"
    },
    "beta": {
        "title": "Бета-ридер",
        "desc": "Читает главы до релиза, ловит шероховатости.",
        "guide": "https://example.com/beta_guide",
        "test_folder": "https://drive.google.com/beta_test"
    },
    "typecheck": {
        "title": "Тайп-чекер",
        "desc": "Проверяет соответствие тайпа гайдам и аккуратность.",
        "guide": "https://example.com/typecheck_guide",
        "test_folder": "https://drive.google.com/typecheck_test"
    },
}

TEST_DEADLINE_DAYS = int(os.getenv("TEST_DEADLINE_DAYS", "3"))
PORT = int(os.getenv("PORT", "10000"))

# ============ BOT CORE ============

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
STATE = {}

# ============ KEYBOARDS ============

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎨 Вакансии", callback_data="vacancies"),
            InlineKeyboardButton(text="🦊 О команде", callback_data="about"),
        ],
        [InlineKeyboardButton(text="📨 Подать заявку", callback_data="apply")]
    ])

def vacancies_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Переводчик", callback_data="v:translator"),
            InlineKeyboardButton(text="Редактор", callback_data="v:editor"),
        ],
        [
            InlineKeyboardButton(text="Клинер", callback_data="v:cleaner"),
            InlineKeyboardButton(text="Тайпер", callback_data="v:typesetter"),
        ],
        [
            InlineKeyboardButton(text="Склейщик", callback_data="v:gluer"),
            InlineKeyboardButton(text="Куратор", callback_data="v:curator"),
        ],
        [
            InlineKeyboardButton(text="Бета-ридер", callback_data="v:beta"),
            InlineKeyboardButton(text="Тайп-чекер", callback_data="v:typecheck"),
        ],
        [InlineKeyboardButton(text="« Назад", callback_data="back:menu"),
         InlineKeyboardButton(text="Подать заявку", callback_data="apply")]
    ])

def back_and_apply_small():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="« Назад", callback_data="back:vacancies"),
            InlineKeyboardButton(text="Подать заявку", callback_data="apply")
        ]
    ])

def apply_roles_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Переводчик", callback_data="a:translator"),
            InlineKeyboardButton(text="Редактор", callback_data="a:editor"),
        ],
        [
            InlineKeyboardButton(text="Клинер", callback_data="a:cleaner"),
            InlineKeyboardButton(text="Тайпер", callback_data="a:typesetter"),
        ],
        [
            InlineKeyboardButton(text="Склейщик", callback_data="a:gluer"),
            InlineKeyboardButton(text="Куратор", callback_data="a:curator"),
        ],
        [
            InlineKeyboardButton(text="Бета-ридер", callback_data="a:beta"),
            InlineKeyboardButton(text="Тайп-чекер", callback_data="a:typecheck"),
        ],
        [InlineKeyboardButton(text="« Назад", callback_data="back:menu")]
    ])

def start_test_keyboard(role_key: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пройти тестовое задание", callback_data=f"starttest:{role_key}")],
        [InlineKeyboardButton(text="« Назад", callback_data="back:applyroles")]
    ])

# ============ HELPERS ============

def role_title(key: str) -> str:
    return ROLE_INFO.get(key, {}).get("title", key)

def role_desc_block(key: str) -> str:
    info = ROLE_INFO.get(key) or {}
    title = info.get("title", key)
    desc = info.get("desc", "Описание скоро будет.")
    return f"{title}\n{desc}"

def apply_info_block(key: str) -> str:
    info = ROLE_INFO.get(key) or {}
    title = info.get("title", key)
    desc = info.get("desc", "Описание скоро будет.")
    guide = info.get("guide", "—")
    return f"{title}\n{desc}\n\nМетодичка: {guide}"

async def render_screen(user_id: int, chat_id: int, text: str, *, reply_markup=None):
    st = STATE.setdefault(user_id, {"msg_id": None})
    msg_id = st.get("msg_id")
    if msg_id:
        try:
            await bot.edit_message_text(text=text, chat_id=chat_id, message_id=msg_id, reply_markup=reply_markup)
            return
        except Exception:
            pass
    sent = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    st["msg_id"] = sent.message_id

# ============ HANDLERS ============

@dp.message(Command("start"))
async def cmd_start(m: Message):
    STATE[m.from_user.id] = {"msg_id": None}
    await render_screen(
        m.from_user.id, m.chat.id,
        "Присоединяйся к команде Tales of Kitsune — магия начинается с первой главы.\n\nВыбери раздел:",
        reply_markup=main_menu()
    )

@dp.callback_query(F.data == "about")
async def on_about(c: CallbackQuery):
    await render_screen(
        c.from_user.id, c.message.chat.id,
        "Tales of Kitsune — команда, которая переводит манхвы с любовью к оригиналу и уважением к читателю.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« Назад", callback_data="back:menu"),
             InlineKeyboardButton(text="Подать заявку", callback_data="apply")]
        ])
    )
    await c.answer()

@dp.callback_query(F.data == "apply")
async def on_apply(c: CallbackQuery):
    await render_screen(c.from_user.id, c.message.chat.id,
        "Выбери специальность для подачи заявки:", reply_markup=apply_roles_keyboard())
    await c.answer()

@dp.callback_query(F.data == "back:menu")
async def on_back_menu(c: CallbackQuery):
    await render_screen(c.from_user.id, c.message.chat.id, "Главное меню:", reply_markup=main_menu())
    await c.answer()

@dp.callback_query(F.data.startswith("a:"))
async def apply_role_intro(c: CallbackQuery):
    key = c.data.split(":", 1)[1]
    await render_screen(
        c.from_user.id, c.message.chat.id,
        apply_info_block(key),
        reply_markup=start_test_keyboard(key)
    )
    await c.answer()

@dp.callback_query(F.data.startswith("starttest:"))
async def start_test(c: CallbackQuery):
    key = c.data.split(":", 1)[1]
    info = ROLE_INFO.get(key, {})
    folder = info.get("test_folder", "—")
    await render_screen(
        c.from_user.id, c.message.chat.id,
        "Заполните анкету по форме ниже:\nИмя / Ник\nОпыт\nЧасовой пояс\nГотовность по времени\n\n"
        f"Папка с тестом: {folder}\nДедлайн: {TEST_DEADLINE_DAYS} дня.",
    )
    await c.answer("Тест выдан")

# ============ /PM (отправка куратором пользователю) ============

@dp.message(Command("pm"))
async def admin_pm(m: Message, command: CommandObject):
    if m.chat.type not in ("supergroup", "group"):
        return
    if ADMIN_IDS and m.from_user.id not in ADMIN_IDS:
        return

    if not command.args:
        await m.reply("Использование: /pm <user_id> [текст] (можно с ответом на сообщение)")
        return

    try:
        parts = command.args.split(maxsplit=1)
        user_id = int(parts[0])
        extra_text = parts[1] if len(parts) > 1 else ""
    except Exception:
        await m.reply("Неверный формат. Пример: /pm 123456 Привет!")
        return

    try:
        await m.delete()
    except Exception:
        pass

    header = "Сообщение от куратора:"
    comment_block = "\n\n".join([t for t in [header, extra_text if extra_text else None] if t])

    try:
        if m.reply_to_message:
            orig_caption = m.reply_to_message.caption or ""
            final_caption = "\n\n".join(
                [t for t in [header, extra_text if extra_text else None, orig_caption if orig_caption else None] if t]
            )
            await m.reply_to_message.copy_to(user_id, caption=final_caption)
        else:
            await bot.send_message(user_id, comment_block or header)
        await bot.send_message(m.chat.id, "Отправлено.")
    except Exception as e:
        await bot.send_message(m.chat.id, f"Не удалось отправить: {e}")

# ============ HTTP KEEPALIVE ============

class _Handler(BaseHTTPRequestHandler):
    def _ok(self):
        body = b"OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        return body

    def do_GET(self):
        if self.path in ("/", "/healthz"):
            self.wfile.write(self._ok())
        else:
            self.send_response(404); self.end_headers()

    def do_HEAD(self):
        if self.path in ("/", "/healthz"):
            self._ok()
        else:
            self.send_response(404); self.end_headers()

    def log_message(self, fmt, *args):
        return

def start_http():
    srv = HTTPServer(("0.0.0.0", PORT), _Handler)
    print(f"HTTP server on {PORT}")
    srv.serve_forever()

async def main():
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass

    Thread(target=start_http, daemon=True).start()
    print("Bot polling…")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
