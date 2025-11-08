import os
import re
import asyncio
import html as pyhtml
from datetime import datetime, timedelta, timezone
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
from time import monotonic

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery, BotCommand,
    BotCommandScopeAllPrivateChats, BotCommandScopeAllChatAdministrators,
    InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio
)

# ==== HTML parse_mode: совместимость с разными aiogram ====
try:
    from aiogram.client.default import DefaultBotProperties  # v3.x
except Exception:  # noqa
    DefaultBotProperties = None

try:
    from aiogram.enums import ParseMode  # v3.x
except Exception:  # noqa
    from aiogram.types import ParseMode  # type: ignore

# ============ CONFIG ============

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

GROUP_ID = int(os.getenv("GROUP_ID", "0"))
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

EXTRA_GUIDE_URL = (
    "https://docs.google.com/document/d/1kfJ18MnWzpWa6n4oSTYEn0tisz3VNC0a/"
    "edit?usp=sharing&ouid=104155753409319228630&rtpof=true&sd=true"
)

ROLE_INFO = {
    "translator": {
        "title": "Переводчик",
        "desc": """
Существо редкое, почти мистическое.
Он изучает древние письмена, полные странных знаков и смыслов, сокрытых от простых смертных, и извлекает из них истории, понятные человеческому сознанию. 
Живёт на кофе, словарях и милости духов-кицунэ, что шепчут ему подсказки между строчек.

<b>Доступные языки:</b>
• Английский
• Испанский
• Корейский
• Индонезийский

<i>Современные чары машинного перевода и нейросетей можно звать на помощь, но не позволяйте им творить вместо вас.</i>
 """,
        "guide": "https://docs.google.com/document/d/1fKu8n-1nLpgLHV2-XNPM-HeBaCFlpX23lbAdXDllB-A/edit?usp=sharing",
        "test_folder": "https://drive.google.com/drive/folders/1jferUktlsctxsRWYmHiqU7gHr6JE6eyJ?usp=sharing"
    },
    "editor": {
        "title": "Редактор",
        "desc": """
Хранитель чистоты слова и проводник смысла.
Он вычищает следы человеческой небрежности, полирует текст до блеска и собирает рассыпавшиеся мысли в чёткий узор фраз.
 """,
        "guide": "https://docs.google.com/document/d/1yBjmbplGJ2owy-0a9IrRO9UyskW9ljLAqZctCoOJal0/edit?usp=sharing",
        "test_folder": "https://drive.google.com/drive/folders/1rsCbmU3mhJQClZkW8VyToHZkYAFIxIlB?usp=sharing"
    },
    "cleaner": {
        "title": "Клинер/Ретушёр",
        "desc": """
Тихий мученик с ластиком в руке, стирающий чужие буквы с древних страниц. Он возвращает рисунку первозданную чистоту, жертвуя зрением, осанкой и, порой, остатками душевного равновесия.
 """,
        "guide": "https://docs.google.com/document/d/1Ncg8KpvUa6KferVPdP0XLJ3DILegs1a2d3DhMJTarPA/edit?usp=sharing",
        "test_folder": "https://drive.google.com/drive/folders/11q4UZeid9ewMze6M9fVMNABdPxeWiZ64?usp=sharing"
    },
    "typesetter": {
        "title": "Тайпер",
        "desc": """
Заклинатель текста, что вплетает слова в очищенные страницы.
Он подбирает шрифты, ловит ритм строк и старается приручить капризные баблы…
 """,
        "guide": "https://docs.google.com/document/d/1Xd7Nн0UPS9372f5otgyv8FfО0hGfyNLP/edit?usp=sharing&ouid=104155753409319228630&rtpof=true&sd=true",
        "test_folder": "https://drive.google.com/drive/folders/1VVrAiriLncotiKkII5_xbAsIyystDtXq?usp=sharing"
    },
    "gluer": {
        "title": "Склейщик",
        "desc": """
Незаметный мастер теней, собирающий рассыпанное полотно страниц в единое целое.
Он знает, где прячутся лучшие сканы, какие святилища не искажают качество, и на сколько пикселей нужно сдвинуть слой, чтобы стыки исчезли, словно их никогда и не было.
 """,
        "guide": "https://docs.google.com/document/d/1d-JOzkwз2MyQ1K-8LLeзIRka6ceг7mxw6ePnrUvMkho/edit?usp=sharing",
        "test_folder": "https://drive.google.com/drive/folders/1Ape7qsiKkm6uhFeKcYvsh1XOuYAa93f8?usp=sharing"
    },
    "curator": {
        "title": "Куратор",
        "desc": """
Мозг команды и её личный громоотвод.
Он всегда знает, кто где увяз: у кого полыхают дедлайны, у кого застрял перевод на «я сделаю вечером», а у кого внезапно исчез интернет или совесть.
 """,
        "guide": "https://docs.google.com/document/d/1TVFM-oX-e7mwlxEnSI0hKSIzezruDHj1EHCuVLYK1KY/edit?usp=sharing",
    },
    "beta": {
        "title": "Бета-ридер",
        "desc": """
Читает главы до релиза, высматривая каждую шероховатость, пока текст ещё не покинул стены лисьего логова.
 """,
        "guide": "https://docs.google.com/document/d/1naGul_KQhkV4bMUBaGзHR5KMwNK90j-gNgr5jrIjxWA/edit?usp=sharing",
        "test_folder": "https://drive.google.com/drive/folders/1jHYnfP7HGuJZFaM_VOJ1UWe-VLrTvLdw?usp=sharing"
    },
    "typecheck": {
        "title": "Тайп-чекер",
        "desc": """
Хранитель порядка в мире шрифтов и баблов.
Он зорко следит за выравниванием, отступами, переносами и толщиной обводки, чтобы каждая страница дышала гармонией и аккуратностью.
 """,
        "guide": "https://docs.google.com/document/d/1--JVkuwGl1u5UUpGKnzaETmIg6EJJX2u/edit?usp=sharing&ouid=104155753409319228630&rtpof=true&sd=true",
        "test_folder": "https://drive.google.com/drive/folders/1O1Dw5yWrsR27ZXVbQDMP0q4GDBV5F-Un?usp=sharing"
    },
}

