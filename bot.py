import os
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

# ================== CONFIG ==================

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# ID супергруппы (вид -100...)
GROUP_ID = int(os.getenv("GROUP_ID", "0"))

# Админы, которым разрешён /pm в группе
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}

# ID ВКЛАДОК (тем форума) по ролям
# ВАЖНО: для переводчиков один общий ID темы (все языки летят туда)
ROLE_TOPICS = {
    "translator": int(os.getenv("THREAD_TRANSLATOR_ID", "0")),  # общая тема «Переводчики»
    "editor":     int(os.getenv("THREAD_EDITOR_ID", "0")),
    "cleaner":    int(os.getenv("THREAD_CLEAN_ID", "0")),
    "typesetter": int(os.getenv("THREAD_TYPES_ID", "0")),
    "gluer":      int(os.getenv("THREAD_GLUE_ID", "0")),
    "curator":    int(os.getenv("THREAD_CURATOR_ID", "0")),
    "beta":       int(os.getenv("THREAD_BETA_ID", "0")),
    "typecheck":  int(os.getenv("THREAD_TYPECHECK_ID", "0")),
}

# Справочная инфа по ролям (линки подставь свои)
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

# Подъязыки для переводчика (в одну тему)
TRANSLATOR_LANGS = {
    "en": "Английский",
    "es": "Испанский",
    "ko": "Корейский",
    "id": "Индонезийский",
}

TEST_DEADLINE_DAYS = int(os.getenv("TEST_DEADLINE_DAYS", "3"))
PORT = int(os.getenv("PORT", "10000"))  # для Render/Uptime

# ================== BOT CORE ==================

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# Простейшее состояние
# user_id -> {"flow":..., "role":..., "lang":..., "deadline":..., "msg_id":...}
STATE = {}

# ================== KEYBOARDS ==================

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

def translator_langs_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Английский",    callback_data="a:translator_lang:en"),
            InlineKeyboardButton(text="Испанский",     callback_data="a:translator_lang:es"),
        ],
        [
            InlineKeyboardButton(text="Корейский",     callback_data="a:translator_lang:ko"),
            InlineKeyboardButton(text="Индонезийский", callback_data="a:translator_lang:id"),
        ],
        [InlineKeyboardButton(text="« Назад", callback_data="back:applyroles")]
    ])

def start_test_keyboard(role_key: str, lang_code: str | None = None):
    suffix = f":{lang_code}" if lang_code else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пройти тестовое задание", callback_data=f"starttest:{role_key}{suffix}")],
        [InlineKeyboardButton(text="« Назад", callback_data="back:applyroles")]
    ])

# ================== HELPERS ==================

def role_title(key: str) -> str:
    return ROLE_INFO.get(key, {}).get("title", key)

def role_desc_block(key: str) -> str:
    i = ROLE_INFO.get(key) or {}
    return f"{i.get('title', key)}\n{i.get('desc', 'Описание скоро будет.')}"

def apply_info_block(key: str, lang_label: str | None = None) -> str:
    i = ROLE_INFO.get(key) or {}
    lang_line = f"\nЯзык: {lang_label}" if lang_label else ""
    return f"{i.get('title', key)}{lang_line}\n{i.get('desc', 'Описание скоро будет.')}\n\nМетодичка: {i.get('guide','—')}"

async def render_screen(user_id: int, chat_id: int, text: str, *, reply_markup=None):
    st = STATE.setdefault(user_id, {"msg_id": None})
    msg_id = st.get("msg_id")
    if msg_id:
        try:
            await bot.edit_message_text(text=text, chat_id=chat_id, message_id=msg_id, reply_markup=reply_markup)
            return
        except Exception as e:
            print("Edit failed, fallback to send:", e)
    sent = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    st["msg_id"] = sent.message_id

