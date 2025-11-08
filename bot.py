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
    Message, CallbackQuery, BotCommand,
    BotCommandScopeAllPrivateChats, BotCommandScopeAllChatAdministrators
)

# ==== HTML parse_mode: совместимость с разными aiogram ====
try:
    from aiogram.client.default import DefaultBotProperties  # v3.x
except Exception:  # noqa
    DefaultBotProperties = None

try:
    from aiogram.enums import ParseMode, ChatType  # v3.x
except Exception:  # noqa
    from aiogram.types import ParseMode  # type: ignore
    from aiogram.types import ChatType  # type: ignore

# Для альбомов
try:
    from aiogram.types import (
        InputMediaPhoto, InputMediaVideo, InputMediaDocument,
        InputMediaAudio, InputMediaAnimation
    )
except Exception:
    from aiogram.types import (
        InputMediaPhoto, InputMediaVideo, InputMediaDocument,
        InputMediaAudio
    )
    InputMediaAnimation = None  # type: ignore

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
    # ... (оставлено без изменений)
}

TEST_DEADLINE_DAYS = int(os.getenv("TEST_DEADLINE_DAYS", "3"))
PORT = int(os.getenv("PORT", "10000"))

# ============ BOT STATE / ACCESS CONTROL ============

STATE: dict[int, dict] = {}
USER_LAST_ROLE: dict[int, str] = {}
BANNED_IDS = {int(x) for x in os.getenv("BANNED_IDS", "").split(",") if x.strip().isdigit()}
_LAST_START_AT: dict[int, float] = {}
_LAST_CB_KEY_AT: dict[tuple[int, str], float] = {}
_CB_DEBOUNCE_SEC = 2.5
_USER_LOCKS: dict[int, asyncio.Lock] = {}

# Сообщение в группе -> целевой user_id для «свайп-ответа»
REPLY_MAP: dict[tuple[int, int], int] = {}

def is_admin(user_id: int) -> bool:
    return not ADMIN_IDS or user_id in ADMIN_IDS

# ============ NEW: MEDIA GROUP BUFFERING (кандидаты -> кураторы) ============

_MEDIA_BUFFERS: dict[str, list[Message]] = {}
_MEDIA_TASKS: dict[str, asyncio.Task] = {}
_ACKED_MEDIA_GROUPS: set[str] = set()

# ============ NEW: OUTGOING BUNDLE (админы -> кандидаты) ============

# ключ: (target_user_id, media_group_id) -> список сообщений админа
_OUT_BUFFERS: dict[tuple[int, str], list[Message]] = {}
_OUT_TASKS: dict[tuple[int, str], asyncio.Task] = {}

if DefaultBotProperties:
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
else:
    bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)

dp = Dispatcher()

# ============ SMALL UTILITIES ============

async def send_plain(chat_id: int, text: str):
    await bot.send_message(chat_id, text, parse_mode=None, disable_web_page_preview=True)

def remember_reply_target(msg: Message | None, user_id: int):
    if not msg:
        return
    try:
        REPLY_MAP[(msg.chat.id, msg.message_id)] = user_id
    except Exception:
        pass

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

def _compose_header(m: Message, role_key: str | None) -> tuple[str, str]:
    role_title_text = role_title(role_key) if role_key else "—"
    username = f"@{m.from_user.username}" if m.from_user.username else "—"
    hashtag_line = f"\n#{m.from_user.username}" if m.from_user.username else ""
    header = f"📥 Сообщение от {username} (id {m.from_user.id}) | Роль: {role_title_text}{hashtag_line}"
    return header, hashtag_line

def _extract_user_text(m: Message) -> str:
    return (m.text or m.caption or "").strip()

def _media_to_input(item: Message, caption: str | None = None):
    try:
        if item.photo:
            fid = item.photo[-1].file_id
            return InputMediaPhoto(media=fid, caption=caption), True
        if item.video:
            return InputMediaVideo(media=item.video.file_id, caption=caption), True
        if item.document:
            return InputMediaDocument(media=item.document.file_id, caption=caption), True
        if getattr(item, "audio", None):
            return InputMediaAudio(media=item.audio.file_id, caption=caption), True
        if getattr(item, "animation", None) and InputMediaAnimation:
            return InputMediaAnimation(media=item.animation.file_id, caption=caption), True
    except Exception:
        pass
    return None, False

