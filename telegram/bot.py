#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SF-Shop Bot — هسته ربات فروش (v1 — بخش ۳ از ۶)
جایگزین کامل bot.py قبلی. وابستگی‌های بخش‌های ۴ و ۵ اختیاری است —
اگر ماژول‌ها نبودند، ربات با پیام مناسب کار می‌کند (نه کرش).

نقش‌ها (از تنظیمات پنل): اولین آیدی tg_admins = Owner · بقیه = Admin
"""

import re
import threading
import time
import traceback

import requests

from core import config as cfg
from core import database as db            # دیتابیس پنل
from core.utils import fmt_bytes, fmt_duration, load_json
from core.link_builder import client_links, resolve_public_host

from . import db as sdb                    # دیتابیس فروش (shop.db)
from . import texts
from . import panel_link

API_TIMEOUT = 35
MSG_MAX = 4000
BIND_CODE_RE = re.compile(r"^[A-Za-z0-9_\-]{6,64}$")
TOKEN_RE = re.compile(r"^\d+:[\w\-]{30,}$$")
START_TS = time.time()

# حالت‌های گفتگو (FSM ساده)
_states = {}   # tg_id → dict(step="...", data={...})


# ================================================== ابزار

def now_ms() -> int:
    return int(time.time() * 1000)


def esc(s) -> str:
    return (str(s or "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def base_url() -> str:
    raw = (db.get_setting("public_domain") or "").strip()
    if raw:
        if raw.startswith(("http://", "https://")):
            return raw.rstrip("/")
        scheme = "https" if cfg.PAAS else "http"
        return f"{scheme}://{raw.strip('/')}"
    scheme = "https" if cfg.PAAS else "http"
    return f"{scheme}://{resolve_public_host()}"


# ================================================== ارسال

def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    if not chat_id or not text:
        return
    token = db.get_setting("tg_token")
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    parts = [text[i:i + MSG_MAX] for i in range(0, len(text), MSG_MAX)]
    try:
        for i, part in enumerate(parts):
            payload = {
                "chat_id": chat_id, "text": part,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            if reply_markup and i == len(parts) - 1:
                payload["reply_markup"] = reply_markup
            r = requests.post(url, json=payload, timeout=API_TIMEOUT)
            if r.status_code == 400 and parse_mode:
                payload.pop("parse_mode", None)
                payload.pop("reply_markup", None)
                requests.post(url, json=payload, timeout=API_TIMEOUT)
    except Exception as e:
        db.log_event(f"tg send: {e}", "err")


def answer_cbq(cbq_id, text=""):
    token = db.get_setting("tg_token")
    if not token or not cbq_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json={"callback_query_id": cbq_id, "text": text[:200]},
            timeout=10)
    except Exception:
        pass


def edit_message(chat_id, message_id, text, reply_markup=None):
    token = db.get_setting("tg_token")
    if not token:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/editMessageText",
            json={"chat_id": chat_id, "message_id": message_id,
                  "text": text[:MSG_MAX], "parse_mode": "HTML",
                  "disable_web_page_preview": True,
                  **({"reply_markup": reply_markup} if reply_markup else {})},
            timeout=API_TIMEOUT)
    except Exception:
        pass


def forward_photo_or_file(chat_id, from_chat_id, message_id):
    token = db.get_setting("tg_token")
    if not token:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/forwardMessage",
            json={"chat_id": chat_id, "from_chat_id": from_chat_id,
                  "message_id": message_id},
            timeout=API_TIMEOUT)
    except Exception:
        pass


# ================================================== نقش‌ها

def get_role(tg_id: int) -> str:
    """owner | admin | user"""
    owner, admins = sdb.owner_and_admins()
    if tg_id == owner:
        return "owner"
    if tg_id in admins:
        return "admin"
    return "user"


def _admins_all():
    owner, admins = sdb.owner_and_admins()
    return [owner] + admins


# ================================================== کیبوردها

def main_kb(role="user"):
    rows = [
        [{"text": "🛒 خرید اشتراک", "callback_data": "shop"},
         {"text": "📋 اشتراک‌های من", "callback_data": "mysubs"}],
        [{"text": "👤 پروفایل", "callback_data": "profile"},
         {"text": "💰 کیف پول", "callback_data": "wallet"}],
        [{"text": "🎁 اکانت تست", "callback_data": "trial"},
         {"text": "🤝 کسب درآمد", "callback_data": "referral"}],
        [{"text": "🏪 نمایندگی", "callback_data": "agent"},
         {"text": "💬 پشتیبانی", "callback_data": "support"}],
    ]
    return {"inline_keyboard": rows}


def back_kb():
    return {"inline_keyboard": [[
        {"text": "🔙 بازگشت به منو", "callback_data": "menu"}]]}


# ================================================== دستورات

def cmd_start(chat, args):
    u = sdb.ensure_user(chat, args[1] if args and len(args) > 0 else "")
    if u["is_blocked"]:
        send_message(chat, texts.T["blocked"])
        return
    _states.pop(chat, None)

    # ریفرال: /start rXXXX
    if args:
        code = args[0].strip()
        m = re.match(r"^r[0-9a-f]{6}$", code)
        if m and not u["ref_by"]:
            inviter = sdb.q("SELECT tg_id FROM users WHERE ref_code=?",
                            (code,), one=True)
            if inviter and inviter["tg_id"] != chat:
                sdb.ex("UPDATE users SET ref_by=? WHERE tg_id=?",
                       (inviter["tg_id"], chat))

    title = sdb.get_setting("shop_title", "SF VPN Shop")
    send_message(chat, texts.T["welcome"].format(
        title=esc(title), uid=chat), reply_markup=main_kb())


def cmd_help(chat, args):
    role = get_role(chat)
    lines = [
        "📖 <b>راهنما</b>",
        "",
        "🛒 خرید اشتراک از منوی اصلی",
        "💳 شارژ کیف پول با ارسال رسید",
        "🎁 اکانت تست رایگان",
        "🤝 دعوت دوستان = پاداش",
        "💬 /start → بازگشت به منو",
    ]
    if role in ("owner", "admin"):
        lines += ["", "👑 /panel → پنل مدیریت"]
    send_message(chat, "\n".join(lines))


# ================================================== بخش‌های اصلی

def cb_profile(chat):
    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (chat,), one=True)
    if not u:
        return
    refs = sdb.q("SELECT COUNT(*) n FROM users WHERE ref_by=?",
                 (chat,), one=True)["n"]
    bot_username = _bot_username()
    ref = (f"https://t.me/{bot_username}?start={u['ref_code']}"
           if bot_username else u["ref_code"])
    send_message(chat, texts.T["profile"].format(
        uid=chat, username=esc(u["username"] or "—"),
        balance=u["balance"], buys=u["buys_count"],
        joined=time.strftime("%Y-%m-%d",
                             time.localtime(u["joined_at"] / 1000)),
        ref=ref, refs=refs, earn=u["ref_earnings"]),
        reply_markup=back_kb())


def _bot_username():
    token = db.get_setting("tg_token")
    if not token:
        return ""
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe",
                         timeout=10).json()
        if r.get("ok"):
            return r["result"].get("username", "")
    except Exception:
        pass
    return ""


def cb_mysubs(chat):
    accs = sdb.q("SELECT * FROM bot_accounts WHERE user_id=? ORDER BY id DESC",
                 (chat,))
    if not accs:
        send_message(chat,
                     "هنوز اشتراکی نخریده‌ای. از «🛒 خرید اشتراک» شروع کن.",
                     reply_markup=main_kb())
        return
    base = base_url()
    items = []
    for a in accs:
        info = panel_link.account_info(a["sub_id"])
        if not info:
            continue
        used = info["used"]
        total = info["total"]
        if not info["enable"]:
            status = "⛔"
        elif info["expiry"] and info["expiry"] < now_ms():
            status = "❌ منقضی"
        else:
            status = "✅"
        exp = (time.strftime("%Y-%m-%d", time.localtime(info["expiry"] / 1000))
               if info["expiry"] else "∞")
        items.append(texts.T["sub_item"].format(
            email=esc(a["email"]), status=status,
            used=fmt_bytes(used), total=fmt_bytes(total) if total else "∞",
            expiry=exp, sub=f"{base}/sub/{a['sub_id']}"))
    send_message(chat, texts.T["my_subs"].format(
        list="\n".join(items)), reply_markup=back_kb())


# ================================================== Callback Router

def handle_callback(cbq):
    chat = str(cbq.get("message", {}).get("chat", {}).get("id", ""))
    data = cbq.get("data", "")
    cbq_id = str(cbq.get("id", ""))
    if not chat or not data:
        return
    if not data:
        return

    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (int(chat),), one=True)
    if u and u["is_blocked"]:
        answer_cbq(cbq_id, "⛔ مسدود")
        return
    _states.pop(int(chat), None)   # کلیک روی دکمه = خروج از حالت FSM

    if data == "menu":
        answer_cbq(cbq_id)
        cmd_start(chat, [])
    elif data == "profile":
        answer_cbq(cbq_id)
        cb_profile(chat)
    elif data == "mysubs":
        answer_cbq(cbq_id)
        cb_mysubs(chat)

    # ─── بخش ۴: فروش (اگر ماژول نصب بود) ───
    elif data in ("wallet", "deposit", "shop", "buy", "coupon",
                  "trial", "referral", "agent", "support"):
        try:
            from .handlers_shop import route_callback
            answer_cbq(cbq_id)
            route_callback(data, chat, cbq)
        except ImportError:
            answer_cbq(cbq_id, "این بخش هنوز نصب نشده (بخش ۴)")
        except Exception:
            answer_cbq(cbq_id, "خطا — /start")
            db.log_event(traceback.format_exc(limit=4), "err")

    # ─── بخش ۵: پنل ادمین ───
    elif data.startswith("adm:"):
        try:
            from .handlers_admin import route_callback
            route_callback(cbq, data)
        except ImportError:
            answer_cbq(cbq_id, "پنل ادمین هنوز نصب نشده (بخش ۵)")
        except Exception:
            answer_cbq(cbq_id, "خطا در پنل")
            db.log_event(traceback.format_exc(limit=4), "err")
    else:
        answer_cbq(cbq_id)


# ================================================== دستورات ادمین (قدیمی — حفظ شده)

def _xray():
    from core.xray import xray
    return xray


def cmd_status(chat, args):
    if get_role(chat) not in ("owner", "admin"):
        send_message(chat, "این دستور فقط برای مدیران است.")
        return
    xs = _xray().state()
    totals = db.q(
        "SELECT COALESCE(SUM(up),0) AS u, COALESCE(SUM(down),0) AS d, "
        "COUNT(*) AS n, COALESCE(SUM(enable),0) AS e FROM clients",
        one=True)
    day = time.strftime("%Y-%m-%d", time.gmtime())
    daily = db.q("SELECT * FROM daily_totals WHERE day=?", (day,), one=True) \
        or {"up": 0, "down": 0}
    send_message(chat, (
        f"🖥 <b>{esc(cfg.APP_NAME)}</b>\n"
        f"├ Xray: {'✅' if xs['running'] else '❌'} "
        f"{esc(xs['version'] or '—')}\n"
        f"├ کاربران پنل: {totals['n']} (فعال: {totals['e']})\n"
        f"├ مشتریان فروش: "
        f"{sdb.q('SELECT COUNT(*) n FROM users', one=True)['n']}\n"
        f"├ امروز: ↑{fmt_bytes(daily['up'])} ↓{fmt_bytes(daily['down'])}\n"
        f"└ کل: ↑{fmt_bytes(totals['u'])} ↓{fmt_bytes(totals['d'])}"))


def cmd_clients(chat, args):
    if get_role(chat) not in ("owner", "admin"):
        send_message(chat, "این دستور فقط برای مدیران است.")
        return
    rows = db.q("SELECT * FROM clients ORDER BY id DESC LIMIT 50")
    msg = "👥 <b>کاربران پنل</b> (۵۰ آخر)\n"
    for c in rows:
        used = c["up"] + c["down"]
        extra = f" ({int(used * 100 / c['limit_bytes'])}%)" if c["limit_bytes"] else ""
        msg += (f"\n#{c['id']} {esc(c['email'])} "
                f"{'✅' if c['enable'] else '⛔'} — {fmt_bytes(used)}{extra}")
    send_message(chat, msg)


def cmd_inbounds(chat, args):
    if get_role(chat) not in ("owner", "admin"):
        send_message(chat, "این دستور فقط برای مدیران است.")
        return
    rows = db.q("SELECT * FROM inbounds ORDER BY id")
    clients = db.q("SELECT inbounds FROM clients")
    msg = "📡 <b>اینباند‌ها</b>\n"
    for ib in rows:
        g = load_json(ib["config"], {})
        if cfg.PAAS:
            detail = f"wss://{esc(g.get('path', ''))}"
        else:
            detail = (f"پورت {g.get('port', '?')} • "
                      f"{g.get('transport', 'tcp')}/{g.get('security', 'none')}")
        cnt = sum(1 for c in clients
                  if ib["id"] in load_json(c["inbounds"], []))
        msg += (f"\n#{ib['id']} <b>{esc(ib['remark'])}</b> "
                f"[{ib['protocol'].upper()}] {detail} • {cnt} کاربر • "
                f"{'✅' if ib['enable'] else '❌'}")
    send_message(chat, msg)


def cmd_restart(chat, args):
    if get_role(chat) not in ("owner", "admin"):
        send_message(chat, "این دستور فقط برای مدیران است.")
        return
    send_message(chat, "⏳ در حال راه‌اندازی مجدد هسته ...")
    try:
        ok, err = _xray().restart("دستور تلگرام")
        send_message(chat, "✅ هسته Xray راه‌اندازی مجدد شد." if ok
                     else "❌ خطا:\n<code>" + esc(err[:600]) + "</code>")
    except Exception as e:
        send_message(chat, "❌ " + esc(str(e)))


def cmd_notify(chat, args):
    if get_role(chat) not in ("owner", "admin"):
        send_message(chat, "این دستور فقط برای مدیران است.")
        return
    text = " ".join(args).strip()
    if not text:
        send_message(chat, "❌ صحیح: <code>/notify متن پیام</code>")
        return
    rows = sdb.q("SELECT DISTINCT tg_id FROM users")
    n = 0
    for r in rows:
        send_message(r["tg_id"], f"📢 <b>پیام مدیر</b>\n\n{esc(text)}")
        n += 1
        time.sleep(0.05)
    send_message(chat, f"✅ به {n} کاربر ارسال شد.")


# ================================================== پیام‌های متنی (Router)

def route_message(chat: str, text: str):
    tg = int(chat)
    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    if u and u["is_blocked"]:
        send_message(chat, texts.T["blocked"])
        return

    low = text.split("@", 1)[0].lower()
    parts = text.split()

    # در حالت FSM؟ → به ماژول بخش ۴/۵ بده
    if tg in _states:
        try:
            from .handlers_fsm import route_fsm
            if route_fsm(tg, text, _states):
                return
        except ImportError:
            _states.pop(tg, None)
        except Exception:
            db.log_event(traceback.format_exc(limit=4), "err")
            _states.pop(tg, None)

    # کد bind خام (سازگاری با ربات قبلی)
    if len(parts) == 1 and BIND_CODE_RE.match(low):
        cmd_bind(chat, [low])
        return

    if not low.startswith("/"):
        send_message(chat, texts.T["start_help"])
        return

    cmd = low.split("@")[0]
    args = parts[1:]
    ROUTES = {
        "/start": cmd_start, "/help": cmd_help,
        "/status": cmd_status, "/clients": cmd_clients,
        "/inbounds": cmd_inbounds, "/restart": cmd_restart,
        "/notify": cmd_notify,
        "/panel": None,   # بخش ۵ — placeholder
    }
    handler = ROUTES.get(cmd)
    if handler:
        handler(chat, args)
    elif cmd == "/panel":
        try:
            from .handlers_admin import cmd_panel
            cmd_panel(chat)
        except ImportError:
            send_message(chat, "پنل ادمین هنوز نصب نشده (بخش ۵).")
        except Exception:
            db.log_event(traceback.format_exc(limit=4), "err")
    elif cmd == "/cancel":
        _states.pop(tg, None)
        send_message(chat, texts.T["cancelled"], reply_markup=main_kb())
    else:
        send_message(chat, "دستور ناشناخته. /help")


# ================================================== سازگاری با ربات قبلی (/bind)

def cmd_bind(chat, args):
    if not args:
        send_message(chat, "❌ صحیح: <code>/bind کد-اتصال</code>")
        return
    code = args[0].strip()
    c = db.q("SELECT * FROM clients WHERE sub_id=?", (code,), one=True)
    if not c:
        send_message(chat, "❌ کد اتصال معتبر نیست.")
        return
    if c["tg_id"] and c["tg_id"] != chat:
        send_message(chat, "❌ این کانفیگ به تلگرام دیگری متصل است.")
        return
    db.ex("UPDATE clients SET tg_id=? WHERE id=?", (chat, c["id"]))
    db.log_event(f"کاربر «{c['email']}» به تلگرام متصل شد", "ok")
    send_message(chat, f"✅ کانفیگ <b>{esc(c['email'])}</b> متصل شد!")


# ================================================== پولینگ

class BotPoller(threading.Thread):
    def __init__(self):
        super().__init__(name="sf-shop-poller", daemon=True)
        self.offset = 0
        self.last_token = ""

    def run(self):
        while True:
            try:
                token = db.get_setting("tg_token") or ""
                if not TOKEN_RE.match(token or ""):
                    time.sleep(8)
                    continue
                if token != self.last_token:
                    self.last_token = token
                    self.offset = 0
                    self._reset_webhook(token)
                    db.log_event("ربات فروش فعال شد", "ok")
                self._poll_loop(token)
            except Exception as e:
                db.log_event(f"tg poll: {e}", "err")
                time.sleep(10)

    @staticmethod
    def _reset_webhook(token):
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/deleteWebhook",
                json={"drop_pending_updates": True}, timeout=10)
        except Exception:
            pass

    def _poll_loop(self, token):
        base = f"https://api.telegram.org/bot{token}"
        while True:
            if (db.get_setting("tg_token") or "") != token:
                return
            try:
                r = requests.get(
                    base + "/getUpdates",
                    params={"timeout": 25, "offset": self.offset},
                    timeout=API_TIMEOUT).json()
            except (requests.RequestException, ValueError):
                time.sleep(5)
                continue
            if not r.get("ok"):
                db.log_event(f"tg getUpdates: {r.get('description', '')}",
                             "err")
                time.sleep(10)
                continue
            for upd in (r.get("result") or []):
                self.offset = max(self.offset,
                                  int(upd.get("update_id", 0)) + 1)
                try:
                    self._dispatch(upd)
                except Exception:
                    db.log_event(traceback.format_exc(limit=4), "err")

    def _dispatch(self, upd: dict):
        if "callback_query" in upd:
            handle_callback(upd["callback_query"])
            return
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        if chat and text:
            route_message(chat, text)
            return
        # عکس/فایل → رسید؟ (بخش ۴)
        if chat and (msg.get("photo") or msg.get("document")):
            try:
                from .handlers_fsm import handle_media
                handle_media(msg, chat)
            except ImportError:
                pass
            except Exception:
                db.log_event(traceback.format_exc(limit=4), "err")


_poller = None


def start_bot() -> BotPoller:
    """از app.py صدا زده می‌شود."""
    global _poller
    try:
        sdb.connect()   # ساخت shop.db
    except Exception as e:
        db.log_event(f"shop db: {e}", "err")
    if _poller is None or not _poller.is_alive():
        _poller = BotPoller()
        _poller.start()
    return _poller


# سازگاری: scheduler کهن send_message صدا می‌زند (همان تابع ما)
# send_message با امضای (chat_id, text) سازگار است. ✅
