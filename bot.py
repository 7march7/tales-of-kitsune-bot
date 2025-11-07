import os
import re
import asyncio
from datetime import datetime, timedelta, timezone
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
from time import monotonic

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

# супергруппа с включенными темами (форум)
GROUP_ID = int(os.getenv("GROUP_ID", "0"))  # пример: -1001234567890

# список админов, кому разрешено /pm из группы
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}

# ID тем по ролям (вкладки форума)
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

# инфо по ролям (подставь свои ссылки при желании)
ROLE_INFO = {
"translator": {
    "title": "Переводчик",
    "desc": """Переводчик — человек, который смотрит на непонятные всем остальным смертным иероглифы 
и пытается извлечь из них хоть какой-то смысл. 
Он живёт на кофе, словарях и щепотке догадок.

Доступные языки:
• Английский
• Испанский
• Корейский
• Индонезийский

Мы не приветствуем машинный перевод (с помощью онлайн-переводчиков и нейросетей).""",
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
        "guide": "https://docs.google.com/document/d/1kfJ18MnWzpWa6n4oSTYEn0tisz3VNC0a/edit?usp=sharing&ouid=104155753409319228630&rtpof=true&sd=true",
        "test_folder": "https://drive.google.com/drive/folders/1jHYnfP7HGuJZFaM_VOJ1UWe-VLrTvLdw?usp=sharing"
    },
}

TEST_DEADLINE_DAYS = int(os.getenv("TEST_DEADLINE_DAYS", "3"))
PORT = int(os.getenv("PORT", "10000"))  # для Render/Uptime

# ============ BOT CORE ============

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# состояние пользователей:
# user_id -> {"flow": ..., "role": ..., "deadline": datetime|None, "msg_id": int|None, "chat_id": int|None}
STATE = {}

# долговременная "память" последней роли пользователя (чтобы принимать сообщения ВСЕГДА)
USER_LAST_ROLE: dict[int, str] = {}

# антидребезг /start
_LAST_START_AT: dict[int, float] = {}

# антидребезг callback-кнопок
_LAST_CB_KEY_AT: dict[tuple[int, str], float] = {}
_CB_DEBOUNCE_SEC = 2.2

# замки на «экран» пользователя
_USER_LOCKS: dict[int, asyncio.Lock] = {}

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
    return ROLE_INFO.get(key, {}).get("title", "—")

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

def _cb_too_fast_for_key(user_id: int, data: str) -> bool:
    key = data.split(":", 1)[0] if data else ""
    now = monotonic()
    last = _LAST_CB_KEY_AT.get((user_id, key), 0.0)
    if now - last < _CB_DEBOUNCE_SEC:
        return True
    _LAST_CB_KEY_AT[(user_id, key)] = now
    return False

async def schedule_deadline_notify(user_id: int, role_key: str, started_at: datetime):
    deadline = started_at + timedelta(days=TEST_DEADLINE_DAYS)
    thread_id = ROLE_TOPICS.get(role_key) or None
    title = role_title(role_key)

    username = ""
    try:
        user = await bot.get_chat(user_id)
        username = f" (@{user.username})" if user.username else ""
    except Exception:
        pass

    try:
        text = (
            "⏳ Выдано тестовое задание\n"
            f"Роль: {title}\n"
            f"Пользователь: id {user_id}{username}\n"
            f"Дедлайн: {deadline.strftime('%Y-%m-%d %H:%M %Z') or deadline.isoformat()}"
        )



        if GROUP_ID:
            if thread_id:
                await bot.send_message(GROUP_ID, text, message_thread_id=thread_id)
            else:
                await bot.send_message(GROUP_ID, text)
    except Exception as e:
        print("Error posting assignment:", e)

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

# --- EDIT-IN-PLACE: один «экран» на пользователя ---

async def render_screen(user_id: int, chat_id: int, text: str, *, reply_markup=None):
    lock = _USER_LOCKS.setdefault(user_id, asyncio.Lock())
    async with lock:
        st = STATE.setdefault(user_id, {"flow": None, "role": None, "deadline": None, "msg_id": None, "chat_id": None})

        old_chat_id = st.get("chat_id")
        old_msg_id = st.get("msg_id")
        if old_msg_id and old_chat_id and old_chat_id != chat_id:
            try:
                await bot.delete_message(old_chat_id, old_msg_id)
            except Exception:
                pass
            st["msg_id"] = None

        msg_id = st.get("msg_id")
        if msg_id:
            try:
                await bot.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=msg_id,
                    reply_markup=reply_markup
                )
                st["chat_id"] = chat_id
                return
            except Exception as e:
                print("Edit failed, fallback to send:", e)
                st["msg_id"] = None

        sent = await bot.send_message(chat_id, text, reply_markup=reply_markup)
        st["msg_id"] = sent.message_id
        st["chat_id"] = chat_id

# ============ HANDLERS ============

