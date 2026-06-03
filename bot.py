import asyncio
import logging
from datetime import datetime, timedelta

import bcrypt
import psycopg2
import psycopg2.extras
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("NoryxHack")

# ══════════════════════════════════════════════════════════════════
#   КОНФИГУРАЦИЯ
# ══════════════════════════════════════════════════════════════════

BOT_TOKEN        = "8951682715:AAGu2N_L9OhvLXc1wfoupk4oC9mbMsSXHJg"
CHANNEL_USERNAME = "@noryxhack"
CHANNEL_ID       = -1003928878729
ADMINS           = ["illusiononce", "ANTIITAPCHIKo", "f_luger"]
BETA_LINK        = "https://t.me/+ueQeqop01DRiM2Ni"
DATABASE_URL     = "postgresql://postgres.lriagtyzxhquojilqnsx:[noryxhackbustit67]@aws-1-eu-central-1.pooler.supabase.com:6543/postgres"

PROMO_DISCOUNT   = 9  # %

PLANS = {
    "30D":      {"days": 30,    "stars": 90,  "label": "30 дней"},
    "90D":      {"days": 90,    "stars": 180, "label": "90 дней"},
    "LIFETIME": {"days": 99999, "stars": 300, "label": "Навсегда"},
}

# ══════════════════════════════════════════════════════════════════
#   БАЗА ДАННЫХ (PostgreSQL)
# ══════════════════════════════════════════════════════════════════

def db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def init_db():
    c = db()
    cur = c.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            tg_id         BIGINT UNIQUE NOT NULL,
            username      TEXT,
            login         TEXT UNIQUE,
            password_hash TEXT,
            hwid          TEXT,
            role          TEXT DEFAULT 'FREE',
            status        TEXT DEFAULT 'DEFOLT',
            sub_bought_at TIMESTAMP,
            sub_expires   TIMESTAMP,
            media_balance REAL DEFAULT 0.0,
            is_banned     INTEGER DEFAULT 0,
            created_at    TIMESTAMP DEFAULT NOW()
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            id          SERIAL PRIMARY KEY,
            code        TEXT UNIQUE NOT NULL,
            owner_tg_id BIGINT,
            discount    INTEGER DEFAULT 8,
            created_at  TIMESTAMP DEFAULT NOW()
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS promo_activations (
            id           SERIAL PRIMARY KEY,
            code         TEXT NOT NULL,
            tg_id        BIGINT NOT NULL,
            activated_at TIMESTAMP DEFAULT NOW()
        )""")
    c.commit()
    cur.close()
    c.close()


# ── users ──────────────────────────────────────────────────────────

def get_user(tg_id):
    c = db()
    cur = c.cursor()
    cur.execute("SELECT * FROM users WHERE tg_id=%s", (tg_id,))
    u = cur.fetchone()
    cur.close(); c.close()
    return u

def get_user_by_username(username):
    c = db()
    cur = c.cursor()
    cur.execute("SELECT * FROM users WHERE username=%s", (username.lstrip("@"),))
    u = cur.fetchone()
    cur.close(); c.close()
    return u

def get_user_by_login(login):
    c = db()
    cur = c.cursor()
    cur.execute("SELECT * FROM users WHERE login=%s", (login.lower(),))
    u = cur.fetchone()
    cur.close(); c.close()
    return u

def login_exists(login):
    c = db()
    cur = c.cursor()
    cur.execute("SELECT id FROM users WHERE login=%s", (login.lower(),))
    r = cur.fetchone()
    cur.close(); c.close()
    return r is not None

def get_all_users():
    c = db()
    cur = c.cursor()
    cur.execute("SELECT * FROM users ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close(); c.close()
    return rows

def upsert_user(tg_id, username):
    c = db()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO users (tg_id, username) VALUES (%s, %s)
        ON CONFLICT(tg_id) DO UPDATE SET username=EXCLUDED.username
    """, (tg_id, username or ""))
    c.commit(); cur.close(); c.close()

def register_user(tg_id, username, login, password):
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    c = db()
    cur = c.cursor()
    cur.execute("""
        UPDATE users SET login=%s, password_hash=%s WHERE tg_id=%s
    """, (login.lower(), pw_hash, tg_id))
    c.commit(); cur.close(); c.close()

def verify_password(tg_id, password):
    u = get_user(tg_id)
    if not u or not u["password_hash"]:
        return False
    return bcrypt.checkpw(password.encode(), u["password_hash"].encode())

def change_password(tg_id, new_password):
    pw_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    c = db()
    cur = c.cursor()
    cur.execute("UPDATE users SET password_hash=%s WHERE tg_id=%s", (pw_hash, tg_id))
    c.commit(); cur.close(); c.close()

def update_hwid(tg_id, hwid):
    c = db()
    cur = c.cursor()
    cur.execute("UPDATE users SET hwid=%s WHERE tg_id=%s", (hwid, tg_id))
    c.commit(); cur.close(); c.close()

def is_registered(tg_id):
    u = get_user(tg_id)
    return u is not None and u.get("login") is not None

def ban_user(username):
    c = db()
    cur = c.cursor()
    cur.execute("UPDATE users SET is_banned=1 WHERE username=%s", (username.lstrip("@"),))
    c.commit(); cur.close(); c.close()

def unban_user(username):
    c = db()
    cur = c.cursor()
    cur.execute("UPDATE users SET is_banned=0 WHERE username=%s", (username.lstrip("@"),))
    c.commit(); cur.close(); c.close()

def is_banned(tg_id):
    u = get_user(tg_id)
    return bool(u and u["is_banned"])

def has_active_sub(tg_id):
    u = get_user(tg_id)
    if not u or u["role"] == "FREE" or not u["sub_expires"]:
        return False
    return u["sub_expires"] > datetime.now()

def grant_sub(tg_id, days):
    now = datetime.now()
    exp = now + timedelta(days=days)
    c = db()
    cur = c.cursor()
    cur.execute("""
        UPDATE users SET role='BETA', sub_bought_at=%s, sub_expires=%s WHERE tg_id=%s
    """, (now, exp, tg_id))
    c.commit(); cur.close(); c.close()

# ── media ──────────────────────────────────────────────────────────

def set_media(tg_id):
    c = db()
    cur = c.cursor()
    cur.execute("UPDATE users SET status='MEDIA' WHERE tg_id=%s", (tg_id,))
    c.commit(); cur.close(); c.close()

def get_media_users():
    c = db()
    cur = c.cursor()
    cur.execute("SELECT * FROM users WHERE status='MEDIA'")
    rows = cur.fetchall()
    cur.close(); c.close()
    return rows