TEST_DEADLINE_DAYS = int(os.getenv("TEST_DEADLINE_DAYS", "3"))
PORT = int(os.getenv("PORT", "10000"))

# ============ BOT STATE / ACCESS CONTROL ============

# STATE[user_id] = { flow, role, deadline, msg_id, chat_id, active }
STATE: dict[int, dict] = {}
USER_LAST_ROLE: dict[int, str] = {}

# Бан-лист
BANNED_IDS = {int(x) for x in os.getenv("BANNED_IDS", "").split(",") if x.strip().isdigit()}

_LAST_START_AT: dict[int, float] = {}
_LAST_CB_KEY_AT: dict[tuple[int, str], float] = {}
_CB_DEBOUNCE_SEC = 2.5
_USER_LOCKS: dict[int, asyncio.Lock] = {}

def is_admin(user_id: int) -> bool:
    return not ADMIN_IDS or user_id in ADMIN_IDS

# ============ BOT CORE ============

if DefaultBotProperties:
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
else:
    bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)

dp = Dispatcher()

# ============ SMALL UTILITIES ============

async def send_plain(chat_id: int, text: str):
    await bot.send_message(chat_id, text, parse_mode=None, disable_web_page_preview=True)

def esc(s: str) -> str:
    return pyhtml.escape(s or "")

def header_line(username: str | None, uid: int, role_text: str) -> str:
    uname = f"@{username}" if username else "—"
    return f"📥 Сообщение от {uname} (id {uid}) | Роль: {role_text}"

# ============ MEDIA GROUP AGGREGATION ============

# ключ: (from_id, media_group_id)
PENDING_ALBUMS: dict[tuple[int, str], dict] = {}

ALBUM_COLLECT_SEC = 1.2  # пауза, чтобы собрать все части альбома

def to_input_media(m: Message):
    cap = m.caption or ""
    if m.photo:
        return InputMediaPhoto(media=m.photo[-1].file_id, caption=cap or None, parse_mode=None)
    if m.video:
        return InputMediaVideo(media=m.video.file_id, caption=cap or None, parse_mode=None)
    if m.document:
        return InputMediaDocument(media=m.document.file_id, caption=cap or None, parse_mode=None)
    if m.audio:
        return InputMediaAudio(media=m.audio.file_id, caption=cap or None, parse_mode=None)
    # анимации/стикеры/voice в альбом не идут
    return None