# ============ KEYBOARDS (без изменений) ============

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

# ============ DEADLINE NOTIFY / render_screen (без изменений) ============

# ... schedule_deadline_notify и render_screen здесь без изменений ...

# ============ HANDLERS (start/cancel/topicid/ban/unban/about/apply/...) ============

# ... эти хендлеры оставлены как в твоем файле ...

# ============ ВСПОМОГАТЕЛЬНО: отправка связки в группу (кандидаты -> кураторы) ============

async def _send_bundled_to_group(header_text: str, user_text: str, thread_id: int | None, items: list[Message]):
    media: list = []
    unsupported: list[Message] = []

    for msg in items:
        im, ok = _media_to_input(msg, caption=None)
        if ok:
            media.append((msg, im))
        else:
            unsupported.append(msg)

    first_sent_message: Message | None = None

    if media:
        pack = media[:10]
        common_caption = header_text + (f"\n{user_text}" if user_text else "")
        inputs = []
        for j, (_m, im) in enumerate(pack):
            cls = type(im)
            kwargs = {"media": im.media}
            if j == 0:
                kwargs["caption"] = common_caption
                kwargs["parse_mode"] = None
            inputs.append(cls(**kwargs))  # type: ignore

        if GROUP_ID:
            if thread_id:
                sent = await bot.send_media_group(GROUP_ID, media=inputs, message_thread_id=thread_id)
            else:
                sent = await bot.send_media_group(GROUP_ID, media=inputs)
            first_sent_message = sent[0]

    if unsupported:
        for msg in unsupported:
            try:
                if GROUP_ID:
                    if msg.voice:
                        sent2 = await bot.send_voice(
                            GROUP_ID, msg.voice.file_id,
                            caption=None,
                            reply_to_message_id=first_sent_message.message_id if first_sent_message else None,
                            message_thread_id=thread_id if thread_id else None
                        )
                    elif msg.sticker:
                        sent2 = await bot.send_sticker(
                            GROUP_ID, msg.sticker.file_id,
                            reply_to_message_id=first_sent_message.message_id if first_sent_message else None,
                            message_thread_id=thread_id if thread_id else None
                        )
                    else:
                        sent2 = await msg.copy_to(
                            GROUP_ID,
                            reply_to_message_id=first_sent_message.message_id if first_sent_message else None,
                            message_thread_id=thread_id if thread_id else None
                        )
                    if not first_sent_message:
                        first_sent_message = sent2
            except Exception as e:
                print("Unsupported media forward error:", e)

    if not media and not unsupported:
        if GROUP_ID:
            if thread_id:
                first_sent_message = await bot.send_message(
                    GROUP_ID, f"{header_text}\n{user_text}".strip(),
                    message_thread_id=thread_id, parse_mode=None
                )
            else:
                first_sent_message = await bot.send_message(
                    GROUP_ID, f"{header_text}\n{user_text}".strip(), parse_mode=None
                )

    return first_sent_message

# ============ NEW: универсальная отправка бандла админа кандидату ============

async def _send_admin_bundle_to_user(user_id: int, text: str, items: list[Message]):
    """
    Отправляет админу-кандидату единым альбомом до 10 вложений.
    text — общий текст («Ответ куратора: …»). items — исходные сообщения админа.
    Возвращает True/False по факту успеха.
    """
    media: list = []
    unsupported: list[Message] = []

    for msg in items:
        im, ok = _media_to_input(msg, caption=None)
        if ok:
            media.append((msg, im))
        else:
            unsupported.append(msg)

    anchor: Message | None = None

    try:
        if media:
            pack = media[:10]
            caption = text.strip() if text else "Ответ куратора:"
            inputs = []
            for i, (_m, im) in enumerate(pack):
                cls = type(im)
                kwargs = {"media": im.media}
                if i == 0:
                    kwargs["caption"] = caption
                    kwargs["parse_mode"] = None
                inputs.append(cls(**kwargs))  # type: ignore
            sent = await bot.send_media_group(user_id, media=inputs)
            anchor = sent[0]

        if unsupported:
            for msg in unsupported:
                if msg.voice:
                    s2 = await bot.send_voice(user_id, msg.voice.file_id, caption=None,
                                              reply_to_message_id=anchor.message_id if anchor else None)
                elif msg.sticker:
                    s2 = await bot.send_sticker(user_id, msg.sticker.file_id,
                                                reply_to_message_id=anchor.message_id if anchor else None)
                else:
                    s2 = await msg.copy_to(user_id, reply_to_message_id=anchor.message_id if anchor else None)
                if not anchor:
                    anchor = s2

        if not media and not unsupported:
            await send_plain(user_id, text or "Ответ куратора:")

        return True
    except Exception as e:
        print("admin bundle failed:", e)
        return False

