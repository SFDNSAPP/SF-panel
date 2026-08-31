# -*- coding: utf-8 -*-
"""لایه دیتابیس — SQLite + WAL، thread-safe، با کش تنظیمات و پشتیبان‌گیری."""
import sqlite3
import threading
import time

from . import config as cfg
from .utils import now_ms

_lock = threading.RLock()
_conn: sqlite3.Connection = None
_cache: dict = {}

DEFAULTS = {
    "admin_user": "",
    "admin_pass": "",        # pbkdf2 hash
    "secret": "",            # کلید امضای توکن
    "totp_secret": "",
    "totp_enabled": "0",
    "tg_token": "",
    "tg_admins": "",         # chat id های ادمین با کاما
    "tg_notify": "1",
    "public_domain": "",
    "sub_title": "SF-Panel",
    "reset_mode": "off",     # off | daily | monthly
    "reset_day": "1",
    "xray_version": "",      # پین‌کردن نسخه هسته (اختیاری)
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS inbounds (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    remark        TEXT NOT NULL DEFAULT '',
    protocol      TEXT NOT NULL DEFAULT 'vless',
    config        TEXT NOT NULL DEFAULT '{}',
    enable        INTEGER NOT NULL DEFAULT 1,
    internal_port INTEGER NOT NULL DEFAULT 0,
    up_total      INTEGER NOT NULL DEFAULT 0,
    down_total    INTEGER NOT NULL DEFAULT 0,
    created_at    INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS clients (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT NOT NULL UNIQUE,
    uuid        TEXT NOT NULL DEFAULT '',
    password    TEXT NOT NULL DEFAULT '',
    flow        TEXT NOT NULL DEFAULT '',
    inbounds    TEXT NOT NULL DEFAULT '[]',
    expiry      INTEGER NOT NULL DEFAULT 0,
    limit_bytes INTEGER NOT NULL DEFAULT 0,
    up          INTEGER NOT NULL DEFAULT 0,
    down        INTEGER NOT NULL DEFAULT 0,
    enable      INTEGER NOT NULL DEFAULT 1,
    tg_id       TEXT NOT NULL DEFAULT '',
    sub_id      TEXT NOT NULL UNIQUE,
    note        TEXT NOT NULL DEFAULT '',
    notify80    INTEGER NOT NULL DEFAULT 0,
    notify_exp  INTEGER NOT NULL DEFAULT 0,
    last_seen   INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS daily_totals (
    day  TEXT PRIMARY KEY,
    up   INTEGER NOT NULL DEFAULT 0,
    down INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS daily_clients (
    day   TEXT NOT NULL,
    email TEXT NOT NULL,
    up    INTEGER NOT NULL DEFAULT 0,
    down  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, email)
);
CREATE TABLE IF NOT EXISTS events (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts    INTEGER NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
    msg   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_clients_tg    ON clients(tg_id);
CREATE INDEX IF NOT EXISTS idx_daily_clients ON daily_clients(day);
CREATE INDEX IF NOT EXISTS idx_events_ts     ON events(ts);
"""


def connect() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is not None:
            return _conn
        cfg.ensure_dirs()
        _conn = sqlite3.connect(cfg.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute("PRAGMA busy_timeout=5000")
        _conn.executescript(SCHEMA)
        _conn.commit()
        if not get_setting("secret"):
            import secrets
            set_setting("secret", secrets.token_hex(32))
        return _conn


def q(sql: str, args=(), one=False):
    with _lock:
        cur = connect().execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
    return (rows[0] if rows else None) if one else rows


def ex(sql: str, args=()) -> int:
    with _lock:
        c = connect()
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid


def next_internal_port() -> int:
    used = {cfg.PUBLIC_PORT, cfg.PANEL_INTERNAL_PORT, cfg.XRAY_API_PORT}
    for r in q("SELECT internal_port FROM inbounds"):
        used.add(r["internal_port"])
    p = cfg.INTERNAL_PORT_START
    while p <= cfg.INTERNAL_PORT_END and p in used:
        p += 1
    return p


# ---------------- تنظیمات ----------------

def get_setting(key: str, default=None):
    with _lock:
        if key in _cache:
            return _cache[key]
        row = connect().execute("SELECT v FROM settings WHERE k=?", (key,)).fetchone()
        val = row["v"] if row else None
        if val is None or val == "":
            val = DEFAULTS.get(key, "" if default is None else default)
        _cache[key] = val
        return val


def set_setting(key: str, value) -> None:
    with _lock:
        connect().execute(
            "INSERT INTO settings(k,v) VALUES(?,?) "
            "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, str(value)))
        connect().commit()
        _cache[key] = str(value)


def get_bool(key: str, default=False) -> bool:
    v = get_setting(key, "1" if default else "0")
    return str(v).lower() in ("1", "true", "yes", "on")


def get_int(key: str, default=0) -> int:
    try:
        return int(get_setting(key, default))
    except (TypeError, ValueError):
        return default


def all_settings() -> dict:
    return {r["k"]: r["v"] for r in q("SELECT k,v FROM settings")}


# ---------------- رویدادها ----------------

def log_event(msg: str, level: str = "info") -> None:
    ex("INSERT INTO events(ts,level,msg) VALUES(?,?,?)", (now_ms(), level, str(msg)[:500]))
    print(f"[SF-Panel][{level}] {msg}", flush=True)


def prune_events() -> None:
    ex("DELETE FROM events WHERE id NOT IN "
       "(SELECT id FROM events ORDER BY id DESC LIMIT ?)", (cfg.MAX_EVENT_ROWS,))


def prune_daily(keep_days: int = 90) -> None:
    cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - keep_days * 86400))
    ex("DELETE FROM daily_clients WHERE day < ?", (cutoff,))
    ex("DELETE FROM daily_totals WHERE day < ?", (cutoff,))


# ---------------- پشتیبان‌گیری / بازیابی ----------------

_CLIENT_COLS = ["id", "email", "uuid", "password", "flow", "inbounds", "expiry",
                "limit_bytes", "up", "down", "enable", "tg_id", "sub_id", "note",
                "notify80", "notify_exp", "last_seen", "created_at"]
_INBOUND_COLS = ["id", "remark", "protocol", "config", "enable",
                 "internal_port", "up_total", "down_total", "created_at"]
_RESTORABLE_SETTINGS = ["admin_user", "admin_pass", "totp_secret", "totp_enabled",
                        "tg_token", "tg_admins", "tg_notify", "public_domain",
                        "sub_title", "reset_mode", "reset_day"]


def export_all() -> dict:
    return {
        "app": cfg.APP_NAME,
        "version": cfg.APP_VERSION,
        "exported_at": now_ms(),
        "settings": {k: v for k, v in all_settings().items()
                     if k not in ("secret",)},
        "inbounds": q("SELECT * FROM inbounds ORDER BY id"),
        "clients": q("SELECT * FROM clients ORDER BY id"),
        "daily_totals": q("SELECT * FROM daily_totals"),
    }


def import_all(data: dict) -> dict:
    """بازیابی کامل؛ IDs حفظ می‌شوند. خروجی: تعداد رکوردها."""
    if not isinstance(data, dict) or "inbounds" not in data or "clients" not in data:
        raise ValueError("ساختار فایل پشتیبان معتبر نیست")
    with _lock:
        c = connect()
        try:
            c.execute("BEGIN")
            c.execute("DELETE FROM inbounds")
            c.execute("DELETE FROM clients")
            c.execute("DELETE FROM daily_totals")
            c.execute("DELETE FROM daily_clients")
            for row in data.get("inbounds", []):
                vals = {k: row.get(k) for k in _INBOUND_COLS}
                c.execute(
                    f"INSERT OR REPLACE INTO inbounds({','.join(_INBOUND_COLS)}) "
                    f"VALUES({','.join(':' + k for k in _INBOUND_COLS)})", vals)
            for row in data.get("clients", []):
                vals = {k: row.get(k) for k in _CLIENT_COLS}
                c.execute(
                    f"INSERT OR REPLACE INTO clients({','.join(_CLIENT_COLS)}) "
                    f"VALUES({','.join(':' + k for k in _CLIENT_COLS)})", vals)
            for row in data.get("daily_totals", []):
                c.execute("INSERT OR REPLACE INTO daily_totals(day,up,down) VALUES(?,?,?)",
                          (row.get("day"), row.get("up", 0), row.get("down", 0)))
            saved = data.get("settings") or {}
            for k in _RESTORABLE_SETTINGS:
                if k in saved:
                    c.execute("INSERT OR REPLACE INTO settings(k,v) VALUES(?,?)",
                              (k, str(saved[k])))
                    _cache.pop(k, None)
            c.commit()
            return {"inbounds": len(data.get("inbounds", [])),
                    "clients": len(data.get("clients", []))}
        except Exception:
            c.rollback()
            raise