async def _flush_album(key: tuple[int, str]):
    pack = PENDING_ALBUMS.get(key)
    if not pack:
        return
    await asyncio.sleep(ALBUM_COLLECT_SEC)
    pack = PENDING_ALBUMS.pop(key, None)
    if not pack:
        return

    chat_id = pack["chat_id"]
    thread_id = pack["thread_id"]
    header = pack["header"]
    media_list = pack["media"]

    delivered = False
    try:
        if GROUP_ID:
            await bot.send_message(chat_id, header, message_thread_id=thread_id)
            # Telegram разрешает подпись только у одного элемента — оставим у первого
            # У остальных затираем caption, чтобы не упасть на валидации
            first = True
            cleaned = []
            for item in media_list:
                if first:
                    cleaned.append(item)
                    first = False
                else:
                    cls = type(item)
                    cleaned.append(cls(media=item.media))  # без подписи
            await bot.send_media_group(chat_id, cleaned, message_thread_id=thread_id)
            delivered = True
    except Exception as e:
        print("Album forward error:", e)

    try:
        if delivered:
            await send_plain(pack["user_chat"], "Сообщение доставлено кураторам.")
        else:
            await send_plain(pack["user_chat"], "Не получилось доставить сообщение кураторам. Попробуйте ещё раз позже.")
    except Exception:
        pass

# ============ KEYBOARDS ============

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="જ⁀➴ О команде", callback_data="about")],
        [InlineKeyboardButton(text="Подать заявку <┈╯", callback_data="apply")]
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
    return (
        f"<b>{title}</b>\n{desc}\n\n"
        f"<b>Правила:</b> {guide}\n"
        f"<b>Методичка:</b> {EXTRA_GUIDE_URL}"
    )

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
            "⏳ <b>Выдано тестовое задание</b>\n"
            f"Роль: <b>{title}</b>\n"
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