async def schedule_deadline_notify(user_id: int, role_key: str, started_at: datetime, lang_label: str | None = None):
    deadline = started_at + timedelta(days=TEST_DEADLINE_DAYS)
    thread_id = ROLE_TOPICS.get(role_key) or None
    title = role_title(role_key)
    lang_line = f"\nЯзык: {lang_label}" if lang_label else ""
    try:
        text = (
            "⏳ Выдано тестовое задание\n"
            f"Роль: {title}{lang_line}\n"
            f"Пользователь: id {user_id}\n"
            f"Дедлайн: {deadline.strftime('%Y-%m-%d %H:%M %Z') or deadline.isoformat()}"
        )
        if GROUP_ID:
            if thread_id:
                await bot.send_message(GROUP_ID, text, message_thread_id=thread_id)
            else:
                await bot.send_message(GROUP_ID, text)
    except Exception as e:
        print("Error posting assignment:", e)

    # напоминалка пользователю
    now = datetime.now(timezone.utc)
    delta = (deadline.replace(tzinfo=timezone.utc) - now).total_seconds()
    if delta > 0:
        await asyncio.sleep(delta)
        try:
            await bot.send_message(
                user_id,
                f"Напоминание: срок сдачи теста по роли «{title}» истёк. Если нужно продление, ответьте на это сообщение."
            )
        except Exception as e:
            print("Notify user failed:", e)

# ================== HANDLERS ==================

@dp.message(Command("start"))
async def cmd_start(m: Message):
    STATE[m.from_user.id] = {"flow": None, "role": None, "lang": None, "deadline": None, "msg_id": None}
    await render_screen(
        m.from_user.id, m.chat.id,
        "Присоединяйся к команде Tales of Kitsune — магия начинается с первой главы.\n\nВыбери раздел:",
        reply_markup=main_menu()
    )

@dp.message(Command("cancel"))
async def cancel(m: Message):
    STATE.pop(m.from_user.id, None)
    await m.answer("Окей. Режим подачи заявки сброшен. /start чтобы начать заново.")

@dp.message(Command("topicid"))
async def topic_id(m: Message):
    if getattr(m, "is_topic_message", False):
        await m.answer(f"ID этой темы: {m.message_thread_id}")
    else:
        await m.answer("Отправьте /topicid внутри нужной темы (вкладки) группы.")

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

@dp.callback_query(F.data == "vacancies")
async def on_vacancies(c: CallbackQuery):
    st = STATE.setdefault(c.from_user.id, {})
    st.update({"flow": "vacancies", "role": None, "lang": None})
    await render_screen(c.from_user.id, c.message.chat.id, "Выбери специальность:", reply_markup=vacancies_keyboard())
    await c.answer()

@dp.callback_query(F.data == "apply")
async def on_apply(c: CallbackQuery):
    st = STATE.setdefault(c.from_user.id, {})
    st.update({"flow": "apply", "role": None, "lang": None})
    await render_screen(c.from_user.id, c.message.chat.id, "Выбери специальность для подачи заявки:", reply_markup=apply_roles_keyboard())
    await c.answer()

@dp.callback_query(F.data == "back:menu")
async def on_back_menu(c: CallbackQuery):
    st = STATE.setdefault(c.from_user.id, {})
    st.update({"flow": None, "role": None, "lang": None})
    await render_screen(c.from_user.id, c.message.chat.id, "Главное меню:", reply_markup=main_menu())
    await c.answer()

@dp.callback_query(F.data == "back:vacancies")
async def on_back_vacancies(c: CallbackQuery):
    st = STATE.setdefault(c.from_user.id, {})
    st.update({"flow": "vacancies", "role": None, "lang": None})
    await render_screen(c.from_user.id, c.message.chat.id, "Специальности:", reply_markup=vacancies_keyboard())
    await c.answer()

@dp.callback_query(F.data == "back:applyroles")
async def on_back_applyroles(c: CallbackQuery):
    st = STATE.setdefault(c.from_user.id, {})
    st.update({"flow": "apply", "role": None, "lang": None})
    await render_screen(c.from_user.id, c.message.chat.id, "Выбери специальность:", reply_markup=apply_roles_keyboard())
    await c.answer()

# --- Вакансии: показать описание
@dp.callback_query(F.data.startswith("v:"))
async def vacancy_show(c: CallbackQuery):
    key = c.data.split(":", 1)[1]
    st = STATE.setdefault(c.from_user.id, {})
    st["role"] = key
    await render_screen(
        c.from_user.id, c.message.chat.id,
        role_desc_block(key),
        reply_markup=back_and_apply_small()
    )
    await c.answer()

# --- Подача: переводчик требует выбор языка, остальные сразу показывают инфо
@dp.callback_query(F.data.startswith("a:"))
async def apply_role_intro(c: CallbackQuery):
    key = c.data.split(":", 1)[1]
    st = STATE.setdefault(c.from_user.id, {})
    st["role"] = key
    st["lang"] = None

    if key == "translator":
        await render_screen(c.from_user.id, c.message.chat.id, "Выберите язык перевода:", reply_markup=translator_langs_keyboard())
    else:
        await render_screen(c.from_user.id, c.message.chat.id, apply_info_block(key), reply_markup=start_test_keyboard(key))
    await c.answer()