def add_balance(tg_id, amount):
    c = db()
    cur = c.cursor()
    cur.execute("UPDATE users SET media_balance=media_balance+%s WHERE tg_id=%s", (amount, tg_id))
    c.commit(); cur.close(); c.close()

# ── promos ─────────────────────────────────────────────────────────

def get_all_promos():
    c = db()
    cur = c.cursor()
    cur.execute("SELECT * FROM promo_codes ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close(); c.close()
    return rows

def get_activated_promos():
    c = db()
    cur = c.cursor()
    cur.execute("""
        SELECT code, COUNT(*) as cnt FROM promo_activations
        GROUP BY code ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    cur.close(); c.close()
    return rows

def create_promo(code, owner_id):
    c = db()
    cur = c.cursor()
    try:
        cur.execute("INSERT INTO promo_codes (code,owner_tg_id,discount) VALUES (%s,%s,%s)",
                    (code, owner_id, PROMO_DISCOUNT))
        c.commit(); cur.close(); c.close()
        return True
    except psycopg2.errors.UniqueViolation:
        c.rollback(); cur.close(); c.close()
        return False

def delete_promo(code):
    c = db()
    cur = c.cursor()
    cur.execute("DELETE FROM promo_codes WHERE code=%s", (code,))
    deleted = cur.rowcount > 0
    c.commit(); cur.close(); c.close()
    return deleted

def activate_promo(code, tg_id):
    c = db()
    cur = c.cursor()
    cur.execute("SELECT * FROM promo_codes WHERE code=%s", (code,))
    promo = cur.fetchone()
    if not promo:
        cur.close(); c.close(); return None
    cur.execute("SELECT id FROM promo_activations WHERE code=%s AND tg_id=%s", (code, tg_id))
    if cur.fetchone():
        cur.close(); c.close(); return -1
    cur.execute("INSERT INTO promo_activations (code,tg_id) VALUES (%s,%s)", (code, tg_id))
    c.commit()
    discount = promo["discount"]
    cur.close(); c.close()
    return discount

# ══════════════════════════════════════════════════════════════════
#   ХЕЛПЕРЫ
# ══════════════════════════════════════════════════════════════════

def fmt_dt(s):
    if not s: return "—"
    try:
        if isinstance(s, datetime):
            return s.strftime("%d.%m.%Y %H:%M")
        return datetime.strptime(str(s), "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(s)

def role_fmt(r):   return "👑 BETA"  if r == "BETA"  else "🆓 FREE"
def status_fmt(s): return "🌟 MEDIA" if s == "MEDIA" else "⚙️ DEFOLT"

def is_admin(username):
    return (username or "").lstrip("@").lower() in [a.lower() for a in ADMINS]

def mask_hwid(hwid):
    if not hwid or hwid == "—":
        return "не привязан"
    if len(hwid) <= 8:
        return hwid
    return hwid[:8] + "•" * min(len(hwid) - 8, 16)

async def check_sub_channel(bot: Bot, user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(CHANNEL_ID, user_id)
        return m.status not in ("left", "kicked", "banned")
    except Exception:
        return False

# ══════════════════════════════════════════════════════════════════
#   КЛАВИАТУРЫ
# ══════════════════════════════════════════════════════════════════

def kb(*rows):
    buttons = []
    for row in rows:
        line = []
        for item in row:
            text, action = item
            if action.startswith("http"):
                line.append(InlineKeyboardButton(text=text, url=action))
            else:
                line.append(InlineKeyboardButton(text=text, callback_data=action))
        buttons.append(line)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def back(target="main"):
    return kb([("◀️ Назад", f"back_{target}")])

def cancel(target="admin_panel"):
    return kb([("❌ Отмена", f"back_{target}")])

def main_menu_kb(admin=False, has_sub=False):
    rows = [
        [("❔ Информация",         "info")],
        [("💸 Купить клиент",      "buy")],
        [("📱 Проверить подписку", "check_sub")],
        [("📝 Профиль",            "profile")],
    ]
    if has_sub:
        rows.append([("📁 Скачать Бета", "download_beta")])
    rows.append([("🪩 Медиа", "media_user")])
    if admin:
        rows.append([("🚩 Админ панель", "admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
        for row in rows
    ])

def subscribe_kb():
    return kb(
        [("📢 Подписаться на канал", f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
        [("✅ Я подписался",          "check_channel_sub")]
    )

def buy_kb():
    rows = []
    icons = {"30D": "🥉", "90D": "🥈", "LIFETIME": "👑"}
    for key, p in PLANS.items():
        rows.append([(f"{icons[key]} {key} — {p['stars']} ⭐", f"buy_plan_{key}")])
    rows.append([("◀️ Назад", "back_main")])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
        for row in rows
    ])

def confirm_buy_kb(plan_key, stars):
    return kb(
        [(f"💳 Оплатить {stars} ⭐",   f"pay_stars_{plan_key}_{stars}")],
        [("🏷 Использовать промокод",  f"use_promo_{plan_key}")],
        [("◀️ Назад",                  "buy")]
    )

def check_sub_kb(has_sub):
    if has_sub:
        return kb([("📁 Скачать Бета", "download_beta")], [("◀️ Назад", "back_main")])
    return kb([("💸 Купить клиент", "buy")], [("◀️ Назад", "back_main")])

def profile_kb():
    return kb(
        [("🔐 Сменить пароль", "change_password")],
        [("◀️ Назад",          "back_main")]
    )

def admin_panel_kb():
    return kb(
        [("🎟 Промокоды",   "admin_promos")],
        [("🎁 Выдать Бета",  "admin_give_beta")],
        [("👥 Юзеры",        "admin_users")],
        [("🌟 Медиа",        "admin_media")],
        [("◀️ Назад",        "back_main")]
    )

def admin_promos_kb():
    return kb(
        [("✅ Активированные", "admin_promos_activated")],
        [("📋 Все промокоды",  "admin_promos_all")],
        [("➕ Создать",         "admin_promo_create")],
        [("🗑 Удалить",         "admin_promo_delete")],
        [("◀️ Назад",          "admin_panel")]
    )

def give_beta_kb():
    icons = {"30D": "🥉", "90D": "🥈", "LIFETIME": "👑"}
    rows = [[(f"{icons[k]} {p['label']}", f"admin_give_{k}")] for k, p in PLANS.items()]
    rows.append([("◀️ Назад", "admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
        for row in rows
    ])

def admin_media_kb():
    return kb(
        [("🌟 Выдать медиа",     "admin_media_give")],
        [("💰 Начислить баланс", "admin_media_balance")],
        [("◀️ Назад",            "admin_panel")]
    )

def media_list_kb(users):
    rows = []
    for u in users:
        name = u["username"] or str(u["tg_id"])
        rows.append([(f"@{name}  💰 {u['media_balance']:.0f} ⭐",
                      f"admin_topup_{u['tg_id']}")])
    rows.append([("◀️ Назад", "admin_media")])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
        for row in rows
    ])

# ══════════════════════════════════════════════════════════════════
#   FSM СОСТОЯНИЯ
# ══════════════════════════════════════════════════════════════════

class RegState(StatesGroup):
    waiting_login    = State()
    waiting_password = State()

class ChangePassState(StatesGroup):
    waiting_old_pass = State()
    waiting_new_pass = State()
    waiting_confirm  = State()

class BuyState(StatesGroup):
    waiting_promo = State()

class AdminState(StatesGroup):
    give_beta_user   = State()
    give_beta_plan   = State()
    promo_create_usr = State()
    promo_create_cod = State()
    promo_delete_cod = State()
    media_give_user  = State()
    topup_amount     = State()

# ══════════════════════════════════════════════════════════════════
#   РОУТЕР
# ══════════════════════════════════════════════════════════════════

router = Router()

# ── Главное меню ──────────────────────────────────────────────────

async def send_main(bot: Bot, chat_id: int, tg_id: int, username: str):
    nick = f"@{username}" if username else f"#{tg_id}"
    text = (
        "╔══════════════════════╗\n"
        "║   🎮  NoryxHack Bot   ║\n"
        "╚══════════════════════╝\n\n"
        f"👋 Добро пожаловать, <b>{nick}</b>!\n\n"
        "Что сегодня хотите узнать?"
    )
    await bot.send_message(
        chat_id, text, parse_mode="HTML",
        reply_markup=main_menu_kb(
            admin=is_admin(username),
            has_sub=has_active_sub(tg_id)
        )
    )

# ══════════════════════════════════════════════════════════════════
#   /start — регистрация при первом запуске
# ══════════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(m: Message, bot: Bot, state: FSMContext):
    tg_id    = m.from_user.id
    username = m.from_user.username or ""

    upsert_user(tg_id, username)

    if is_banned(tg_id):
        await m.answer("🚫 <b>Вы заблокированы.</b>", parse_mode="HTML")
        return

    if not await check_sub_channel(bot, tg_id):
        await m.answer(
            "╔══════════════════════╗\n"
            "║   🎮  NoryxHack Bot   ║\n"
            "╚══════════════════════╝\n\n"
            "⚠️ Для использования бота необходимо\n"
            f"подписаться на канал <b>{CHANNEL_USERNAME}</b>!",
            parse_mode="HTML",
            reply_markup=subscribe_kb()
        )
        return

    # Первый запуск — просим создать аккаунт
    if not is_registered(tg_id):
        await state.set_state(RegState.waiting_login)
        await m.answer(
            "╔══════════════════════╗\n"
            "║   🔐  Регистрация     ║\n"
            "╚══════════════════════╝\n\n"
            "👋 Добро пожаловать в <b>NoryxHack</b>!\n\n"
            "Для начала создайте аккаунт.\n"
            "Этот логин и пароль вы будете использовать\n"
            "для входа в клиент.\n\n"
            "📝 Введите желаемый <b>логин</b>:\n"
            "<i>(латинские буквы, цифры и _ • 3–20 символов)</i>",
            parse_mode="HTML"
        )
        return

    await send_main(bot, m.chat.id, tg_id, username)

# ── Шаг 1: логин ──────────────────────────────────────────────────

@router.message(RegState.waiting_login)
async def reg_login(m: Message, state: FSMContext):
    login = m.text.strip()

    if not login.replace("_", "").isalnum() or not (3 <= len(login) <= 20):
        await m.answer(
            "❌ <b>Неверный формат логина!</b>\n\n"
            "Допускаются: латинские буквы, цифры, _ (подчёркивание)\n"
            "Длина: от 3 до 20 символов\n\n"
            "📝 Попробуйте ещё раз:",
            parse_mode="HTML"
        )
        return

    if login_exists(login):
        await m.answer(
            f"❌ <b>Логин «{login}» уже занят!</b>\n\n"
            "📝 Введите другой логин:",
            parse_mode="HTML"
        )
        return

    await state.update_data(reg_login=login)
    await state.set_state(RegState.waiting_password)
    await m.answer(
        f"✅ Логин <b>{login}</b> свободен!\n\n"
        "🔑 Теперь придумайте <b>пароль</b>:\n"
        "<i>(минимум 6 символов)</i>\n\n"
        "⚠️ Сообщение с паролем будет удалено автоматически.",
        parse_mode="HTML"
    )

# ── Шаг 2: пароль ─────────────────────────────────────────────────

@router.message(RegState.waiting_password)
async def reg_password(m: Message, state: FSMContext, bot: Bot):
    password = m.text.strip()

    # Удаляем сообщение с паролем
    try:
        await m.delete()
    except Exception:
        pass

    if len(password) < 6:
        await bot.send_message(
            m.chat.id,
            "❌ <b>Пароль слишком короткий!</b>\n\n"
            "Минимум 6 символов.\n\n"
            "🔑 Введите пароль ещё раз:",
            parse_mode="HTML"
        )
        return

    data     = await state.get_data()
    login    = data["reg_login"]
    tg_id    = m.from_user.id
    username = m.from_user.username or ""

    register_user(tg_id, username, login, password)
    await state.clear()

    await bot.send_message(
        m.chat.id,
        "╔══════════════════════╗\n"
        "║  ✅  Аккаунт создан!  ║\n"
        "╚══════════════════════╝\n\n"
        f"🎉 Добро пожаловать, <b>@{username or login}</b>!\n\n"
        f"👤 <b>Логин:</b> <code>{login}</code>\n"
        "🔐 <b>Пароль:</b> сохранён\n\n"
        "Используйте эти данные для входа в клиент <b>NoryxHack</b>.\n\n"
        "💡 Чтобы привязать HWID, отправьте:\n"
        "<code>/hwid ВАШ_HWID</code>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(
            admin=is_admin(username),
            has_sub=has_active_sub(tg_id)
        )
    )

# ══════════════════════════════════════════════════════════════════
#   СМЕНА ПАРОЛЯ
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "change_password")
async def cb_change_password(cb: CallbackQuery, state: FSMContext):
    await state.set_state(ChangePassState.waiting_old_pass)
    await cb.message.edit_text(
        "╔══════════════════════╗\n"
        "║   🔐  Смена пароля    ║\n"
        "╚══════════════════════╝\n\n"
        "🔑 Введите <b>текущий пароль</b>:\n"
        "<i>(сообщение удалится автоматически)</i>",
        parse_mode="HTML",
        reply_markup=cancel("profile")
    )
    await cb.answer()


@router.message(ChangePassState.waiting_old_pass)
async def change_pass_old(m: Message, state: FSMContext, bot: Bot):
    tg_id = m.from_user.id
    text  = m.text.strip()
    try:
        await m.delete()
    except Exception:
        pass

    if not verify_password(tg_id, text):
        await bot.send_message(
            m.chat.id,
            "❌ <b>Неверный пароль!</b>\n\nПопробуйте ещё раз:",
            parse_mode="HTML",
            reply_markup=cancel("profile")
        )
        return

    await state.set_state(ChangePassState.waiting_new_pass)
    await bot.send_message(
        m.chat.id,
        "✅ Пароль подтверждён!\n\n"
        "🔑 Введите <b>новый пароль</b>:\n"
        "<i>(минимум 6 символов)</i>",
        parse_mode="HTML",
        reply_markup=cancel("profile")
    )


@router.message(ChangePassState.waiting_new_pass)
async def change_pass_new(m: Message, state: FSMContext, bot: Bot):
    new_pass = m.text.strip()
    try:
        await m.delete()
    except Exception:
        pass

    if len(new_pass) < 6:
        await bot.send_message(
            m.chat.id,
            "❌ Пароль слишком короткий! Минимум 6 символов.\n\n"
            "🔑 Введите новый пароль:",
            parse_mode="HTML",
            reply_markup=cancel("profile")
        )
        return

    await state.update_data(new_pass=new_pass)
    await state.set_state(ChangePassState.waiting_confirm)
    await bot.send_message(
        m.chat.id,
        "🔑 Повторите <b>новый пароль</b> для подтверждения:",
        parse_mode="HTML",
        reply_markup=cancel("profile")
    )


@router.message(ChangePassState.waiting_confirm)
async def change_pass_confirm(m: Message, state: FSMContext, bot: Bot):
    tg_id = m.from_user.id
    try:
        await m.delete()
    except Exception:
        pass

    data = await state.get_data()

    if m.text.strip() != data["new_pass"]:
        await bot.send_message(
            m.chat.id,
            "❌ <b>Пароли не совпадают!</b>\n\nВведите новый пароль заново:",
            parse_mode="HTML",
            reply_markup=cancel("profile")
        )
        await state.set_state(ChangePassState.waiting_new_pass)
        return

    await state.clear()
    change_password(tg_id, data["new_pass"])
    await bot.send_message(
        m.chat.id,
        "╔══════════════════════╗\n"
        "║  ✅  Пароль изменён!  ║\n"
        "╚══════════════════════╝\n\n"
        "🔐 Пароль успешно обновлён!\n\n"
        "Используйте новый пароль для входа в клиент.",
        parse_mode="HTML",
        reply_markup=back("main")
    )

# ══════════════════════════════════════════════════════════════════
#   HWID — обновление через команду
# ══════════════════════════════════════════════════════════════════

@router.message(Command("hwid"))
async def cmd_hwid(m: Message):
    """Клиент отправляет: /hwid <HWID>"""
    tg_id = m.from_user.id
    if not is_registered(tg_id):
        await m.answer("❌ Сначала зарегистрируйтесь через /start")
        return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await m.answer("❌ Укажите HWID: /hwid <ваш_hwid>")
        return
    hwid = parts[1].strip()
    update_hwid(tg_id, hwid)
    await m.answer("✅ <b>HWID привязан!</b>", parse_mode="HTML")

# ══════════════════════════════════════════════════════════════════
#   ПОДПИСКА НА КАНАЛ
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "check_channel_sub")
async def cb_check_channel(cb: CallbackQuery, bot: Bot, state: FSMContext):
    tg_id    = cb.from_user.id
    username = cb.from_user.username or ""
    upsert_user(tg_id, username)

    if is_banned(tg_id):
        await cb.answer("🚫 Вы заблокированы!", show_alert=True); return

    if not await check_sub_channel(bot, tg_id):
        await cb.answer("❌ Вы ещё не подписались!", show_alert=True); return

    await cb.message.delete()

    if not is_registered(tg_id):
        await state.set_state(RegState.waiting_login)
        await bot.send_message(
            cb.message.chat.id,
            "╔══════════════════════╗\n"
            "║   🔐  Регистрация     ║\n"
            "╚══════════════════════╝\n\n"
            "👋 Добро пожаловать в <b>NoryxHack</b>!\n\n"
            "Для начала создайте аккаунт.\n\n"
            "📝 Введите желаемый <b>логин</b>:\n"
            "<i>(латинские буквы, цифры и _ • 3–20 символов)</i>",
            parse_mode="HTML"
        )
        await cb.answer()
        return

    await send_main(bot, cb.message.chat.id, tg_id, username)
    await cb.answer()

# ── Назад ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "back_main")
async def cb_back_main(cb: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    await cb.message.delete()
    await send_main(bot, cb.message.chat.id, cb.from_user.id, cb.from_user.username or "")
    await cb.answer()

@router.callback_query(F.data == "back_profile")
async def cb_back_profile(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb_profile(cb)

# ── /ban  /unban ──────────────────────────────────────────────────

@router.message(Command("ban"))
async def cmd_ban(m: Message):
    if not is_admin(m.from_user.username or ""): return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        await m.answer("Использование: /ban @username"); return
    ban_user(parts[1])
    await m.answer(f"🚫 @{parts[1].lstrip('@')} заблокирован.", parse_mode="HTML")

@router.message(Command("unban"))
async def cmd_unban(m: Message):
    if not is_admin(m.from_user.username or ""): return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        await m.answer("Использование: /unban @username"); return
    unban_user(parts[1])
    await m.answer(f"✅ @{parts[1].lstrip('@')} разблокирован.", parse_mode="HTML")

# ══════════════════════════════════════════════════════════════════
#   ИНФОРМАЦИЯ
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "info")
async def cb_info(cb: CallbackQuery):
    await cb.message.edit_text(
        "╔══════════════════════╗\n"
        "║   ❔  Информация      ║\n"
        "╚══════════════════════╝\n\n"
        "🎮 <b>NoryxHack</b> — клиент, разработанный тремя людьми:\n\n"
        "👤 <b>illusiononce</b>\n"
        "👤 <b>ANTIITAP</b>\n"
        "👤 <b>Blue_CatGG</b>\n\n"
        "📌 Изначально создан для сервера <b>SpookyTime</b>,\n"
        "но стал мультисерверным клиентом для комфортной\n"
        "и приятной игры.\n\n"
        "⚡ Наслаждайтесь лучшим игровым опытом!",
        parse_mode="HTML", reply_markup=back("main")
    )
    await cb.answer()

# ══════════════════════════════════════════════════════════════════
#   ПРОФИЛЬ — с логином, HWID и кнопкой смены пароля
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "profile")
async def cb_profile(cb: CallbackQuery):
    tg_id    = cb.from_user.id
    username = cb.from_user.username or "—"
    u        = get_user(tg_id)
    if not u:
        await cb.answer("❌ Профиль не найден.", show_alert=True); return

    sub_ok    = "✅ Активна" if has_active_sub(tg_id) else "❌ Не активна"
    login     = u.get("login") or "—"
    hwid_show = mask_hwid(u.get("hwid"))

    await cb.message.edit_text(
        "╔══════════════════════╗\n"
        "║   📝  Профиль         ║\n"
        "╚══════════════════════╝\n\n"
        f"👤 <b>Telegram:</b> @{username}\n"
        f"🆔 <b>TG ID:</b> <code>{tg_id}</code>\n"
        f"🔑 <b>Логин:</b> <code>{login}</code>\n\n"
        f"🖥 <b>HWID:</b> <code>{hwid_show}</code>\n\n"
        f"📅 <b>Подписка куплена:</b>\n"
        f"    <code>{fmt_dt(u['sub_bought_at'])}</code>\n\n"
        f"⏳ <b>Подписка до:</b>\n"
        f"    <code>{fmt_dt(u['sub_expires'])}</code>\n\n"
        f"📊 <b>Статус подписки:</b> {sub_ok}\n\n"
        f"🎭 <b>Роль:</b>    {role_fmt(u['role'])}\n"
        f"🏷 <b>Статус:</b>  {status_fmt(u['status'])}",
        parse_mode="HTML",
        reply_markup=profile_kb()
    )
    await cb.answer()

# ══════════════════════════════════════════════════════════════════
#   ПРОВЕРИТЬ ПОДПИСКУ
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "check_sub")
async def cb_check_sub(cb: CallbackQuery):
    tg_id = cb.from_user.id
    u     = get_user(tg_id)
    has_s = has_active_sub(tg_id)
    if has_s:
        text = (
            "╔══════════════════════╗\n"
            "║  📱 Проверка подписки ║\n"
            "╚══════════════════════╝\n\n"
            "✅ <b>Подписка активна!</b>\n\n"
            f"⏳ Действует до: <code>{fmt_dt(u['sub_expires'])}</code>\n"
            f"🎭 Роль: {role_fmt(u['role'])}\n\n"
            "📁 Вы можете скачать клиент:"
        )
    else:
        text = (
            "╔══════════════════════╗\n"
            "║  📱 Проверка подписки ║\n"
            "╚══════════════════════╝\n\n"
            "❌ <b>Подписка не активна.</b>\n\n"
            "Приобретите клиент, чтобы получить доступ\n"
            "ко всем функциям <b>NoryxHack</b>!"
        )
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=check_sub_kb(has_s))
    await cb.answer()

# ══════════════════════════════════════════════════════════════════
#   СКАЧАТЬ БЕТУ
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "download_beta")
async def cb_download_beta(cb: CallbackQuery):
    if not has_active_sub(cb.from_user.id):
        await cb.answer("❌ У вас нет активной подписки!", show_alert=True); return
    await cb.message.edit_text(
        "╔══════════════════════╗\n"
        "║   📁  Скачать Бета    ║\n"
        "╚══════════════════════╝\n\n"
        "✅ <b>Подписка подтверждена!</b>\n\n"
        "🚀 Нажмите кнопку ниже, чтобы перейти\n"
        "в закрытый канал с клиентом <b>NoryxHack</b>:",
        parse_mode="HTML",
        reply_markup=kb(
            [("📥 Перейти к загрузке", BETA_LINK)],
            [("◀️ Назад", "back_main")]
        )
    )
    await cb.answer()

# ══════════════════════════════════════════════════════════════════
#   МЕДИА
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "media_user")
async def cb_media_user(cb: CallbackQuery):
    tg_id = cb.from_user.id
    u     = get_user(tg_id)
    if not u or u["status"] != "MEDIA":
        await cb.answer("🚫 У вас нет доступа к разделу Медиа.", show_alert=True); return
    await cb.message.edit_text(
        "╔══════════════════════╗\n"
        "║   🪩  Медиа           ║\n"
        "╚══════════════════════╝\n\n"
        f"👤 <b>Пользователь:</b> @{u['username'] or tg_id}\n"
        f"🌟 <b>Статус:</b> {status_fmt(u['status'])}\n\n"
        f"💰 <b>На счету:</b> <code>{u['media_balance']:.0f} ⭐</code>\n\n"
        "📌 Баланс начисляется администратором\n"
        "за медиа-активность.",
        parse_mode="HTML", reply_markup=back("main")
    )
    await cb.answer()

# ══════════════════════════════════════════════════════════════════
#   ПОКУПКА
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "buy")
async def cb_buy(cb: CallbackQuery):
    await cb.message.edit_text(
        "╔══════════════════════╗\n"
        "║   💸  Купить клиент   ║\n"
        "╚══════════════════════╝\n\n"
        "🎮 Выберите тарифный план:\n\n"
        "🥉 <b>30D</b>       — 30 дней    <code>90 ⭐</code>\n"
        "🥈 <b>90D</b>       — 90 дней   <code>180 ⭐</code>\n"
        "👑 <b>LIFETIME</b> — навсегда  <code>300 ⭐</code>\n\n"
        "⭐ Оплата — звёздами Telegram.\n"
        "🏷 Можно применить промокод для скидки 8%.",
        parse_mode="HTML", reply_markup=buy_kb()
    )
    await cb.answer()

@router.callback_query(F.data.startswith("buy_plan_"))
async def cb_buy_plan(cb: CallbackQuery):
    key  = cb.data.split("buy_plan_")[1]
    plan = PLANS.get(key)
    if not plan:
        await cb.answer("❌ Тариф не найден.", show_alert=True); return
    icons = {"30D": "🥉", "90D": "🥈", "LIFETIME": "👑"}
    await cb.message.edit_text(
        f"╔══════════════════════╗\n"
        f"║   💳  Оплата          ║\n"
        f"╚══════════════════════╝\n\n"
        f"📦 <b>Тариф:</b> {icons.get(key,'')} {key} — {plan['label']}\n"
        f"💰 <b>Стоимость:</b> <code>{plan['stars']} ⭐</code>\n\n"
        f"🏷 Есть промокод? Нажмите кнопку ниже\n"
        f"для получения скидки <b>8%</b>.\n\n"
        f"✅ Доступ будет выдан автоматически.",
        parse_mode="HTML", reply_markup=confirm_buy_kb(key, plan["stars"])
    )
    await cb.answer()

@router.callback_query(F.data.startswith("use_promo_"))
async def cb_use_promo(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split("use_promo_")[1]
    await state.set_state(BuyState.waiting_promo)
    await state.update_data(plan_key=key)
    await cb.message.edit_text(
        "🏷 <b>Введите промокод:</b>\n\nОтправьте код следующим сообщением.",
        parse_mode="HTML", reply_markup=cancel("buy")
    )
    await cb.answer()

@router.message(BuyState.waiting_promo)
async def process_promo(m: Message, state: FSMContext):
    code  = m.text.strip()
    data  = await state.get_data()
    key   = data.get("plan_key", "30D")
    tg_id = m.from_user.id

    result = activate_promo(code, tg_id)
    await state.clear()

    if result is None:
        await m.answer("❌ <b>Промокод не найден!</b>", parse_mode="HTML"); return
    if result == -1:
        await m.answer("⚠️ <b>Вы уже использовали этот промокод.</b>", parse_mode="HTML"); return

    stars      = PLANS[key]["stars"]
    discounted = int(stars * (1 - result / 100))
    await m.answer(
        f"✅ <b>Промокод применён!</b>\n\n"
        f"📦 Тариф: <b>{key}</b>\n"
        f"💰 Было: <s>{stars} ⭐</s>\n"
        f"🎉 Стало: <code>{discounted} ⭐</code> (скидка {result}%)\n\n"
        "Нажмите кнопку для оплаты:",
        parse_mode="HTML",
        reply_markup=kb(
            [(f"💳 Оплатить {discounted} ⭐", f"pay_stars_{key}_{discounted}")],
            [("◀️ Назад", "buy")]
        )
    )

async def send_invoice(bot: Bot, chat_id: int, plan_key: str, stars: int):
    plan = PLANS[plan_key]
    await bot.send_invoice(
        chat_id=chat_id,
        title=f"NoryxHack — {plan_key}",
        description=(
            f"🎮 Доступ к клиенту NoryxHack\n"
            f"📅 Период: {plan['label']}\n"
            f"✅ Доступ выдаётся автоматически."
        ),
        payload=f"sub_{plan_key}_{chat_id}",
        currency="XTR",
        prices=[LabeledPrice(label=f"NoryxHack {plan_key}", amount=stars)],
        provider_token="",
    )

@router.callback_query(F.data.startswith("pay_stars_"))
async def cb_pay_stars(cb: CallbackQuery, bot: Bot):
    parts    = cb.data.split("_")
    plan_key = parts[2]
    stars    = int(parts[3])
    await cb.message.delete()
    await send_invoice(bot, cb.message.chat.id, plan_key, stars)
    await cb.answer()

@router.pre_checkout_query()
async def pre_checkout(pcq: PreCheckoutQuery):
    await pcq.answer(ok=True)

@router.message(F.successful_payment)
async def on_payment(m: Message, bot: Bot):
    payload = m.successful_payment.invoice_payload
    parts   = payload.split("_")
    if len(parts) >= 2:
        plan_key = parts[1]
        plan     = PLANS.get(plan_key)
        if plan:
            grant_sub(m.from_user.id, plan["days"])
            nick = f"@{m.from_user.username}" if m.from_user.username else f"#{m.from_user.id}"
            await m.answer(
                "╔══════════════════════╗\n"
                "║  ✅  Оплата прошла!   ║\n"
                "╚══════════════════════╝\n\n"
                f"🎉 <b>Поздравляем, {nick}!</b>\n\n"
                f"📦 Тариф: <b>{plan_key}</b> — {plan['label']}\n"
                f"💰 Оплачено: <code>{m.successful_payment.total_amount} ⭐</code>\n\n"
                "📁 Теперь вам доступна кнопка <b>«Скачать Бета»</b>\n"
                "в главном меню!\n\n"
                "🚀 Приятной игры с NoryxHack!",
                parse_mode="HTML"
            )

# ══════════════════════════════════════════════════════════════════
#   АДМИН ПАНЕЛЬ
# ══════════════════════════════════════════════════════════════════

def admin_guard(cb: CallbackQuery) -> bool:
    return is_admin(cb.from_user.username or "")

@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(cb: CallbackQuery):
    if not admin_guard(cb):
        await cb.answer("🚫 Нет доступа!", show_alert=True); return
    await cb.message.edit_text(
        "╔══════════════════════╗\n"
        "║   🚩  Админ панель    ║\n"
        "╚══════════════════════╝\n\n"
        "👋 Добро пожаловать в панель управления!\n\n"
        "Выберите раздел:",
        parse_mode="HTML", reply_markup=admin_panel_kb()
    )
    await cb.answer()

@router.callback_query(F.data == "back_admin_panel")
async def cb_back_admin(cb: CallbackQuery, state: FSMContext):
    if not admin_guard(cb):
        await cb.answer("🚫 Нет доступа!", show_alert=True); return
    await state.clear()
    await cb.message.edit_text(
        "╔══════════════════════╗\n"
        "║   🚩  Админ панель    ║\n"
        "╚══════════════════════╝\n\n"
        "Выберите раздел:",
        parse_mode="HTML", reply_markup=admin_panel_kb()
    )
    await cb.answer()

@router.callback_query(F.data == "admin_users")
async def cb_admin_users(cb: CallbackQuery):
    if not admin_guard(cb):
        await cb.answer("🚫 Нет доступа!", show_alert=True); return
    users = get_all_users()
    if not users:
        text = "👥 Пользователей нет."
    else:
        lines = [
            "╔══════════════════════╗\n"
            "║   👥  Все юзеры       ║\n"
            "╚══════════════════════╝\n"
        ]
        for u in users[:50]:
            uname = f"@{u['username']}" if u["username"] else f"#{u['tg_id']}"
            login = u.get("login") or "—"
            sub   = "✅" if u["role"] == "BETA" else "❌"
            ban   = " 🚫" if u["is_banned"] else ""
            hwid  = "🖥✅" if u.get("hwid") else "🖥❌"
            lines.append(
                f"{uname}{ban}  <code>{login}</code>  {hwid}\n"
                f"  {role_fmt(u['role'])}  {status_fmt(u['status'])}  📱{sub}\n"
            )
        text = "\n".join(lines)
        if len(users) > 50:
            text += f"\n<i>...и ещё {len(users)-50}. Всего: {len(users)}</i>"
    await cb.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=kb([("◀️ Назад", "admin_panel")])
    )
    await cb.answer()

@router.callback_query(F.data == "admin_give_beta")
async def cb_admin_give_beta(cb: CallbackQuery, state: FSMContext):
    if not admin_guard(cb):
        await cb.answer("🚫 Нет доступа!", show_alert=True); return
    await state.set_state(AdminState.give_beta_user)
    await cb.message.edit_text(
        "╔══════════════════════╗\n"
        "║   🎁  Выдать Бета     ║\n"
        "╚══════════════════════╝\n\n"
        "👤 Введите <b>юзернейм</b> пользователя\n"
        "(без @, например: <code>username</code>):",
        parse_mode="HTML", reply_markup=cancel("admin_panel")
    )
    await cb.answer()

@router.message(AdminState.give_beta_user)
async def admin_give_user(m: Message, state: FSMContext):
    if not is_admin(m.from_user.username or ""): return
    username = m.text.strip().lstrip("@")
    user     = get_user_by_username(username)
    if not user:
        await m.answer(
            f"❌ <b>@{username}</b> не найден. Убедитесь, что он запускал бота.",
            parse_mode="HTML", reply_markup=cancel("admin_panel")
        ); return
    await state.update_data(target_id=user["tg_id"], target_name=username)
    await state.set_state(AdminState.give_beta_plan)
    await m.answer(
        f"✅ Пользователь: <b>@{username}</b>\n\nВыберите период:",
        parse_mode="HTML", reply_markup=give_beta_kb()
    )

@router.callback_query(F.data.startswith("admin_give_"), AdminState.give_beta_plan)
async def admin_give_plan(cb: CallbackQuery, state: FSMContext, bot: Bot):
    if not admin_guard(cb):
        await cb.answer("🚫 Нет доступа!", show_alert=True); return
    key  = cb.data.split("admin_give_")[1]
    plan = PLANS.get(key)
    data = await state.get_data()
    tid  = data.get("target_id")
    name = data.get("target_name")
    await state.clear()
    if plan and tid:
        grant_sub(tid, plan["days"])
        try:
            await bot.send_message(tid,
                f"🎉 <b>Вам выдана подписка NoryxHack!</b>\n\n"
                f"📦 Тариф: <b>{key}</b> — {plan['label']}\n"
                f"📁 Главное меню → <b>Скачать Бета</b>",
                parse_mode="HTML")
        except Exception: pass
        await cb.message.edit_text(
            f"✅ Подписка <b>{key}</b> ({plan['label']}) выдана @{name}!",
            parse_mode="HTML", reply_markup=back("admin_panel")
        )
    await cb.answer()

@router.callback_query(F.data == "admin_promos")
async def cb_admin_promos(cb: CallbackQuery):
    if not admin_guard(cb):
        await cb.answer("🚫 Нет доступа!", show_alert=True); return
    await cb.message.edit_text(
        "╔══════════════════════╗\n"
        "║   🎟  Промокоды       ║\n"
        "╚══════════════════════╝\n\n"
        "Управление промокодами:",
        parse_mode="HTML", reply_markup=admin_promos_kb()
    )
    await cb.answer()

@router.callback_query(F.data == "admin_promos_all")
async def cb_promos_all(cb: CallbackQuery):
    if not admin_guard(cb):
        await cb.answer("🚫 Нет доступа!", show_alert=True); return
    promos = get_all_promos()
    if not promos:
        text = "📋 Промокодов ещё нет."
    else:
        lines = [
            "╔══════════════════════╗\n"
            "║   📋  Все промокоды   ║\n"
            "╚══════════════════════╝\n"
        ]
        for p in promos:
            owner = get_user(p["owner_tg_id"]) if p["owner_tg_id"] else None
            oname = f"@{owner['username']}" if owner and owner["username"] else f"#{p['owner_tg_id']}"
            lines.append(
                f"🏷 <code>{p['code']}</code>\n"
                f"  👤 {oname}  💰 {p['discount']}%  📅 {fmt_dt(p['created_at'])}\n"
            )
        text = "\n".join(lines)
    await cb.message.edit_text(text, parse_mode="HTML",
        reply_markup=kb([("◀️ Назад", "admin_promos")]))
    await cb.answer()

@router.callback_query(F.data == "admin_promos_activated")
async def cb_promos_activated(cb: CallbackQuery):
    if not admin_guard(cb):
        await cb.answer("🚫 Нет доступа!", show_alert=True); return
    rows = get_activated_promos()
    if not rows:
        text = "✅ Ни один промокод ещё не активирован."
    else:
        lines = [
            "╔══════════════════════╗\n"
            "║ ✅ Активированные    ║\n"
            "╚══════════════════════╝\n"
        ]
        for r in rows:
            lines.append(f"🏷 <code>{r['code']}</code>  —  <b>{r['cnt']}x</b>")
        text = "\n".join(lines)
    await cb.message.edit_text(text, parse_mode="HTML",
        reply_markup=kb([("◀️ Назад", "admin_promos")]))
    await cb.answer()

@router.callback_query(F.data == "admin_promo_create")
async def cb_promo_create(cb: CallbackQuery, state: FSMContext):
    if not admin_guard(cb):
        await cb.answer("🚫 Нет доступа!", show_alert=True); return
    await state.set_state(AdminState.promo_create_usr)
    await cb.message.edit_text(
        "➕ <b>Создание промокода</b>\n\n"
        "👤 Введите юзернейм владельца промокода\n(без @):",
        parse_mode="HTML", reply_markup=cancel("admin_promos")
    )
    await cb.answer()

@router.message(AdminState.promo_create_usr)
async def promo_create_usr(m: Message, state: FSMContext):
    if not is_admin(m.from_user.username or ""): return
    username = m.text.strip().lstrip("@")
    user     = get_user_by_username(username)
    if not user:
        await m.answer(f"❌ <b>@{username}</b> не найден.", parse_mode="HTML",
                       reply_markup=cancel("admin_promos")); return
    await state.update_data(owner_id=user["tg_id"], owner_name=username)
    await state.set_state(AdminState.promo_create_cod)
    await m.answer(
        f"✅ Владелец: <b>@{username}</b>\n\n"
        "🏷 Введите название промокода\n(например: <code>HACK2024</code>):",
        parse_mode="HTML", reply_markup=cancel("admin_promos")
    )

@router.message(AdminState.promo_create_cod)
async def promo_create_cod(m: Message, state: FSMContext):
    if not is_admin(m.from_user.username or ""): return
    code = m.text.strip().upper()
    data = await state.get_data()
    await state.clear()
    ok = create_promo(code, data["owner_id"])
    text = (
        f"✅ Промокод <code>{code}</code> создан!\n"
        f"👤 @{data['owner_name']}  💰 {PROMO_DISCOUNT}%"
    ) if ok else f"❌ Промокод <code>{code}</code> уже существует!"
    await m.answer(text, parse_mode="HTML",
                   reply_markup=kb([("◀️ Назад", "admin_promos")]))

@router.callback_query(F.data == "admin_promo_delete")
async def cb_promo_delete(cb: CallbackQuery, state: FSMContext):
    if not admin_guard(cb):
        await cb.answer("🚫 Нет доступа!", show_alert=True); return
    promos = get_all_promos()
    if not promos:
        await cb.answer("📋 Промокодов нет.", show_alert=True); return
    await state.set_state(AdminState.promo_delete_cod)
    lines = ["🗑 <b>Удаление промокода</b>\n\nСуществующие коды:"]
    for p in promos:
        lines.append(f"  • <code>{p['code']}</code>")
    lines.append("\n✏️ Введите код для удаления:")
    await cb.message.edit_text("\n".join(lines), parse_mode="HTML",
                               reply_markup=cancel("admin_promos"))
    await cb.answer()

@router.message(AdminState.promo_delete_cod)
async def promo_delete_cod(m: Message, state: FSMContext):
    if not is_admin(m.from_user.username or ""): return
    code = m.text.strip().upper()
    await state.clear()
    ok = delete_promo(code)
    text = (f"✅ Промокод <code>{code}</code> удалён."
            if ok else f"❌ Промокод <code>{code}</code> не найден.")
    await m.answer(text, parse_mode="HTML",
                   reply_markup=kb([("◀️ Назад", "admin_promos")]))

@router.callback_query(F.data == "admin_media")
async def cb_admin_media(cb: CallbackQuery):
    if not admin_guard(cb):
        await cb.answer("🚫 Нет доступа!", show_alert=True); return
    await cb.message.edit_text(
        "╔══════════════════════╗\n"
        "║   🌟  Медиа           ║\n"
        "╚══════════════════════╝\n\n"
        "Управление медиа-пользователями:",
        parse_mode="HTML", reply_markup=admin_media_kb()
    )
    await cb.answer()

@router.callback_query(F.data == "admin_media_give")
async def cb_media_give(cb: CallbackQuery, state: FSMContext):
    if not admin_guard(cb):
        await cb.answer("🚫 Нет доступа!", show_alert=True); return
    await state.set_state(AdminState.media_give_user)
    await cb.message.edit_text(
        "🌟 <b>Выдать медиа</b>\n\n👤 Введите юзернейм (без @):",
        parse_mode="HTML", reply_markup=cancel("admin_media")
    )
    await cb.answer()

@router.message(AdminState.media_give_user)
async def media_give_user(m: Message, state: FSMContext, bot: Bot):
    if not is_admin(m.from_user.username or ""): return
    username = m.text.strip().lstrip("@")
    user     = get_user_by_username(username)
    if not user:
        await m.answer(f"❌ <b>@{username}</b> не найден.", parse_mode="HTML",
                       reply_markup=cancel("admin_media")); return
    await state.clear()
    set_media(user["tg_id"])
    try:
        await bot.send_message(user["tg_id"],
            "🌟 <b>Вам выдан статус MEDIA!</b>\n\n"
            "Теперь у вас есть доступ к разделу 🪩 Медиа.",
            parse_mode="HTML")
    except Exception: pass
    await m.answer(
        f"✅ Статус <b>MEDIA</b> выдан пользователю <b>@{username}</b>!",
        parse_mode="HTML", reply_markup=kb([("◀️ Назад", "admin_media")])
    )

@router.callback_query(F.data == "admin_media_balance")
async def cb_media_balance(cb: CallbackQuery):
    if not admin_guard(cb):
        await cb.answer("🚫 Нет доступа!", show_alert=True); return
    users = get_media_users()
    if not users:
        await cb.answer("📋 Медиа-пользователей нет.", show_alert=True); return
    await cb.message.edit_text(
        "╔══════════════════════╗\n"
        "║  💰  Начислить баланс ║\n"
        "╚══════════════════════╝\n\n"
        "Выберите пользователя:",
        parse_mode="HTML", reply_markup=media_list_kb(users)
    )
    await cb.answer()

@router.callback_query(F.data.startswith("admin_topup_"))
async def cb_admin_topup(cb: CallbackQuery, state: FSMContext):
    if not admin_guard(cb):
        await cb.answer("🚫 Нет доступа!", show_alert=True); return
    tid    = int(cb.data.split("admin_topup_")[1])
    target = get_user(tid)
    uname  = target["username"] if target else str(tid)
    bal    = target["media_balance"] if target else 0
    await state.set_state(AdminState.topup_amount)
    await state.update_data(topup_id=tid, topup_name=uname)
    await cb.message.edit_text(
        f"💰 <b>Начисление баланса</b>\n\n"
        f"👤 Пользователь: <b>@{uname}</b>\n"
        f"💎 Текущий баланс: <code>{bal:.0f} ⭐</code>\n\n"
        "Введите сумму для начисления (например: <code>13</code>):",
        parse_mode="HTML", reply_markup=cancel("admin_media_balance")
    )
    await cb.answer()

@router.message(AdminState.topup_amount)
async def topup_amount(m: Message, state: FSMContext, bot: Bot):
    if not is_admin(m.from_user.username or ""): return
    try:
        amount = float(m.text.strip())
        if amount <= 0: raise ValueError
    except ValueError:
        await m.answer("❌ Введите корректную сумму (число > 0).",
                       reply_markup=cancel("admin_media_balance")); return
    data  = await state.get_data()
    tid   = data["topup_id"]
    uname = data["topup_name"]
    await state.clear()
    add_balance(tid, amount)
    updated = get_user(tid)
    try:
        await bot.send_message(tid,
            f"💰 <b>Вам начислено {amount:.0f} ⭐ на медиа-баланс!</b>\n\n"
            f"💎 Новый баланс: <code>{updated['media_balance']:.0f} ⭐</code>",
            parse_mode="HTML")
    except Exception: pass
    await m.answer(
        f"✅ Начислено <b>{amount:.0f} ⭐</b> пользователю <b>@{uname}</b>\n"
        f"💎 Новый баланс: <code>{updated['media_balance']:.0f} ⭐</code>",
        parse_mode="HTML",
        reply_markup=kb([("◀️ Назад", "admin_media")])
    )

@router.callback_query(F.data == "back_admin_media_balance")
async def cb_back_media_bal(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb_media_balance(cb)

# ══════════════════════════════════════════════════════════════════
#   ЗАПУСК
# ══════════════════════════════════════════════════════════════════

async def main():
    init_db()
    logger.info("✅ База данных инициализирована")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logger.info("🚀 NoryxHack Bot запущен!")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        logger.info("🛑 Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())