# --- один «экран» на пользователя ---
async def render_screen(
    user_id: int,
    chat_id: int,
    text: str,
    *,
    reply_markup=None,
    parse_mode: str | None = ParseMode.HTML
):
    lock = _USER_LOCKS.setdefault(user_id, asyncio.Lock())
    async with lock:
        st = STATE.setdefault(user_id, {"flow": None, "role": None, "deadline": None,
                                        "msg_id": None, "chat_id": None, "active": False})

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
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                st["chat_id"] = chat_id
                return
            except Exception as e:
                print("Edit failed, fallback to send:", e)
                st["msg_id"] = None

        sent = await bot.send_message(
            chat_id,
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
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

    st = STATE.setdefault(m.from_user.id, {"flow": None, "role": None, "deadline": None,
                                            "msg_id": None, "chat_id": None, "active": False})
    st.update({"flow": None, "role": None, "active": True})
    await render_screen(
        m.from_user.id, m.chat.id,
        """ㅤㅤㅤ🐾『𝐓𝐚𝐥𝐞𝐬 𝐨𝐟 𝐊𝐢𝐭𝐬𝐮𝐧𝐞』 🐾
        ㅤУзнай легенды логова иㅤ
        правила его обитателей, аㅤ
        затем оставь свою заявку,ㅤ
        если готов присоединить-
        ㅤся к стае.༄˖°.🍂.ೃ࿔*:･ㅤ""",
        reply_markup=main_menu()
    )

@dp.message(Command("cancel"))
async def cancel(m: Message):
    st = STATE.setdefault(m.from_user.id, {"flow": None, "role": None, "deadline": None,
                                            "msg_id": None, "chat_id": None, "active": False})
    st.update({"flow": None, "role": None, "active": False})
    await send_plain(
        m.chat.id,
        "Ты больше не желаешь быть частью стаи? Окей, мы закрыли твою заявку и кураторы больше не увидят твои сообщения. "
        "Чтобы снова иметь возможность подать заявку и общаться в чате, используй /start"
    )

@dp.message(Command("topicid"))
async def topic_id(m: Message):
    if getattr(m, "is_topic_message", False):
        await send_plain(m.chat.id, f"ID этой темы: {m.message_thread_id}")
    else:
        await send_plain(m.chat.id, "Отправьте команду /topicid внутри нужной темы (вкладки) группы.")

# ---- Админ-команды: бан / разбан ----

@dp.message(Command("ban"))
async def admin_ban(m: Message, command: CommandObject):
    if m.chat.type not in ("supergroup", "group"):
        return
    if not is_admin(m.from_user.id):
        return

    args = (command.args or "").split()
    if not args:
        await send_plain(m.chat.id, "Использование: /ban ID_пользователя\nНапример: /ban 123456789")
        return
    try:
        user_id = int(args[0])
    except ValueError:
        await send_plain(m.chat.id, "Айди должен быть числом: /ban 123456789")
        return

    BANNED_IDS.add(user_id)
    st = STATE.setdefault(user_id, {"flow": None, "role": None, "deadline": None,
                                     "msg_id": None, "chat_id": None, "active": False})
    st["active"] = False
    try:
        await send_plain(
            user_id,
            "Ты слишком болтлив, молодой лис. Нам пришлось отобрать у тебя возможность общаться и отправлять анкеты."
        )
    except Exception:
        pass
    await send_plain(m.chat.id, f"✅ Забанен id {user_id}. Пересылка его сообщений отключена.")

@dp.message(Command("unban"))
async def admin_unban(m: Message, command: CommandObject):
    if m.chat.type not in ("supergroup", "group"):
        return
    if not is_admin(m.from_user.id):
        return

    args = (command.args or "").split()
    if not args:
        await send_plain(m.chat.id, "Использование: /unban ID_пользователя\nНапример: /unban 123456789")
        return
    try:
        user_id = int(args[0])
    except ValueError:
        await send_plain(m.chat.id, "Айди должен быть числом: /unban 123456789")
        return

    if user_id in BANNED_IDS:
        BANNED_IDS.discard(user_id)
        try:
            await send_plain(
                user_id,
                "Связь со стаей восстановлена. Набери /start, чтобы снова подать заявку и общаться."
            )
        except Exception:
            pass
        await send_plain(m.chat.id, f"✅ Разбанен id {user_id}. Может снова общаться после /start.")
    else:
        await send_plain(m.chat.id, "Этого лиса и так никто не держал в клетке. Он не в бане.")

# ---- Кнопки и экраны ----

@dp.callback_query(F.data == "about")
async def on_about(c: CallbackQuery):
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Притормози, лисёнок...")
        return

    about_html = (
        "<b>Tales of Kitsune</b> — команда, которая переводит манхвы с любовью к оригиналу и уважением к читателю.\n\n"
        "<b>Работаем за спасибо.</b>\n"
        "Наш проект некоммерческий: здесь нет зарплат, премий и прочих земных наград.\n"
        "Мы трудимся ради удовольствия творить и ради тех, кто хочет читать эти истории свободно — так, как их задумали авторы.\n\n"
        "<b>Берём кандидатов без опыта.</b>\n"
        "Не умеешь чистить, вставлять текст или спорить со шрифтами — научим.\n"
        "Умеешь — тем лучше, сбережём немного нервов и времени для сна.\n"
        "Главное — желание делать хорошо. Остальное приходит с практикой, терпением и парой ночей в компании таинственного файла «финал_3_точно_последний.psd».\n\n"
        "<b>Требования:</b>\n"
        "• Пара свободных часов в неделю\n"
        "• Ответственность и уважение к срокам\n"
        "• Возраст от 16 лет\n"
        "• Прохождение тестового задания"
    )

    await render_screen(
        c.from_user.id,
        c.message.chat.id,
        about_html,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« Назад", callback_data="back:menu"),
             InlineKeyboardButton(text="Подать заявку", callback_data="apply")]
        ])
    )
    await c.answer()

@dp.callback_query(F.data == "apply")
async def on_apply(c: CallbackQuery):
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Притормози, лисёнок...")
        return
    st = STATE.setdefault(c.from_user.id, {"flow": None, "role": None, "deadline": None,
                                            "msg_id": None, "chat_id": None, "active": False})
    st.update({"flow": "apply", "role": None})
    await render_screen(
        c.from_user.id,
        c.message.chat.id,
        """        ㅤ        Выбери направление,ㅤ
        ㅤв котором раскроетсяㅤ
        ㅤтвой талант под пред-ㅤ
        ㅤводительством кицунэ.ㅤ""",
        reply_markup=apply_roles_keyboard()
    )
    await c.answer()

