#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SF-Shop Bot — نسخه اصلاح‌شده و پایدار
- رفع باگ کوپن
- پرداخت atomic
- ذخیره صحیح tg_id
- مدیریت بهتر state و خطاها
"""

import re
import threading
import time
import traceback

import requests

from core import config as cfg
from core import database as db
from core.utils import fmt_bytes, load_json
from core.link_builder import resolve_public_host

from . import db as sdb
from . import texts
from . import panel_link

API_TIMEOUT = 35
MSG_MAX = 4000
BIND_CODE_RE = re.compile(r"^[A-Za-z0-9_\-]{6,64}$")
TOKEN_RE = re.compile(r"^\d+:[\w\-]{30,}$")

# state کاربران: {tg_id: {"step": str, "data": dict}}
_states = {}
_states_lock = threading.RLock()


def now_ms() -> int:
    return int(time.time() * 1000)


def esc(s) -> str:
    return texts.esc(s)


def base_url() -> str:
    raw = (db.get_setting("public_domain") or "").strip()
    if raw:
        if raw.startswith(("http://", "https://")):
            return raw.rstrip("/")
        scheme = "https" if cfg.PAAS else "http"
        return f"{scheme}://{raw.strip('/')}"
    scheme = "https" if cfg.PAAS else "http"
    return f"{scheme}://{resolve_public_host()}"


# ================================================== ارسال پیام

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
                "chat_id": chat_id,
                "text": part,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            if reply_markup and i == len(parts) - 1:
                payload["reply_markup"] = reply_markup
            r = requests.post(url, json=payload, timeout=API_TIMEOUT)
            if r.status_code == 400 and parse_mode:
                payload.pop("parse_mode", None)
                if "reply_markup" in payload:
                    # اگر HTML مشکل داشت، markup را نگه می‌داریم
                    pass
                requests.post(url, json=payload, timeout=API_TIMEOUT)
    except Exception as e:
        db.log_event(f"tg send: {e}", "err")


def answer_cbq(cbq_id, text="", show_alert=False):
    token = db.get_setting("tg_token")
    if not token or not cbq_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json={
                "callback_query_id": cbq_id,
                "text": (text or "")[:200],
                "show_alert": show_alert,
            },
            timeout=10,
        )
    except Exception:
        pass


def forward_photo_or_file(chat_id, from_chat_id, message_id):
    token = db.get_setting("tg_token")
    if not token:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/forwardMessage",
            json={
                "chat_id": chat_id,
                "from_chat_id": from_chat_id,
                "message_id": message_id,
            },
            timeout=API_TIMEOUT,
        )
    except Exception:
        pass


# ================================================== نقش‌ها

def get_role(tg_id: int) -> str:
    owner, admins = sdb.owner_and_admins()
    if tg_id == owner:
        return "owner"
    if tg_id in admins:
        return "admin"
    return "user"


def _admins_all():
    owner, admins = sdb.owner_and_admins()
    result = []
    if owner:
        result.append(owner)
    result.extend(admins)
    return result


def _bot_username():
    token = db.get_setting("tg_token")
    if not token:
        return ""
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getMe", timeout=10
        ).json()
        if r.get("ok"):
            return r["result"].get("username", "")
    except Exception:
        pass
    return ""


# ================================================== کیبوردها

def main_kb(role="user"):
    return {
        "inline_keyboard": [
            [
                {"text": "🛒 خرید اشتراک", "callback_data": "shop"},
                {"text": "📋 اشتراک‌های من", "callback_data": "mysubs"},
            ],
            [
                {"text": "👤 پروفایل", "callback_data": "profile"},
                {"text": "💰 کیف پول", "callback_data": "wallet"},
            ],
            [
                {"text": "🎁 اکانت تست", "callback_data": "trial"},
                {"text": "🤝 کسب درآمد", "callback_data": "referral"},
            ],
            [
                {"text": "🏪 نمایندگی", "callback_data": "agent"},
                {"text": "💬 پشتیبانی", "callback_data": "support"},
            ],
        ]
    }


def back_kb():
    return {
        "inline_keyboard": [
            [{"text": "🔙 بازگشت به منو", "callback_data": "menu"}]
        ]
    }


# ================================================== دستورات اصلی

def _extract_ref_code(args) -> str:
    """استخراج کد ریفرال از آرگومان‌های /start"""
    if not args:
        return ""
    raw = str(args[0] or "").strip()
    # حالت‌های مختلف: r1a2b3c | start=r1a2b3c | =r1a2b3c
    if "=" in raw:
        raw = raw.split("=", 1)[-1].strip()
    raw = raw.strip().lstrip("/")
    # فقط کدهای معتبر shop: r + 6 hex
    if re.match(r"^r[0-9a-fA-F]{6}$", raw):
        return raw.lower()
    return ""


def cmd_start(chat, args=None, username=""):
    tg = int(chat)
    args = args or []
    try:
        with _states_lock:
            _states.pop(tg, None)
    except Exception:
        _states.pop(tg, None)

    u = sdb.ensure_user(tg, username)
    if u.get("is_blocked"):
        send_message(chat, texts.T["blocked"])
        return

    # ریفرال — فقط بار اول
    code = _extract_ref_code(args)
    if code and not u.get("ref_by"):
        inviter = sdb.q(
            "SELECT tg_id FROM users WHERE ref_code=?", (code,), one=True
        )
        if inviter and inviter["tg_id"] != tg:
            sdb.ex(
                "UPDATE users SET ref_by=? WHERE tg_id=?",
                (inviter["tg_id"], tg),
            )
            try:
                send_message(
                    inviter["tg_id"],
                    f"🎉 یک نفر با لینک دعوت تو وارد ربات شد!",
                )
            except Exception:
                pass

    title = sdb.get_setting("shop_title", "SF VPN Shop")
    send_message(
        chat,
        texts.T["welcome"].format(title=esc(title), uid=chat),
        reply_markup=main_kb(),
    )


def cmd_help(chat, args):
    role = get_role(int(chat))
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


def cmd_bind(chat, args):
    if not args:
        send_message(chat, "❌ صحیح: <code>/bind کد-اتصال</code>")
        return
    c = db.q(
        "SELECT * FROM clients WHERE sub_id=?", (args[0].strip(),), one=True
    )
    if not c:
        send_message(chat, "❌ کد اتصال معتبر نیست.")
        return
    if c.get("tg_id") and str(c["tg_id"]) != str(chat):
        send_message(chat, "❌ این کانفیگ به تلگرام دیگری متصل است.")
        return
    db.ex("UPDATE clients SET tg_id=? WHERE id=?", (chat, c["id"]))
    send_message(chat, f"✅ کانفیگ <b>{esc(c['email'])}</b> متصل شد!")


# ================================================== پروفایل و اشتراک‌ها

def cb_profile(chat):
    tg = int(chat)
    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    if not u:
        return
    refs = sdb.q(
        "SELECT COUNT(*) n FROM users WHERE ref_by=?", (tg,), one=True
    )["n"]
    bu = _bot_username()
    ref = (
        f"https://t.me/{bu}?start={u['ref_code']}"
        if bu
        else u["ref_code"]
    )
    send_message(
        chat,
        texts.T["profile"].format(
            uid=tg,
            username=esc(u.get("username") or "—"),
            balance=u.get("balance") or 0,
            buys=u.get("buys_count") or 0,
            joined=time.strftime(
                "%Y-%m-%d", time.localtime((u.get("joined_at") or 0) / 1000)
            ),
            ref=ref,
            refs=refs,
            earn=u.get("ref_earnings") or 0,
        ),
        reply_markup=back_kb(),
    )


def cb_mysubs(chat):
    tg = int(chat)
    accs = sdb.q(
        "SELECT * FROM bot_accounts WHERE user_id=? ORDER BY id DESC", (tg,)
    )
    if not accs:
        send_message(
            chat,
            "هنوز اشتراکی نخریده‌ای. از «🛒 خرید اشتراک» شروع کن.",
            reply_markup=main_kb(),
        )
        return

    base = base_url()
    items = []
    for a in accs:
        info = panel_link.account_info(a["sub_id"])
        if not info:
            # حتی اگر پنل اطلاعات نداد، حداقل ایمیل و لینک را نشان بده
            items.append(
                texts.T["sub_item"].format(
                    email=esc(a.get("email") or "?"),
                    status="❓",
                    used="—",
                    total="—",
                    expiry="—",
                    sub=f"{base}/sub/{a['sub_id']}",
                )
            )
            continue

        status = (
            "⛔"
            if not info["enable"]
            else (
                "❌ منقضی"
                if info["expiry"] and info["expiry"] < now_ms()
                else "✅"
            )
        )
        exp = (
            time.strftime(
                "%Y-%m-%d", time.localtime(info["expiry"] / 1000)
            )
            if info["expiry"]
            else "∞"
        )
        items.append(
            texts.T["sub_item"].format(
                email=esc(a.get("email") or info.get("email") or "?"),
                status=status,
                used=fmt_bytes(info["used"]),
                total=fmt_bytes(info["total"]) if info["total"] else "∞",
                expiry=exp,
                sub=f"{base}/sub/{a['sub_id']}",
            )
        )

    send_message(
        chat,
        texts.T["my_subs"].format(list="\n".join(items)),
        reply_markup=back_kb(),
    )


# ================================================== Callback Router

def handle_callback(cbq):
    chat = str(cbq.get("message", {}).get("chat", {}).get("id", ""))
    data = cbq.get("data", "")
    cbq_id = str(cbq.get("id", ""))
    if not chat or not data:
        return

    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (int(chat),), one=True)
    if u and u.get("is_blocked"):
        answer_cbq(cbq_id, "⛔ مسدود")
        return

    try:
        if data == "menu":
            answer_cbq(cbq_id)
            cmd_start(chat, [])
            return

        if data == "profile":
            answer_cbq(cbq_id)
            cb_profile(chat)
            return

        if data == "mysubs":
            answer_cbq(cbq_id)
            cb_mysubs(chat)
            return

        if data in (
            "wallet",
            "deposit",
            "shop",
            "trial",
            "referral",
            "agent",
            "support",
        ) or data.startswith("shop:") or data.startswith("trial:"):
            from .handlers_shop import route_callback

            answer_cbq(cbq_id)
            route_callback(data, chat, cbq)
            return

        if data.startswith("adm:"):
            from .handlers_admin import route_callback

            route_callback(cbq, data)
            return

        answer_cbq(cbq_id)
    except Exception:
        answer_cbq(cbq_id, "خطا — /start")
        db.log_event(traceback.format_exc(limit=6), "err")


# ================================================== دستورات ادمین قدیمی (سازگاری)

def _xray():
    from core.xray import xray
    return xray


def _require_admin(chat):
    if get_role(int(chat)) not in ("owner", "admin"):
        send_message(chat, "این دستور فقط برای مدیران است.")
        return False
    return True


def cmd_status(chat, args):
    if not _require_admin(chat):
        return
    xs = _xray().state()
    totals = db.q(
        "SELECT COALESCE(SUM(up),0) u, COALESCE(SUM(down),0) d, "
        "COUNT(*) n, COALESCE(SUM(enable),0) e FROM clients",
        one=True,
    )
    day = time.strftime("%Y-%m-%d", time.gmtime())
    daily = db.q(
        "SELECT * FROM daily_totals WHERE day=?", (day,), one=True
    ) or {"up": 0, "down": 0}
    send_message(
        chat,
        (
            f"🖥 <b>{esc(cfg.APP_NAME)}</b>\n"
            f"├ Xray: {'✅' if xs.get('running') else '❌'} "
            f"{esc(xs.get('version') or '—')}\n"
            f"├ کاربران پنل: {totals['n']} (فعال: {totals['e']})\n"
            f"├ مشتریان فروش: "
            f"{sdb.q('SELECT COUNT(*) n FROM users', one=True)['n']}\n"
            f"├ امروز: ↑{fmt_bytes(daily['up'])} ↓{fmt_bytes(daily['down'])}\n"
            f"└ کل: ↑{fmt_bytes(totals['u'])} ↓{fmt_bytes(totals['d'])}"
        ),
    )


def cmd_clients(chat, args):
    if not _require_admin(chat):
        return
    msg = "👥 <b>کاربران پنل</b> (۵۰ آخر)\n"
    for c in db.q("SELECT * FROM clients ORDER BY id DESC LIMIT 50"):
        used = (c.get("up") or 0) + (c.get("down") or 0)
        extra = (
            f" ({int(used * 100 / c['limit_bytes'])}%)"
            if c.get("limit_bytes")
            else ""
        )
        msg += (
            f"\n#{c['id']} {esc(c['email'])} "
            f"{'✅' if c.get('enable') else '⛔'} — {fmt_bytes(used)}{extra}"
        )
    send_message(chat, msg)


def cmd_inbounds(chat, args):
    if not _require_admin(chat):
        return
    clients = db.q("SELECT inbounds FROM clients")
    msg = "📡 <b>اینباند‌ها</b>\n"
    for ib in db.q("SELECT * FROM inbounds ORDER BY id"):
        g = load_json(ib.get("config") or "{}", {})
        detail = (
            f"wss://{esc(g.get('path', ''))}"
            if cfg.PAAS
            else f"پورت {g.get('port', '?')} • "
            f"{g.get('transport', 'tcp')}/{g.get('security', 'none')}"
        )
        cnt = sum(
            1
            for c in clients
            if ib["id"] in load_json(c.get("inbounds") or "[]", [])
        )
        msg += (
            f"\n#{ib['id']} <b>{esc(ib.get('remark') or '')}</b> "
            f"[{(ib.get('protocol') or '').upper()}] {detail} • {cnt} کاربر • "
            f"{'✅' if ib.get('enable') else '❌'}"
        )
    send_message(chat, msg)


def cmd_restart(chat, args):
    if not _require_admin(chat):
        return
    send_message(chat, "⏳ در حال راه‌اندازی مجدد هسته ...")
    try:
        ok, err = _xray().restart("دستور تلگرام")
        send_message(
            chat,
            "✅ هسته Xray راه‌اندازی مجدد شد."
            if ok
            else "❌ خطا:\n<code>" + esc(str(err)[:600]) + "</code>",
        )
    except Exception as e:
        send_message(chat, "❌ " + esc(str(e)))


def cmd_notify(chat, args):
    if not _require_admin(chat):
        return
    text = " ".join(args).strip()
    if not text:
        send_message(chat, "❌ صحیح: <code>/notify متن پیام</code>")
        return
    rows = sdb.q("SELECT tg_id FROM users WHERE is_blocked=0")
    n = 0
    for r in rows:
        send_message(r["tg_id"], f"📢 <b>پیام مدیر</b>\n\n{esc(text)}")
        n += 1
        time.sleep(0.05)
    send_message(chat, f"✅ به {n} کاربر ارسال شد.")


def cmd_panel(chat, args=None):
    try:
        from .handlers_admin import cmd_panel as _panel
        _panel(chat)
    except Exception:
        db.log_event(traceback.format_exc(limit=4), "err")
        send_message(chat, "خطا در باز کردن پنل ادمین.")


# ================================================== پیام متنی

def route_message(chat: str, text: str, username: str = ""):
    tg = int(chat)
    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    if u and u.get("is_blocked"):
        send_message(chat, texts.T["blocked"])
        return

    raw = (text or "").strip()
    parts = raw.split()
    # جدا کردن @botname از دستور
    first = (parts[0] if parts else "").split("@", 1)[0].strip()
    low = first.lower()

    # اول FSM — ولی /start همیشه اولویت دارد (ریفرال)
    is_start = low == "/start" or low.startswith("/start=")
    if not is_start:
        with _states_lock:
            if tg in _states:
                try:
                    from .handlers_fsm import route_fsm
                    if route_fsm(tg, text, _states):
                        return
                except Exception:
                    db.log_event(traceback.format_exc(limit=4), "err")
                    _states.pop(tg, None)

    if len(parts) == 1 and BIND_CODE_RE.match(low):
        cmd_bind(chat, [low])
        return

    if not low.startswith("/"):
        send_message(chat, texts.T["start_help"])
        return

    # آرگومان‌ها
    if low.startswith("/start="):
        # حالت /start=CODE
        payload = first.split("=", 1)[-1]
        args = [payload] if payload else []
        cmd = "/start"
    else:
        cmd = low
        args = parts[1:] if len(parts) > 1 else []

    if cmd == "/start":
        cmd_start(chat, args, username)
        return
    if cmd == "/cancel":
        with _states_lock:
            _states.pop(tg, None)
        send_message(chat, texts.T["cancelled"], reply_markup=main_kb())
        return

    ROUTES = {
        "/help": cmd_help,
        "/status": cmd_status,
        "/clients": cmd_clients,
        "/inbounds": cmd_inbounds,
        "/restart": cmd_restart,
        "/notify": cmd_notify,
        "/panel": cmd_panel,
    }
    handler = ROUTES.get(cmd)
    if handler:
        handler(chat, args)
    else:
        send_message(chat, "دستور ناشناخته. /help")


# ================================================== پولینگ

class BotPoller(threading.Thread):
    def __init__(self):
        super().__init__(name="sf-shop-poller", daemon=True)
        self.offset = 0
        self.last_token = ""
        self._stop = threading.Event()

    def run(self):
        db.log_event("ربات فروش: پولر شروع شد", "ok")
        while not self._stop.is_set():
            try:
                token = (db.get_setting("tg_token") or "").strip()
                if not TOKEN_RE.match(token):
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
                json={"drop_pending_updates": False},
                timeout=10,
            )
        except Exception:
            pass

    def _poll_loop(self, token):
        base = f"https://api.telegram.org/bot{token}"
        while not self._stop.is_set():
            current = (db.get_setting("tg_token") or "").strip()
            if current != token:
                return
            try:
                r = requests.get(
                    base + "/getUpdates",
                    params={"timeout": 25, "offset": self.offset},
                    timeout=API_TIMEOUT + 5,
                ).json()
            except (requests.RequestException, ValueError) as e:
                db.log_event(f"tg getUpdates network: {e}", "err")
                time.sleep(5)
                continue

            if not r.get("ok"):
                desc = r.get("description", "")
                db.log_event(f"tg getUpdates: {desc}", "err")
                # اگر conflict با webhook باشد دوباره پاک کن
                if "webhook" in desc.lower():
                    self._reset_webhook(token)
                time.sleep(10)
                continue

            for upd in (r.get("result") or []):
                self.offset = max(
                    self.offset, int(upd.get("update_id", 0)) + 1
                )
                try:
                    self._dispatch(upd)
                except Exception:
                    db.log_event(traceback.format_exc(limit=5), "err")

    def _dispatch(self, upd: dict):
        if "callback_query" in upd:
            handle_callback(upd["callback_query"])
            return

        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        username = ((msg.get("from") or {}).get("username") or "")

        if chat and text:
            route_message(chat, text, username)
            return

        if chat and (msg.get("photo") or msg.get("document")):
            try:
                from .handlers_fsm import handle_media
                handle_media(msg, chat)
            except Exception:
                db.log_event(traceback.format_exc(limit=4), "err")


_poller = None
_poller_lock = threading.Lock()


def start_bot():
    global _poller
    try:
        sdb.connect()
        db.log_event("shop.db متصل شد", "ok")
    except Exception as e:
        db.log_event(f"shop db error: {e}", "err")
        return None

    with _poller_lock:
        if _poller is None or not _poller.is_alive():
            _poller = BotPoller()
            _poller.start()
            db.log_event("پولر ربات استارت شد", "ok")
    return _poller

