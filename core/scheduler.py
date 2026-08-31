# -*- coding: utf-8 -*-
"""زمان‌بند پس‌زمینه — آمار Xray، محدودیت‌ها، اعلان تلگرام،
ریست دوره‌ای (روزانه/ماهانه) و پاکسازی داده‌های قدیمی."""

import threading
import time
from collections import deque
from datetime import datetime, timezone

from . import config as cfg
from . import database as db
from .utils import now_ms, fmt_bytes, fmt_duration
from .xray import xray

SERIES = deque(maxlen=360)   # (timestamp, up_bytes, down_bytes)
_prune_at = 0.0


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _tg_notify(chat_id: str, text: str) -> None:
    if not chat_id:
        return
    try:
        from telegram.bot import send_message   # ایمپورت تنبل — بخش ۴
        send_message(chat_id, text)
    except Exception:
        pass


def stats_loop() -> None:
    time.sleep(4)  # فرصت بالا آمدن هسته
    while True:
        time.sleep(max(2, cfg.STATS_INTERVAL))
        try:
            _collect()
            _enforce_limits()
            _period_reset()
            _maybe_prune()
        except Exception as e:
            db.log_event(f"scheduler: {e}", "err")


# ---------------- جمع‌آوری آمار ----------------

def _collect() -> None:
    if not xray.alive():
        SERIES.append((int(time.time()), 0, 0))
        return
    try:
        users = xray.stats.query("user>>>", reset=True) or {}
        inbs = xray.stats.query("inbound>>>", reset=True) or {}
    except Exception:
        SERIES.append((int(time.time()), 0, 0))
        return

    per_user = {}
    for name, val in users.items():
        parts = name.split(">>>")
        if len(parts) != 4 or parts[0] != "user":
            continue
        d = per_user.setdefault(parts[1], {"up": 0, "down": 0})
        if parts[3] == "uplink":
            d["up"] += val
        elif parts[3] == "downlink":
            d["down"] += val

    now = now_ms()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_up = total_down = 0

    for email, d in per_user.items():
        if not (d["up"] or d["down"]):
            continue
        db.ex("UPDATE clients SET up=up+?, down=down+?, last_seen=? "
              "WHERE email=?", (d["up"], d["down"], now, email))
        db.ex("INSERT INTO daily_clients(day,email,up,down) VALUES(?,?,?,?) "
              "ON CONFLICT(day,email) DO UPDATE SET up=up+?, down=down+?",
              (day, email, d["up"], d["down"], d["up"], d["down"]))
        total_up += d["up"]
        total_down += d["down"]

    for name, val in inbs.items():
        parts = name.split(">>>")
        if len(parts) == 4 and parts[1].startswith("ib"):
            try:
                iid = int(parts[1][2:])
            except ValueError:
                continue
            col = "up_total" if parts[3] == "uplink" else "down_total"
            db.ex(f"UPDATE inbounds SET {col}={col}+? WHERE id=?",
                  (val, iid))

    db.ex("INSERT INTO daily_totals(day,up,down) VALUES(?,?,?) "
          "ON CONFLICT(day) DO UPDATE SET up=up+?, down=down+?",
          (day, total_up, total_down, total_up, total_down))

    SERIES.append((int(time.time()), total_up, total_down))


# ---------------- محدودیت‌ها و اعلان‌ها ----------------

def _enforce_limits() -> None:
    now = now_ms()
    changed = False
    notes = []

    for c in db.q("SELECT * FROM clients WHERE enable=1"):
        used = c["up"] + c["down"]
        lim, exp, email = c["limit_bytes"], c["expiry"], c["email"]

        if lim and used >= lim:
            db.ex("UPDATE clients SET enable=0 WHERE id=?", (c["id"],))
            changed = True
            db.log_event(f"کاربر «{email}» غیرفعال شد — اتمام حجم", "warn")
            notes.append((c["tg_id"],
                          f"❌ <b>{_esc(email)}</b>\nحجم کانفیگ شما تمام شد "
                          f"و غیرفعال شد.\n📊 مصرف: {fmt_bytes(used)} از "
                          f"{fmt_bytes(lim)}"))
            continue

        if exp and exp <= now:
            db.ex("UPDATE clients SET enable=0 WHERE id=?", (c["id"],))
            changed = True
            db.log_event(f"کاربر «{email}» غیرفعال شد — اتمام اعتبار", "warn")
            notes.append((c["tg_id"],
                          f"❌ <b>{_esc(email)}</b>\nاعتبار کانفیگ شما "
                          f"به پایان رسید."))
            continue

        if lim and not c["notify80"] and used >= lim * 0.8:
            db.ex("UPDATE clients SET notify80=1 WHERE id=?", (c["id"],))
            notes.append((c["tg_id"],
                          f"⚠️ <b>{_esc(email)}</b>\n۸۰٪ حجم مصرف شد.\n📊 "
                          f"{fmt_bytes(used)} از {fmt_bytes(lim)}"))

        if exp and not c["notify_exp"] and 0 < exp - now < 86_400_000:
            db.ex("UPDATE clients SET notify_exp=1 WHERE id=?", (c["id"],))
            notes.append((c["tg_id"],
                          f"⏳ <b>{_esc(email)}</b>\nکانفیگ شما در "
                          f"{fmt_duration((exp - now) // 1000)} آینده "
                          f"منقضی می‌شود."))

    if notes and db.get_bool("tg_notify", True):
        for chat_id, text in notes:
            _tg_notify(chat_id, text)

    if changed:
        try:
            xray.restart("اعمال محدودیت‌ها")
        except Exception as e:
            db.log_event(f"اعمال محدودیت‌ها: {e}", "err")


# ---------------- ریست دوره‌ای ----------------

def _period_reset() -> None:
    mode = (db.get_setting("reset_mode") or "off").strip().lower()
    if mode not in ("daily", "monthly"):
        return
    now = time.localtime()
    if mode == "daily":
        key = time.strftime("%Y-%m-%d", now)
    else:
        day = db.get_int("reset_day", 1)
        y, m, d = now.tm_year, now.tm_mon, now.tm_mday
        if d >= day:
            key = f"{y}-{m:02d}"
        else:
            pm = m - 1 or 12
            py = y - 1 if m == 1 else y
            key = f"{py}-{pm:02d}"

    if (db.get_setting("last_reset_key") or "") == key:
        return
    db.set_setting("last_reset_key", key)
    db.ex("UPDATE clients SET up=0, down=0, notify80=0, notify_exp=0")
    n = db.q("SELECT COUNT(*) AS n FROM clients", one=True)["n"]
    db.log_event(f"ریست دوره‌ای ({'روزانه' if mode == 'daily' else 'ماهانه'})"
                 f" — {n} کاربر", "info")


# ---------------- پاکسازی ----------------

def _maybe_prune() -> None:
    global _prune_at
    if time.time() - _prune_at < 3600:
        return
    _prune_at = time.time()
    try:
        db.prune_events()
        db.prune_daily()
    except Exception:
        pass


def start() -> threading.Thread:
    t = threading.Thread(target=stats_loop, name="sf-scheduler",
                         daemon=True)
    t.start()
    return t