@dp.callback_query(F.data == "back:menu")
async def on_back_menu(c: CallbackQuery):
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Притормози, лисёнок...")
        return
    st = STATE.setdefault(c.from_user.id, {"flow": None, "role": None, "deadline": None,
                                            "msg_id": None, "chat_id": None, "active": False})
    st.update({"flow": None, "role": None})
    await render_screen(
        c.from_user.id, c.message.chat.id,
        """ㅤㅤㅤ🐾『𝐓𝐚𝐥𝐞𝐬 𝐨𝐟 𝐊𝐢𝐭𝐬𝐮𝐧𝐞』 🐾
        ㅤУзнай легенды логова иㅤ
        правила его обитателей, аㅤ
        затем оставь свою заявку,ㅤ
        если готов присоединить-
        ㅤся к стае.༄˖°.🍂.ೃ࿔*:･ㅤ""",
        reply_markup=main_menu()
    )
    await c.answer()

@dp.callback_query(F.data == "back:applyroles")
async def on_back_applyroles(c: CallbackQuery):
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Притормози, лисёнок...")
        return
    st = STATE.setdefault(c.from_user.id, {"flow": None, "role": None, "deadline": None,
                                            "msg_id": None, "chat_id": None, "active": False})
    st.update({"flow": "apply", "role": None})
    await render_screen(
        c.from_user.id,
        c.message.chat.id,
        """        ㅤ        Выбери направление,ㅤ
        ㅤв котором раскроетсяㅤ
        ㅤтвой талант под пред-ㅤ
        ㅤводительством кицунэ.ㅤ""",
        reply_markup=apply_roles_keyboard()
    )
    await c.answer()

@dp.callback_query(F.data == "vacancies"))
async def on_vacancies(c: CallbackQuery):
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Притормози, лисёнок...")
        return
    st = STATE.setdefault(c.from_user.id, {"flow": None, "role": None, "deadline": None,
                                            "msg_id": None, "chat_id": None, "active": False})
    st.update({"flow": "vacancies", "role": None})
    await render_screen(c.from_user.id, c.message.chat.id, "Выбери специальность:", reply_markup=vacancies_keyboard())
    await c.answer()

@dp.callback_query(F.data.startswith("v:"))
async def vacancy_show(c: CallbackQuery):
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Притормози, лисёнок...")
        return
    key = c.data.split(":", 1)[1]
    st = STATE.setdefault(c.from_user.id, {"flow": None, "role": None, "deadline": None,
                                            "msg_id": None, "chat_id": None, "active": False})
    st["role"] = key
    USER_LAST_ROLE[c.from_user.id] = key

    await render_screen(
        c.from_user.id, c.message.chat.id,
        role_desc_block(key),
        reply_markup=back_and_apply_small()
    )
    await c.answer()

@dp.callback_query(F.data.startswith("a:"))
async def apply_role_intro(c: CallbackQuery):
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Притормози, лисёнок...")
        return
    key = c.data.split(":", 1)[1]
    st = STATE.setdefault(c.from_user.id, {"flow": None, "role": None, "deadline": None,
                                            "msg_id": None, "chat_id": None, "active": False})
    st["role"] = key
    USER_LAST_ROLE[c.from_user.id] = key

    await render_screen(
        c.from_user.id, c.message.chat.id,
        apply_info_block(key),
        reply_markup=start_test_keyboard(key)
    )
    await c.answer()

@dp.callback_query(F.data.startswith("starttest:"))
async def start_test(c: CallbackQuery):
    if _cb_too_fast_for_key(c.from_user.id, c.data):
        await c.answer("Притормози, лисёнок...")
        return

    key = c.data.split(":", 1)[1]
    info = ROLE_INFO.get(key, {})
    folder = info.get("test_folder", "")
    guide = info.get("guide", "")

    st = STATE.setdefault(c.from_user.id, {"flow": None, "role": None, "deadline": None,
                                            "msg_id": None, "chat_id": None, "active": False})
    st["deadline"] = datetime.now(timezone.utc)
    st["role"] = key
    USER_LAST_ROLE[c.from_user.id] = key

    title = role_title(key)

    lines = [
        f"<b>{title}</b>",
        "Заполните анкету по форме ниже и прикрепите к ней тестовый файл "
        "(тестовое задание для кураторов отсутствует):",
        "1. Имя (при желании указать).",
        "2. Ник (как к вам обращаться).",
        "3. Наличие/отсутствие опыта (при желании указать). При подаче заявки на куратора указывать обязательно.",
        "4. Количество свободного времени в неделю.",
        "5. Дополнительные полезные навыки/знания (работа в приложениях, с нейросетями, знание EXCEL/Google docs и прочее).",
        "6*. Укажите язык, с которого был выполнен перевод (пункт для переводчиков).",
        "",
    ]

    if folder:
        lines.append(f"<b>Папка с тестовым заданием:</b> {folder}")
    else:
        lines.append("<b>Папка с тестовым заданием:</b> отсутствует для этой роли.")

    if guide:
        lines.append(f"<b>Правила выполнения задания:</b> {guide}")

    lines.append(f"<b>Методичка:</b> {EXTRA_GUIDE_URL}")
    lines.append(f"<b>Дедлайн:</b> {TEST_DEADLINE_DAYS} дня.")

    text = "\n".join(lines)

    await render_screen(
        c.from_user.id, c.message.chat.id,
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« Назад", callback_data="back:applyroles")]
        ])
    )

    asyncio.create_task(schedule_deadline_notify(c.from_user.id, key, st["deadline"]))
    await c.answer("Тест выдан")