# --- Выбран язык переводчика
@dp.callback_query(F.data.startswith("a:translator_lang:"))
async def translator_lang_selected(c: CallbackQuery):
    _, _, lang_code = c.data.split(":", 2)
    lang_label = TRANSLATOR_LANGS.get(lang_code, "—")
    st = STATE.setdefault(c.from_user.id, {})
    st["role"] = "translator"
    st["lang"] = lang_label

    await render_screen(
        c.from_user.id, c.message.chat.id,
        apply_info_block("translator", lang_label),
        reply_markup=start_test_keyboard("translator", lang_code)
    )
    await c.answer()

# --- Старт теста
@dp.callback_query(F.data.startswith("starttest:"))
async def start_test(c: CallbackQuery):
    parts = c.data.split(":")
    key = parts[1]
    lang_label = None
    if len(parts) >= 3:
        lang_label = TRANSLATOR_LANGS.get(parts[2])

    info = ROLE_INFO.get(key, {})
    folder = info.get("test_folder", "—")
    st = STATE.setdefault(c.from_user.id, {})
    st["deadline"] = datetime.now(timezone.utc)
    if lang_label:
        st["lang"] = lang_label

    await render_screen(
        c.from_user.id, c.message.chat.id,
        "Заполните анкету (одним сообщением — пункты можно перечислить):\n"
        "Имя / Ник\nОпыт (если есть)\nЧасовой пояс\nГотовность по времени\n\n"
        f"Папка с тестовым заданием: {folder}\n"
        f"Дедлайн: {TEST_DEADLINE_DAYS} дня.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« Назад", callback_data="back:applyroles")]
        ])
    )

    asyncio.create_task(
        schedule_deadline_notify(c.from_user.id, key, st["deadline"], st.get("lang"))
    )
    await c.answer("Тест выдан")

# --- Админское PM из группы
@dp.message(Command("pm"))
async def admin_pm(m: Message, command: CommandObject):
    if m.chat.type not in ("supergroup", "group"):
        return
    if ADMIN_IDS and m.from_user.id not in ADMIN_IDS:
        return

    if not command.args:
        await m.reply("Использование: /pm <user_id> <текст>")
        return
    try:
        parts = command.args.split(maxsplit=1)
        user_id = int(parts[0])
        text = parts[1] if len(parts) > 1 else ""
    except Exception:
        await m.reply("Неверный формат. Пример: /pm 12345678 Привет!")
        return

    try:
        await bot.send_message(user_id, f"Сообщение от куратора:\n\n{text}")
        await m.reply("Отправлено.")
    except Exception as e:
        await m.reply(f"Не удалось отправить: {e}")

# --- Приём контента заявки и пересылка в нужную тему
@dp.message()
async def collect_and_forward(m: Message):
    if m.text and m.text.startswith("/"):
        return

    st = STATE.get(m.from_user.id)
    if not st or not st.get("role"):
        return

    role = st["role"]
    title = role_title(role)
    lang_line = f"\nЯзык: {st.get('lang')}" if st.get("lang") else ""
    thread_id = ROLE_TOPICS.get(role) or None   # для translator — общий ID темы «Переводчики»

    header = f"📥 Заявка от @{m.from_user.username or '—'} (id {m.from_user.id})\nРоль: {title}{lang_line}"
    try:
        if GROUP_ID:
            if thread_id:
                await bot.send_message(GROUP_ID, header, message_thread_id=thread_id)
                await m.copy_to(GROUP_ID, message_thread_id=thread_id)
            else:
                await bot.send_message(GROUP_ID, header)
                await m.copy_to(GROUP_ID)
        await bot.send_message(m.chat.id, "Принято. Сообщение отправлено кураторам.")
    except Exception as e:
        print("Forward error:", e)
        await bot.send_message(m.chat.id, "Не удалось отправить кураторам. Проверьте позже.")

# ================== FAKE HTTP (для Render/Uptime) ==================

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

    # Для UptimeRobot (бесплатный HEAD)
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
    # гасим вебхуки, чтобы polling не конфликтовал
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass
    try:
        me = await bot.get_me()
        print(f"Running bot: @{me.username} (id {me.id})")
    except Exception:
        pass

    Thread(target=start_http, daemon=True).start()
    print("Bot polling…")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