@dp.message(Command("start"))
async def cmd_start(m: Message):
    now = monotonic()
    last = _LAST_START_AT.get(m.from_user.id, 0.0)
    if now - last < 1.5:
        return
    _LAST_START_AT[m.from_user.id] = now

    STATE[m.from_user.id] = {"flow": None, "role": None, "deadline": None, "msg_id": None, "chat_id": None}
    await render_screen(
        m.from_user.id, m.chat.id,
        "Присоединяйся к команде Tales of Kitsune — магия начинается с первой главы.\n\nВыбери раздел:",
        reply_markup=main_menu()
    )

@dp.message(Command("cancel"))
async def cancel(m: Message):
    STATE.pop(m.from_user.id, None)
    await m.answer("Окей. Режим подачи заявки отключён. Набери /start, чтобы начать заново.")

@dp.message(Command("topicid"))
async def topic_id(m: Message):
    if getattr(m, "is_topic_message", False):
        await m.answer(f"ID этой темы: {m.message_thread_id}")
    else:
        await m.answer("Отправьте команду /topicid внутри нужной темы (вкладки) группы.")

@dp.callback_query(F.data == "about")
async def on_about(c: CallbackQuery):
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Секунду…")
        return
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
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Секунду…")
        return
    st = STATE.setdefault(c.from_user.id, {})
    st.update({"flow": "vacancies", "role": None})
    await render_screen(c.from_user.id, c.message.chat.id, "Выбери специальность:", reply_markup=vacancies_keyboard())
    await c.answer()

@dp.callback_query(F.data == "apply")
async def on_apply(c: CallbackQuery):
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Секунду…")
        return
    st = STATE.setdefault(c.from_user.id, {})
    st.update({"flow": "apply", "role": None})
    await render_screen(c.from_user.id, c.message.chat.id, "Выбери специальность для подачи заявки:", reply_markup=apply_roles_keyboard())
    await c.answer()

@dp.callback_query(F.data == "back:menu")
async def on_back_menu(c: CallbackQuery):
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Секунду…")
        return
    st = STATE.setdefault(c.from_user.id, {})
    st.update({"flow": None, "role": None})
    await render_screen(c.from_user.id, c.message.chat.id, "Главное меню:", reply_markup=main_menu())
    await c.answer()

@dp.callback_query(F.data == "back:vacancies")
async def on_back_vacancies(c: CallbackQuery):
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Секунду…")
        return
    st = STATE.setdefault(c.from_user.id, {})
    st.update({"flow": "vacancies", "role": None})
    await render_screen(c.from_user.id, c.message.chat.id, "Специальности:", reply_markup=vacancies_keyboard())
    await c.answer()

@dp.callback_query(F.data == "back:applyroles")
async def on_back_applyroles(c: CallbackQuery):
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Секунду…")
        return
    st = STATE.setdefault(c.from_user.id, {})
    st.update({"flow": "apply", "role": None})
    await render_screen(c.from_user.id, c.message.chat.id, "Выбери специальность:", reply_markup=apply_roles_keyboard())
    await c.answer()

# ——— Вакансии: показать описание роли
@dp.callback_query(F.data.startswith("v:"))
async def vacancy_show(c: CallbackQuery):
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Секунду…")
        return
    key = c.data.split(":", 1)[1]
    st = STATE.setdefault(c.from_user.id, {})
    st["role"] = key
    # запоминаем как «последнюю роль»
    USER_LAST_ROLE[c.from_user.id] = key

    await render_screen(
        c.from_user.id, c.message.chat.id,
        role_desc_block(key),
        reply_markup=back_and_apply_small()
    )
    await c.answer()

# ——— Подача: роль + методичка + старт теста
@dp.callback_query(F.data.startswith("a:"))
async def apply_role_intro(c: CallbackQuery):
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Секунду…")
        return
    key = c.data.split(":", 1)[1]
    st = STATE.setdefault(c.from_user.id, {})
    st["role"] = key
    USER_LAST_ROLE[c.from_user.id] = key

    await render_screen(
        c.from_user.id, c.message.chat.id,
        apply_info_block(key),
        reply_markup=start_test_keyboard(key)
    )
    await c.answer()

# ——— Старт теста
@dp.callback_query(F.data.startswith("starttest:"))
async def start_test(c: CallbackQuery):
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Секунду…")
        return
    key = c.data.split(":", 1)[1]
    info = ROLE_INFO.get(key, {})
    folder = info.get("test_folder", "—")
    st = STATE.setdefault(c.from_user.id, {})
    st["deadline"] = datetime.now(timezone.utc)
    # на всякий — тоже запоминаем роль
    st["role"] = key
    USER_LAST_ROLE[c.from_user.id] = key

    await render_screen(
        c.from_user.id, c.message.chat.id,
        "Заполните анкету по форме ниже (отправьте одним сообщением — пункты можно перечислить):\n"
        "Имя / Ник\nОпыт (если есть)\nЧасовой пояс\nГотовность по времени\n\n"
        f"Папка с тестовым заданием: {folder}\n"
        f"Дедлайн: {TEST_DEADLINE_DAYS} дня.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« Назад", callback_data="back:applyroles")]
        ])
    )

    asyncio.create_task(schedule_deadline_notify(c.from_user.id, key, st["deadline"]))
    await c.answer("Тест выдан")