# ---- /pm: по ID, по @username и ответом на сообщение ----

async def _resolve_pm_target(m: Message, command: CommandObject):
    # 1) реплай на форвард из пользователя
    if m.reply_to_message and m.reply_to_message.forward_origin:
        try:
            uid = m.reply_to_message.forward_origin.sender_user.id  # Telegram API 6.9+
            return uid
        except Exception:
            pass
    # 2) явный ID в аргументах
    args = (command.args or "").split(maxsplit=1)
    if args:
        # @username?
        if args[0].startswith("@"):
            try:
                user = await bot.get_chat(args[0])
                return user.id
            except Exception:
                return None
        # просто число
        if args[0].isdigit():
            return int(args[0])
    return None

@dp.message(Command("pm"))
async def admin_pm(m: Message, command: CommandObject):
    if m.chat.type not in ("supergroup", "group"):
        return
    if not is_admin(m.from_user.id):
        return

    user_id = await _resolve_pm_target(m, command)
    if not user_id:
        await send_plain(m.chat.id, "Использование: ответьте на сообщение кандидата ИЛИ /pm ID [текст] ИЛИ /pm @username [текст]")
        return

    # отделяем текст
    args = (command.args or "").split(maxsplit=1)
    text_body = ""
    if args:
        if args[0].startswith("@") or args[0].isdigit():
            if len(args) > 1:
                text_body = args[1].strip()
        else:
            text_body = (command.args or "").strip()

    has_media = any([m.photo, m.document, m.video, m.animation, m.voice, m.audio, m.sticker])

    try:
        if has_media:
            caption = "Ответ куратора:"
            if text_body:
                caption += "\n\n" + text_body
            if m.photo:
                await bot.send_photo(user_id, m.photo[-1].file_id, caption=caption, parse_mode=None)
            elif m.document:
                await bot.send_document(user_id, m.document.file_id, caption=caption, parse_mode=None)
            elif m.video:
                await bot.send_video(user_id, m.video.file_id, caption=caption, parse_mode=None)
            elif m.animation:
                await bot.send_animation(user_id, m.animation.file_id, caption=caption, parse_mode=None)
            elif m.audio:
                await bot.send_audio(user_id, m.audio.file_id, caption=caption, parse_mode=None)
            elif m.voice:
                await bot.send_voice(user_id, m.voice.file_id, caption=caption)
            elif m.sticker:
                await bot.send_sticker(user_id, m.sticker.file_id)
                if text_body:
                    await send_plain(user_id, caption)
        else:
            msg = "Ответ куратора:"
            if text_body:
                msg += "\n\n" + text_body
            await send_plain(user_id, msg)

        await send_plain(m.chat.id, "✅ Сообщение отправлено пользователю.")
    except Exception as e:
        await send_plain(m.chat.id, f"⚠️ Не удалось отправить: {e}")

# ---- ЛС от юзеров: сбор и пересылка ----

