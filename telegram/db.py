# -*- coding: utf-8 -*-
"""دیتابیس ربات فروش — فایل جدا: data/shop.db
جداول: users, transactions, receipts, plans, coupons,
coupon_uses, bot_accounts, tickets, admin_log, settings
"""

import os
import secrets
import sqlite3
import threading

from core import config as cfg
from core.utils import now_ms

_lock = threading.RLock()
_conn = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    tg_id INTEGER PRIMARY KEY,
    username TEXT DEFAULT '',
    balance INTEGER DEFAULT 0,
    ref_code TEXT UNIQUE,
    ref_by INTEGER DEFAULT 0,
    ref_earnings INTEGER DEFAULT 0,
    buys_count INTEGER DEFAULT 0,
    is_blocked INTEGER DEFAULT 0,
    trial_last INTEGER DEFAULT 0,
    joined_at INTEGER
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    kind TEXT,
    amount INTEGER,
    note TEXT DEFAULT '',
    ts INTEGER
);
CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    file_id TEXT,
    status TEXT DEFAULT 'pending',
    admin_id INTEGER DEFAULT 0,
    reason TEXT DEFAULT '',
    ts INTEGER,
    decided_at INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    days INTEGER,
    limit_gb INTEGER,
    price INTEGER,
    is_active INTEGER DEFAULT 1,
    sort INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    kind TEXT,
    value INTEGER,
    min_amount INTEGER DEFAULT 0,
    max_uses INTEGER DEFAULT 0,
    used INTEGER DEFAULT 0,
    expires_at INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS coupon_uses (
    coupon_id INTEGER,
    user_id INTEGER,
    PRIMARY KEY (coupon_id, user_id)
);
CREATE TABLE IF NOT EXISTS bot_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    plan_id INTEGER,
    email TEXT UNIQUE,
    sub_id TEXT,
    expires_at INTEGER,
    limit_bytes INTEGER,
    ts INTEGER
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    message TEXT,
    status TEXT DEFAULT 'open',
    ts INTEGER
);
CREATE TABLE IF NOT EXISTS admin_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    action TEXT,
    detail TEXT,
    ts INTEGER
);
CREATE TABLE IF NOT EXISTS settings (
    k TEXT PRIMARY KEY,
    v TEXT DEFAULT ''
);
"""

DEFAULTS = {
    "card_number": "6037-9999-9999-9999",
    "card_name": "نام صاحب حساب",
    "ref_percent": "20",
    "trial_gb": "1",
    "trial_days": "1",
    "trial_cooldown": "7",
    "min_deposit": "10000",
    "shop_title": "SF VPN Shop",
}


def _path() -> str:
    return os.path.join(cfg.DATA_DIR, "shop.db")


def connect() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is not None:
            return _conn
        cfg.ensure_dirs()
        _conn = sqlite3.connect(_path(), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.executescript(SCHEMA)
        _conn.commit()
        for k, v in DEFAULTS.items():
            _conn.execute(
                "INSERT OR IGNORE INTO settings(k,v) VALUES(?,?)", (k, v)
            )
        _conn.commit()
        _seed_plans()
        return _conn


def q(sql, args=(), one=False):
    with _lock:
        cur = connect().execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
    return (rows[0] if rows else None) if one else rows


def ex(sql, args=()) -> int:
    with _lock:
        c = connect()
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid


def _seed_plans():
    if q("SELECT id FROM plans LIMIT 1", one=True):
        return
    plans = [
        ("۱ ماهه — ۲۰ گیگ", 30, 20, 49000, 1),
        ("۳ ماهه — ۶۰ گیگ", 90, 60, 129000, 2),
        ("۶ ماهه — ۱۲۰ گیگ", 180, 120, 239000, 3),
    ]
    for title, days, gb, price, sort in plans:
        ex(
            "INSERT INTO plans(title,days,limit_gb,price,is_active,sort) "
            "VALUES(?,?,?,?,1,?)",
            (title, days, gb, price, sort),
        )


# ---------------- تنظیمات ----------------

def get_setting(k, d=None):
    r = q("SELECT v FROM settings WHERE k=?", (k,), one=True)
    if r and r["v"] not in (None, ""):
        return r["v"]
    return DEFAULTS.get(k, d if d is not None else "")


def set_setting(k, v):
    ex(
        "INSERT INTO settings(k,v) VALUES(?,?) "
        "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (k, str(v)),
    )


# ---------------- کاربران ----------------

def ensure_user(tg_id: int, username: str = "") -> dict:
    u = q("SELECT * FROM users WHERE tg_id=?", (tg_id,), one=True)
    if not u:
        code = "r" + secrets.token_hex(3)
        while q("SELECT tg_id FROM users WHERE ref_code=?", (code,), one=True):
            code = "r" + secrets.token_hex(3)
        ex(
            "INSERT INTO users(tg_id,username,ref_code,joined_at) "
            "VALUES(?,?,?,?)",
            (tg_id, username or "", code, now_ms()),
        )
        u = q("SELECT * FROM users WHERE tg_id=?", (tg_id,), one=True)
    elif username and username != (u.get("username") or ""):
        ex("UPDATE users SET username=? WHERE tg_id=?", (username, tg_id))
        u["username"] = username
    return u


def balance_add(tg_id: int, amount: int, kind: str, note: str = ""):
    """افزایش یا کاهش موجودی + ثبت تراکنش"""
    with _lock:
        c = connect()
        c.execute(
            "UPDATE users SET balance = balance + ? WHERE tg_id=?",
            (amount, tg_id),
        )
        c.execute(
            "INSERT INTO transactions(user_id,kind,amount,note,ts) "
            "VALUES(?,?,?,?,?)",
            (tg_id, kind, amount, note, now_ms()),
        )
        c.commit()


def balance_deduct_safe(tg_id: int, amount: int, kind: str, note: str = "") -> bool:
    """
    کسر امن موجودی.
    فقط اگر موجودی کافی باشد کم می‌کند و True برمی‌گرداند.
    از Race Condition جلوگیری می‌کند.
    """
    if amount <= 0:
        return True
    with _lock:
        c = connect()
        cur = c.execute(
            "UPDATE users SET balance = balance - ? "
            "WHERE tg_id=? AND balance >= ?",
            (amount, tg_id, amount),
        )
        if cur.rowcount == 0:
            return False
        c.execute(
            "INSERT INTO transactions(user_id,kind,amount,note,ts) "
            "VALUES(?,?,?,?,?)",
            (tg_id, kind, -amount, note, now_ms()),
        )
        c.commit()
        return True


def owner_and_admins():
    """اولین آیدی tg_admins پنل = Owner · بقیه = Admin"""
    from core import database as panel_db
    ids = []
    for part in (panel_db.get_setting("tg_admins") or "").split(","):
        p = part.strip()
        if p.lstrip("-").isdigit():
            ids.append(int(p))
    if not ids:
        return 0, []
    return ids[0], ids[1:]


def log_admin(admin_id: int, action: str, detail: str = ""):
    ex(
        "INSERT INTO admin_log(admin_id,action,detail,ts) VALUES(?,?,?,?)",
        (admin_id, action, detail[:300], now_ms()),
    )


# ---------------- کد تخفیف ----------------

def check_coupon(code: str, amount: int, tg_id: int):
    """→ (خطا | None, مبلغ تخفیف)"""
    c = q(
        "SELECT * FROM coupons WHERE code=? AND is_active=1",
        (code.strip().upper(),),
        one=True,
    )
    if not c:
        # جستجو بدون upper هم امتحان شود
        c = q(
            "SELECT * FROM coupons WHERE code=? AND is_active=1",
            (code.strip(),),
            one=True,
        )
    if not c:
        return "کد تخفیف یافت نشد یا غیرفعال است.", 0
    if c["expires_at"] and c["expires_at"] < now_ms():
        return "این کد تخفیف منقضی شده است.", 0
    if c["max_uses"] and c["used"] >= c["max_uses"]:
        return "سقف استفاده از این کد پر شده است.", 0
    if c["min_amount"] and amount < c["min_amount"]:
        return f"این کد برای خریدهای بالای {c['min_amount']:,} تومان است.", 0
    if q(
        "SELECT coupon_id FROM coupon_uses WHERE coupon_id=? AND user_id=?",
        (c["id"], tg_id),
        one=True,
    ):
        return "شما قبلاً از این کد استفاده کرده‌اید.", 0

    discount = (
        amount * c["value"] // 100
        if c["kind"] == "percent"
        else c["value"]
    )
    discount = min(discount, amount)
    return None, discount


def coupon_commit(code: str, tg_id: int):
    c = q(
        "SELECT id FROM coupons WHERE code=? OR code=?",
        (code.strip(), code.strip().upper()),
        one=True,
    )
    if not c:
        return
    with _lock:
        conn = connect()
        conn.execute(
            "UPDATE coupons SET used = used + 1 WHERE id=?", (c["id"],)
        )
        conn.execute(
            "INSERT OR IGNORE INTO coupon_uses(coupon_id,user_id) VALUES(?,?)",
            (c["id"], tg_id),
        )
        conn.commit()