# ——— Админское PM из группы: /pm <user_id> [текст/медиа], без «светящейся» команды
@dp.message(Command("pm"))
async def admin_pm(m: Message, command: CommandObject):
    # только из групп/супергрупп и только от админов
    if m.chat.type not in ("supergroup", "group"):
        return
    if ADMIN_IDS and m.from_user.id not in ADMIN_IDS:
        return

    # /pm <user_id> [текст...]
    args = (command.args or "").split(maxsplit=1)
    if not args:
        await m.reply("Использование: /pm <user_id> [текст или медиа]")
        return

    try:
        user_id = int(args[0])
    except ValueError:
        await m.reply("Неверный формат. Пример: /pm 12345678 Привет или фото.")
        return

    has_media = any([m.photo, m.document, m.video, m.animation, m.voice, m.audio, m.sticker])

    try:
        if has_media:
            # 1) если есть подпись — чистим из неё "/pm <id>" в начале
            raw_caption = m.caption or ""
            clean_caption = re.sub(r"(?i)^/pm\s+\d+\s*", "", raw_caption).strip()

            # 2) если подписи не было, берём текстовую часть после user_id из команды
            if not clean_caption and len(args) > 1:
                clean_caption = args[1].strip()

            caption = "Сообщение от куратора:"
            if clean_caption:
                caption += "\n\n" + clean_caption

            if m.photo:
                await bot.send_photo(user_id, m.photo[-1].file_id, caption=caption)
            elif m.document:
                await bot.send_document(user_id, m.document.file_id, caption=caption)
            elif m.video:
                await bot.send_video(user_id, m.video.file_id, caption=caption)
            elif m.animation:
                await bot.send_animation(user_id, m.animation.file_id, caption=caption)
            elif m.audio:
                await bot.send_audio(user_id, m.audio.file_id, caption=caption)
            elif m.voice:
                await bot.send_voice(user_id, m.voice.file_id, caption=caption)
            elif m.sticker:
                # у стикера подписи нет
                await bot.send_sticker(user_id, m.sticker.file_id)
                if clean_caption or len(args) > 1:
                    await bot.send_message(user_id, caption)
            else:
                # на всякий случай
                await bot.send_message(user_id, caption)
        else:
            # обычный текст без медиа
            text_body = args[1].strip() if len(args) > 1 else ""
            msg = "Сообщение от куратора:"
            if text_body:
                msg += "\n\n" + text_body
            await bot.send_message(user_id, msg)

        # ничего не редактируем/не удаляем в админском чате — оставляем исходное сообщение
        await m.reply("✅ Сообщение отправлено пользователю.")
    except Exception as e:
        await m.reply(f"⚠️ Не удалось отправить: {e}")


# ——— Приём контента ОТ ПОЛЬЗОВАТЕЛЕЙ и пересылка в админскую тему ВСЕГДА
@dp.message()
async def collect_and_forward(m: Message):
    # в приватах ловим всё, кроме команд
    if m.chat.type != "private":
        return
    if m.text and m.text.startswith("/"):
        return

    st = STATE.get(m.from_user.id) or {}
    role_key = st.get("role") or USER_LAST_ROLE.get(m.from_user.id)
    role_title_text = role_title(role_key) if role_key else "—"

    # куда слать: в тему по роли, если есть; иначе в общий поток группы
    thread_id = ROLE_TOPICS.get(role_key) if role_key else None

    username = f"@{m.from_user.username}" if m.from_user.username else "—"
    header = (
        f"📥 Сообщение от {username} (id {m.from_user.id}) | Роль: {role_title_text}"
    )

    try:
        if GROUP_ID:
            if thread_id:
                await bot.send_message(GROUP_ID, header, message_thread_id=thread_id)
                await m.copy_to(GROUP_ID, message_thread_id=thread_id)
            else:
                await bot.send_message(GROUP_ID, header)
                await m.copy_to(GROUP_ID)

        # Пользователю — короткий автоответ, если хочешь, можно убрать:
        # await bot.send_message(m.chat.id, "Принято. Сообщение отправлено кураторам.")
    except Exception as e:
        print("Forward error:", e)
        # мягкий фоллбек без разглашения технической чуши пользователю
        try:
            await bot.send_message(m.chat.id, "Не получилось доставить сообщение кураторам. Попробуйте ещё раз позже.")
        except Exception:
            pass

# ============ FAKE HTTP FOR RENDER ============

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