@dp.message()
async def collect_and_forward(m: Message):
    if m.chat.type != "private":
        return
    if m.text and m.text.startswith("/"):
        return
    if m.from_user.id in BANNED_IDS:
        return

    st = STATE.get(m.from_user.id) or {}
    if not st.get("active", False):
        return

    role_key = st.get("role") or USER_LAST_ROLE.get(m.from_user.id)
    role_title_text = role_title(role_key) if role_key else "—"
    thread_id = ROLE_TOPICS.get(role_key) if role_key else None

    uname = m.from_user.username
    header = header_line(uname, m.from_user.id, role_title_text)

    delivered = False

    # 1) media group: накапливаем и шлём одним батчем
    if m.media_group_id:
        media = to_input_media(m)
        if media is None:
            # неподдерживаемый в альбоме тип — просто копируем отдельно
            try:
                if GROUP_ID:
                    await bot.send_message(GROUP_ID, header, message_thread_id=thread_id)
                    await m.copy_to(GROUP_ID, message_thread_id=thread_id)
                    delivered = True
            except Exception as e:
                print("Forward error (unsupported album type):", e)
        else:
            key = (m.from_user.id, m.media_group_id)
            pack = PENDING_ALBUMS.setdefault(key, {
                "media": [],
                "chat_id": GROUP_ID,
                "thread_id": thread_id,
                "header": header,
                "user_chat": m.chat.id,
            })
            pack["media"].append(media)
            # запуск таймера отправки
            if len(pack["media"]) == 1:
                asyncio.create_task(_flush_album(key))
            return  # подтверждение отправим из _flush_album

    # 2) чистый текст: единым сообщением
    elif m.text:
        body = header + "\nтекст:\n" + esc(m.text)
        try:
            if GROUP_ID:
                await bot.send_message(GROUP_ID, body, message_thread_id=thread_id, parse_mode=ParseMode.HTML)
                delivered = True
        except Exception as e:
            print("Forward text error:", e)

    # 3) одиночное медиа: заголовок + копия
    else:
        try:
            if GROUP_ID:
                await bot.send_message(GROUP_ID, header, message_thread_id=thread_id)
                await m.copy_to(GROUP_ID, message_thread_id=thread_id)
                delivered = True
        except Exception as e:
            print("Forward media error:", e)

    try:
        if delivered:
            await send_plain(m.chat.id, "Сообщение доставлено кураторам.")
        else:
            await send_plain(m.chat.id, "Не получилось доставить сообщение кураторам. Попробуйте ещё раз позже.")
    except Exception:
        pass

# ============ COMMAND SUGGESTIONS (slash menu) ============

async def setup_commands():
    # Пользовательские команды в ЛС
    user_cmds = [
        BotCommand(command="start", description="Начать работу и подать заявку"),
        BotCommand(command="cancel", description="Закрыть заявку и отключить пересылку"),
        BotCommand(command="help", description="Что умеет бот (для кандидата)"),
    ]
    await bot.set_my_commands(user_cmds, scope=BotCommandScopeAllPrivateChats())

    # Админские команды (в группах, где есть админы)
    admin_cmds = [
        BotCommand(command="help", description="Краткая справка по управлению"),
        BotCommand(command="pm", description="Написать пользователю: /pm ID | @username [текст] или ответом"),
        BotCommand(command="ban", description="Забанить пользователя: /ban ID"),
        BotCommand(command="unban", description="Разбанить пользователя: /unban ID"),
        BotCommand(command="topicid", description="Показать ID текущей темы"),
    ]
    await bot.set_my_commands(admin_cmds, scope=BotCommandScopeAllChatAdministrators())

# ======== HELP COMMANDS ========

@dp.message(Command("help"))
async def help_cmd(m: Message):
    if m.chat.type in ("supergroup", "group") and is_admin(m.from_user.id):
        text = (
            "Админ-команды:\n"
            "/pm ID | @username [текст] – отправить ЛС пользователю или ответом на его сообщение\n"
            "/ban ID – запретить писать боту и отключить пересылку\n"
            "/unban ID – снять запрет\n"
            "/topicid – показать ID темы для привязки вакансий\n"
            "\nПодсказка: Telegram сам добавляет @бот к командам в группах. Отключить это невозможно."
        )
        await send_plain(m.chat.id, text)
    else:
        text = (
            "Команды кандидата:\n"
            "/start – начать подачу заявки\n"
            "/cancel – закрыть заявку и отключить пересылку\n"
            "/help – эта справка"
        )
        await send_plain(m.chat.id, text)

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

    try:
        await setup_commands()
    except Exception as e:
        print("setup_commands failed:", e)

    Thread(target=start_http, daemon=True).start()
    print("Bot polling…")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