# ============ ЛС от юзеров: сбор и пересылка (склейка) ============

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
    thread_id = ROLE_TOPICS.get(role_key) if role_key else None

    header_text, _ = _compose_header(m, role_key)
    user_text = _extract_user_text(m)

    if m.media_group_id:
        gid = m.media_group_id
        _MEDIA_BUFFERS.setdefault(gid, []).append(m)

        async def _flush_group(group_id: str):
            await asyncio.sleep(0.8)
            items = _MEDIA_BUFFERS.pop(group_id, [])
            if not items:
                return
            first = items[0]
            st2 = STATE.get(first.from_user.id) or {}
            role_key2 = st2.get("role") or USER_LAST_ROLE.get(first.from_user.id)
            thread_id2 = ROLE_TOPICS.get(role_key2) if role_key2 else None
            header2, _ = _compose_header(first, role_key2)
            utext = ""
            for it in items:
                t = _extract_user_text(it)
                if t:
                    utext = t
                    break
            sent_head = await _send_bundled_to_group(header2, utext, thread_id2, items)
            if sent_head:
                remember_reply_target(sent_head, first.from_user.id)
            if group_id not in _ACKED_MEDIA_GROUPS:
                try:
                    await send_plain(first.chat.id, "Сообщение доставлено кураторам.")
                except Exception:
                    pass
                _ACKED_MEDIA_GROUPS.add(group_id)

        if gid not in _MEDIA_TASKS or _MEDIA_TASKS[gid].done():
            _MEDIA_TASKS[gid] = asyncio.create_task(_flush_group(gid))
        return

    items: list[Message] = []
    has_media = any([m.photo, m.video, m.document, getattr(m, "audio", None), getattr(m, "animation", None)])
    if has_media:
        items.append(m)

    sent_anchor = await _send_bundled_to_group(header_text, user_text if not has_media else user_text, thread_id, items)
    if sent_anchor:
        remember_reply_target(sent_anchor, m.from_user.id)
    try:
        await send_plain(m.chat.id, "Сообщение доставлено кураторам.")
    except Exception:
        pass

# ============ /pm: теперь с бандлингом альбомов админа ============

