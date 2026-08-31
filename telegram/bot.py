#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ربات تلگرام SF-Panel
------------------------------
• پولینگ بلند getUpdates — مقاوم به خطا و تعویض توکن
• دستورات کاربر : /start /help /bind /unbind /config /usage
• دستورات ادمین : /status /clients /inbounds /restart /notify
• اعلان خودکار  : ۸۰٪ حجم، نزدیک انقضا، غیرفعال‌شدن (از scheduler)

صادرات عمومی:
    send_message(chat_id, text)  ← scheduler برای اعلان‌ها
    start_bot()                  ← app.py برای راه‌اندازی
"""

import re
import threading
import time
import traceback

import requests

from core import config as cfg
from core import database as db
from core.utils import fmt_bytes, fmt_duration, load_json
from core.link_builder import client_links, resolve_public_host

API_TIMEOUT = 35
MSG_MAX = 4000
BIND_CODE_RE = re.compile(r"^[A-Za-z0-9_\-]{6,64}$")
TOKEN_RE = re.compile(r"^\d+:[\w\-]{30,}$")
START_TS = time.time()


# ================================================== ابزارها

def now_ms() -> int:
    return int(time.time() * 1000)


def esc(s) -> str:
    return (str(s or "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _base_url() -> str:
    """آدرس پایه پنل برای ساخت لینک اشتراک."""
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
    """ارسال پیام — چندتکه‌کننده + fallback خام اگر HTML خطا داد."""
    if not chat_id or not text:
        return
    token = db.get_setting("tg_token")
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    parts = [text[i:i + MSG_MAX] for i in range(0, len(text), MSG_MAX)]
    try:
        for i, part in enumerate(parts):
            is_last = (i == len(parts) - 1)
            payload = {
                "chat_id": chat_id,
                "text": part,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            if reply_markup and is_last:
                payload["reply_markup"] = reply_markup
            r = requests.post(url, json=payload, timeout=API_TIMEOUT)
            if r.status_code == 400 and parse_mode:
                # خطای تجزیه HTML → ارسال متن خام
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


def _admins() -> list:
    out = []
    for part in (db.get_setting("tg_admins") or "").split(","):
        p = part.strip()
        if p and p.lstrip("-").isdigit():
            out.append(p)
    return out


def _require_admin(chat: str) -> bool:
    if chat in _admins():
        return True
    send_message(chat, "⛔ این دستور فقط برای مدیران است.")
    return False


def _xray():
    from core.xray import xray
    return xray


# ================================================== قالب‌ها

def _fmt_expiry(ts_ms) -> str:
    if not ts_ms:
        return "∞"
    left = (ts_ms - now_ms()) / 1000
    if left <= 0:
        return "منقضی ⛔"
    return fmt_duration(left)


def _progress_bar(pct: int, width: int = 10) -> str:
    filled = max(0, min(width, round(pct * width / 100)))
    return "█" * filled + "░" * (width - filled)


def _client_card(c: dict) -> str:
    used = c["up"] + c["down"]
    lim = c["limit_bytes"]
    pct = int(used * 100 / lim) if lim else 0
    lines = [f"👤 <b>{esc(c['email'])}</b>"]
    if c.get("note"):
        lines.append(f"📝 {esc(c['note'])}")
    lines.append("وضعیت: ✅ فعال" if c["enable"] else "وضعیت: ⛔ غیرفعال")
    if lim:
        lines.append(f"حجم: {fmt_bytes(used)} از {fmt_bytes(lim)} ({pct}%)")
        lines.append(_progress_bar(pct))
    else:
        lines.append(f"حجم: {fmt_bytes(used)} — بدون محدودیت")
    lines.append(f"اعتبار: {_fmt_expiry(c['expiry'])}")
    return "\n".join(lines)


def _user_kb() -> dict:
    return {"inline_keyboard": [
        [{"text": "🔗 کانفیگ‌ها", "callback_data": "cfg"},
         {"text": "📊 مصرف", "callback_data": "usage"}],
        [{"text": "🔄 بروزرسانی", "callback_data": "refresh"}],
    ]}


def _admin_kb() -> dict:
    kb = _user_kb()
    kb["inline_keyboard"].insert(
        0, [{"text": "🖥 وضعیت سرور", "callback_data": "status"}])
    return kb


# ================================================== دستورات کاربر

def cmd_start(chat: str, args) -> None:
    send_message(chat, (
        f"👋 به ربات <b>{esc(cfg.APP_NAME)}</b> خوش آمدید!\n\n"
        f"🆔 شناسه شما: <code>{esc(chat)}</code>\n\n"
        "این شناسه را در پنل ← تنظیمات ← «شناسه‌های ادمین» وارد کنید "
        "تا دسترسی مدیر بگیرید.\n\n"
        "🔗 اتصال کانفیگ: <code>/bind کد</code>\n"
        "کد اتصال را از پنل ← کاربران ← دکمه «لینک‌ها» دریافت کنید.\n\n"
        "📖 راهنما: /help"
    ), reply_markup=_user_kb())


def cmd_help(chat: str, args) -> None:
    admin = chat in _admins()
    lines = [
        "📖 <b>دستورات ربات SF-Panel</b>",
        "",
        "<b>کاربر:</b>",
        "/bind کد — اتصال کانفیگ به تلگرام",
        "/unbind — قطع اتصال همه کانفیگ‌ها",
        "/config — دریافت لینک کانفیگ‌ها",
        "/usage — نمایش مصرف",
    ]
    if admin:
        lines += [
            "",
            "<b>مدیر:</b>",
            "/status — وضعیت سرور",
            "/clients — لیست کاربران",
            "/inbounds — لیست اینباند‌ها",
            "/restart — راه‌اندازی مجدد هسته",
            "/notify متن — ارسال پیام به همه کاربران متصل",
        ]
    send_message(chat, "\n".join(lines))


def cmd_bind(chat: str, args) -> None:
    if not args:
        send_message(chat, "❌ صحیح: <code>/bind کد-اتصال</code>\n"
                           "کد را از پنل ← کاربران ← «لینک‌ها» بگیرید.")
        return
    code = args[0].strip()
    c = db.q("SELECT * FROM clients WHERE sub_id=?", (code,), one=True)
    if not c:
        send_message(chat, "❌ کد اتصال معتبر نیست.")
        return
    if c["tg_id"] and c["tg_id"] != chat:
        send_message(chat, "❌ این کانفیگ قبلاً به حساب تلگرام دیگری متصل است.")
        return
    db.ex("UPDATE clients SET tg_id=? WHERE id=?", (chat, c["id"]))
    db.log_event(f"کاربر «{c['email']}» به تلگرام متصل شد ({chat})", "ok")
    send_message(chat, f"✅ کانفیگ <b>{esc(c['email'])}</b> متصل شد!\n\n"
                       "برای دریافت کانفیگ‌ها /config را بزنید.",
                 reply_markup=_user_kb())


def cmd_unbind(chat: str, args) -> None:
    rows = db.q("SELECT email FROM clients WHERE tg_id=?", (chat,))
    if not rows:
        send_message(chat, "کانفیگی به تلگرام شما متصل نیست.")
        return
    db.ex("UPDATE clients SET tg_id='' WHERE tg_id=?", (chat,))
    names = "، ".join(esc(r["email"]) for r in rows)
    db.log_event(f"قطع اتصال تلگرام {chat}", "info")
    send_message(chat, f"✅ اتصال این کانفیگ‌ها برداشته شد:\n{names}")


def cmd_config(chat: str, args) -> None:
    rows = db.q("SELECT * FROM clients WHERE tg_id=? ORDER BY id", (chat,))
    if not rows:
        send_message(chat, "🔗 هنوز کانفیگی متصل نیست.\n"
                           "کد اتصال را از پنل بگیرید و بفرستید، یا: "
                           "<code>/bind کد</code>")
        return
    base = _base_url()
    for c in rows:
        header = _client_card(c)
        if not c["enable"]:
            send_message(chat, header + "\n\n⛔ این کانفیگ غیرفعال است.")
            continue
        links = client_links(c, host=resolve_public_host())
        if not links:
            send_message(chat, header + "\n\n⚠️ اینباند فعالی برای این کاربر "
                                      "وجود ندارد.")
            continue
        body = "\n\n".join(
            f"🔸 <b>{esc(l['name'])}</b>\n<code>{esc(l['link'])}</code>"
            for l in links)
        sub = (f"\n\n📥 <b>اشتراک هوشمند</b>\n"
               f"<code>{esc(base)}/sub/{esc(c['sub_id'])}</code>")
        send_message(chat, header + "\n\n" + body + sub)


def cmd_usage(chat: str, args) -> None:
    rows = db.q("SELECT * FROM clients WHERE tg_id=? ORDER BY id", (chat,))
    if not rows:
        send_message(chat, "کانفیگی متصل نیست. /bind کد")
        return
    msg = "📊 <b>مصرف کانفیگ‌ها</b>\n"
    for c in rows:
        msg += "\n" + _client_card(c) + "\n"
    send_message(chat, msg, reply_markup=_user_kb())


# ================================================== دستورات ادمین

def cmd_status(chat: str, args) -> None:
    if not _require_admin(chat):
        return
    xs = _xray().state()
    totals = db.q(
        "SELECT COALESCE(SUM(up),0) AS u, COALESCE(SUM(down),0) AS d, "
        "COUNT(*) AS n, COALESCE(SUM(enable),0) AS e FROM clients",
        one=True)
    inb_n = db.q("SELECT COUNT(*) AS n FROM inbounds", one=True)["n"]
    day = time.strftime("%Y-%m-%d", time.gmtime())
    daily = db.q("SELECT * FROM daily_totals WHERE day=?", (day,), one=True) \
        or {"up": 0, "down": 0}
    msg = (
        f"🖥 <b>{esc(cfg.APP_NAME)}</b>\n"
        f"├ پنل: ✅ فعال ({fmt_duration(time.time() - START_TS)})\n"
        f"├ Xray: {'✅' if xs['running'] else '❌'} "
        f"{esc(xs['version'] or '—')}\n"
        f"├ آپتایم هسته: {fmt_duration(xs.get('uptime', 0))}\n"
        f"├ کاربران: {totals['n']} (فعال: {totals['e']})\n"
        f"├ اینباند‌ها: {inb_n}\n"
        f"├ امروز: ↑{fmt_bytes(daily['up'])} ↓{fmt_bytes(daily['down'])}\n"
        f"└ کل: ↑{fmt_bytes(totals['u'])} ↓{fmt_bytes(totals['d'])}"
    )
    send_message(chat, msg, reply_markup=_admin_kb())


def cmd_clients(chat: str, args) -> None:
    if not _require_admin(chat):
        return
    rows = db.q("SELECT * FROM clients ORDER BY id DESC LIMIT 60")
    if not rows:
        send_message(chat, "کاربری وجود ندارد.")
        return
    msg = "👥 <b>کاربران</b> (۶۰ مورد آخر)\n"
    for c in rows:
        used = c["up"] + c["down"]
        lim = c["limit_bytes"]
        extra = f" ({int(used * 100 / lim)}%)" if lim else ""
        msg += (f"\n#{c['id']} {esc(c['email'])} "
                f"{'✅' if c['enable'] else '⛔'} "
                f"— {fmt_bytes(used)}{extra} — {_fmt_expiry(c['expiry'])}")
    send_message(chat, msg)


def cmd_inbounds(chat: str, args) -> None:
    if not _require_admin(chat):
        return
    rows = db.q("SELECT * FROM inbounds ORDER BY id")
    if not rows:
        send_message(chat, "اینباندی وجود ندارد.")
        return
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
                f"[{ib['protocol'].upper()}]\n"
                f"      {detail} • {cnt} کاربر • "
                f"{'✅' if ib['enable'] else '❌'}")
    send_message(chat, msg)


def cmd_restart(chat: str, args) -> None:
    if not _require_admin(chat):
        return
    send_message(chat, "⏳ در حال راه‌اندازی مجدد هسته ...")
    try:
        ok, err = _xray().restart("دستور تلگرام")
        if ok:
            send_message(chat, "✅ هسته Xray با موفقیت راه‌اندازی مجدد شد.")
        else:
            send_message(chat, "❌ خطا:\n<code>" + esc(err[:600]) + "</code>")
    except Exception as e:
        send_message(chat, "❌ خطا: " + esc(str(e)))


def cmd_notify(chat: str, args) -> None:
    """مدیر → ارسال پیام به همه کاربران متصل."""
    if not _require_admin(chat):
        return
    text = " ".join(args).strip()
    if not text:
        send_message(chat, "❌ صحیح: <code>/notify متن پیام</code>")
        return
    rows = db.q("SELECT DISTINCT tg_id FROM clients WHERE tg_id<>''")
    if not rows:
        send_message(chat, "کاربر متصلی وجود ندارد.")
        return
    n = 0
    for r in rows:
        send_message(r["tg_id"], f"📢 <b>پیام مدیر</b>\n\n{esc(text)}")
        n += 1
        time.sleep(0.05)   # احترام به محدودیت نرخ تلگرام
    db.log_event(f"پیام مدیر به {n} کاربر تلگرام ارسال شد", "info")
    send_message(chat, f"✅ پیام به {n} کاربر ارسال شد.")


# ================================================== Callback

def handle_callback(cbq: dict) -> None:
    chat = str(cbq.get("message", {}).get("chat", {}).get("id", ""))
    data = cbq.get("data", "")
    cbq_id = str(cbq.get("id", ""))
    if not chat or not data:
        return
    if data == "cfg":
        answer_cbq(cbq_id)
        cmd_config(chat, [])
    elif data == "usage":
        answer_cbq(cbq_id, "📊")
        cmd_usage(chat, [])
    elif data == "status":
        if chat in _admins():
            answer_cbq(cbq_id)
            cmd_status(chat, [])
        else:
            answer_cbq(cbq_id, "⛔ فقط مدیر")
    elif data == "refresh":
        answer_cbq(cbq_id, "🔄 بروزرسانی شد")
        cmd_usage(chat, [])


# ================================================== پولینگ

class BotPoller(threading.Thread):
    """پولینگ بلند — یکی در زمان؛ توکن از دیتابیس خوانده می‌شود."""

    def __init__(self):
        super().__init__(name="sf-tg-poller", daemon=True)
        self.offset = 0
        self.last_token = ""

    def run(self):
        while True:
            try:
                token = db.get_setting("tg_token") or ""
                if not TOKEN_RE.match(token):
                    time.sleep(8)
                    continue
                if token != self.last_token:
                    self.last_token = token
                    self.offset = 0
                    self._reset_webhook(token)
                    db.log_event("ربات تلگرام فعال شد", "ok")
                self._poll_loop(token)
            except Exception as e:
                db.log_event(f"tg poll: {e}", "err")
                time.sleep(10)

    @staticmethod
    def _reset_webhook(token: str) -> None:
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/deleteWebhook",
                json={"drop_pending_updates": True}, timeout=10)
        except Exception:
            pass

    def _poll_loop(self, token: str):
        base = f"https://api.telegram.org/bot{token}"
        while True:
            if (db.get_setting("tg_token") or "") != token:
                return          # توکن عوض شد؛ حلقه بیرونی دوباره می‌خواند
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

    def _dispatch(self, upd: dict) -> None:
        if "callback_query" in upd:
            handle_callback(upd["callback_query"])
            return
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        if not chat or not text:
            return
        parts = text.split()
        head = parts[0].lower()
        if head.startswith("/"):
            handler = ROUTES.get(head.split("@", 1)[0])
            if handler:
                handler(chat, parts[1:])
            else:
                send_message(chat, "دستور ناشناخته است. /help")
        elif len(parts) == 1 and BIND_CODE_RE.match(head):
            # متن خام = احتمالاً کد اتصال کاربر
            cmd_bind(chat, [head])


ROUTES = {
    "/start": cmd_start,
    "/help": cmd_help,
    "/bind": cmd_bind,
    "/unbind": cmd_unbind,
    "/config": cmd_config,
    "/my": cmd_config,
    "/usage": cmd_usage,
    "/status": cmd_status,
    "/clients": cmd_clients,
    "/inbounds": cmd_inbounds,
    "/restart": cmd_restart,
    "/notify": cmd_notify,
}

_poller = None


def start_bot() -> BotPoller:
    """ایجاد/شروع نخ ربات — از app.py صدا زده می‌شود."""
    global _poller
    if _poller is None or not _poller.is_alive():
        _poller = BotPoller()
        _poller.start()
    return _poller