@dp.message(Command("pm"))
async def admin_pm(m: Message, command: CommandObject):
    if m.chat.type not in ("supergroup", "group"):
        return
    if not is_admin(m.from_user.id):
        return

    args = (command.args or "").split(maxsplit=1)

    if not args and not m.reply_to_message:
        await send_plain(m.chat.id, "Использование: ответьте на сообщение кандидата ИЛИ /pm ID [текст]")
        return

    replied_user_id = None
    if m.reply_to_message:
        replied_user_id = REPLY_MAP.get((m.chat.id, m.reply_to_message.message_id))

    user_id = None
    tail_text = ""
    if args and args[0].isdigit():
        user_id = int(args[0])
        tail_text = args[1].strip() if len(args) > 1 else ""
    elif replied_user_id:
        user_id = replied_user_id
        tail_text = (args[0].strip() if args else "")
    else:
        await send_plain(m.chat.id, "Айди должен быть числом. Пример: /pm 123456789 Привет\nИли просто ответьте на сообщение кандидата.")
        return

    has_media = any([m.photo, m.document, m.video, m.animation, m.voice, m.audio, m.sticker])

    # общий текст ответа
    raw_caption = m.caption or ""
    clean_caption = re.sub(r"(?i)^/pm(\s+\d+)?\s*", "", raw_caption).strip()
    base_text = "Ответ куратора:"
    extra = (tail_text or clean_caption or "").strip()
    if extra:
        base_text += "\n\n" + extra

    # Если это альбом — буферизуем и шлём пакетом
    if m.media_group_id:
        key = (user_id, m.media_group_id)
        _OUT_BUFFERS.setdefault(key, []).append(m)

        async def _flush_out(k):
            await asyncio.sleep(0.8)
            items = _OUT_BUFFERS.pop(k, [])
            if not items:
                return
            # Найдём первый осмысленный текст, если base_text пустой
            text = base_text
            if ":\n\n" not in base_text:
                for it in items:
                    t = _extract_user_text(it)
                    if t:
                        text = "Ответ куратора:\n\n" + t
                        break
            ok = await _send_admin_bundle_to_user(k[0], text, items)
            await send_plain(m.chat.id, "✅ Сообщение отправлено пользователю." if ok else "⚠️ Не удалось отправить пакет.")

        if key not in _OUT_TASKS or _OUT_TASKS[key].done():
            _OUT_TASKS[key] = asyncio.create_task(_flush_out(key))
        return

    # Не альбом
    try:
        if has_media:
            ok = await _send_admin_bundle_to_user(user_id, base_text, [m])
            await send_plain(m.chat.id, "✅ Сообщение отправлено пользователю." if ok else "⚠️ Не удалось отправить.")
        else:
            # чистый текст
            await send_plain(user_id, base_text)
            await send_plain(m.chat.id, "✅ Сообщение отправлено пользователю.")
    except Exception as e:
        await send_plain(m.chat.id, f"⚠️ Не удалось отправить: {e}")

# ============ Свайп-ответ в группе: тоже бандлим, если альбом ============

@dp.message(F.chat.type.in_({ChatType.SUPERGROUP, ChatType.GROUP}) & F.reply_to_message)
async def admin_reply_by_swipe(m: Message):
    if not is_admin(m.from_user.id):
        return

    key = (m.chat.id, m.reply_to_message.message_id)
    user_id = REPLY_MAP.get(key)

    if not user_id:
        try:
            txt = m.reply_to_message.text or m.reply_to_message.caption or ""
            mobj = re.search(r"id\s+(\d{6,})", txt)
            if mobj:
                user_id = int(mobj.group(1))
        except Exception:
            pass

    if not user_id:
        await send_plain(m.chat.id, "Использование: ответьте на сообщение кандидата в этой теме, тогда я пойму, кому отправить.")
        return

    base_text = "Ответ куратора:"
    if m.text and not m.text.startswith("/pm"):
        base_text += "\n\n" + m.text.strip()

    # Альбом админа
    if m.media_group_id:
        key2 = (user_id, m.media_group_id)
        _OUT_BUFFERS.setdefault(key2, []).append(m)

        async def _flush_out(k):
            await asyncio.sleep(0.8)
            items = _OUT_BUFFERS.pop(k, [])
            if not items:
                return
            text = base_text
            if ":\n\n" not in base_text:
                for it in items:
                    t = _extract_user_text(it)
                    if t:
                        text = "Ответ куратора:\n\n" + t
                        break
            ok = await _send_admin_bundle_to_user(k[0], text, items)
            await send_plain(m.chat.id, "✅ Сообщение отправлено пользователю." if ok else "⚠️ Не удалось отправить пакет.")

        if key2 not in _OUT_TASKS or _OUT_TASKS[key2].done():
            _OUT_TASKS[key2] = asyncio.create_task(_flush_out(key2))
        return

    # Не альбом
    try:
        has_media = any([m.photo, m.video, m.document, m.animation, m.voice, m.audio, m.sticker])
        if has_media:
            ok = await _send_admin_bundle_to_user(user_id, base_text, [m])
            await send_plain(m.chat.id, "✅ Сообщение отправлено пользователю." if ok else "⚠️ Не удалось отправить.")
        else:
            await send_plain(user_id, base_text)
            await send_plain(m.chat.id, "✅ Сообщение отправлено пользователю.")
    except Exception as e:
        await send_plain(m.chat.id, f"⚠️ Не удалось отправить: {e}")

# ============ HELP / HTTP / main (без изменений) ============

# ... остальной хвост файла без изменений ...
