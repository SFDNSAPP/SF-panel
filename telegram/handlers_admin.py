# -*- coding: utf-8 -*-
"""پنل مدیریت ربات فروش — نسخه اصلاح‌شده و پایدار
نقش‌ها: owner (اولین آیدی tg_admins) · admin (بقیه)
"""

import time
import threading

from . import db as sdb
from . import texts
from .bot import (
    send_message,
    answer_cbq,
    main_kb,
    _states,
    now_ms,
    get_role,
)

try:
    from .bot import _states_lock
except ImportError:
    _states_lock = threading.RLock()

try:
    from .handlers_fsm import STEP_ADMIN_INPUT
except ImportError:
    STEP_ADMIN_INPUT = "admin_input"

MSG_MAX = 3800


def _esc(s):
    return texts.esc(s)


def _toman(n):
    return f"{int(n or 0):,} تومان"


def _ok_role(chat, roles=("owner", "admin")):
    return get_role(int(chat)) in roles


# ================================================== ورود / داشبورد

def cmd_panel(chat, args=None):
    """args برای سازگاری با route که (chat, args) می‌فرستد"""
    tg = int(chat)
    try:
        if not _ok_role(chat):
            from core import database as panel_db
            admins_raw = (panel_db.get_setting("tg_admins") or "").strip()
            send_message(
                chat,
                "⛔ این بخش فقط برای مدیران است.\n\n"
                f"آیدی عددی شما: <code>{tg}</code>\n\n"
                "اگر مدیر هستید، آیدی را در Settings پنل وب "
                "داخل <b>tg_admins</b> بگذارید.\n\n"
                f"مقدار فعلی:\n<code>{texts.esc(admins_raw) or 'خالی'}</code>"
            )
            return
    except Exception as e:
        send_message(chat, f"خطا در بررسی نقش: {e}")
        return

    try:
        with _states_lock:
            _states.pop(tg, None)
    except Exception:
        try:
            _states.pop(tg, None)
        except Exception:
            pass

    pending = users_n = open_t = 0
    try:
        r = sdb.q(
            "SELECT COUNT(*) n FROM receipts WHERE status='pending'",
            one=True,
        )
        pending = (r or {}).get("n") or 0
    except Exception:
        pass
    try:
        r = sdb.q("SELECT COUNT(*) n FROM users", one=True)
        users_n = (r or {}).get("n") or 0
    except Exception:
        pass
    try:
        r = sdb.q(
            "SELECT COUNT(*) n FROM tickets WHERE status='open'", one=True
        )
        open_t = (r or {}).get("n") or 0
    except Exception:
        pass

    kb = {
        "inline_keyboard": [
            [
                {"text": f"🧾 رسیدها ({pending})", "callback_data": "adm:rcps"},
                {"text": "📊 آمار", "callback_data": "adm:stats"},
            ],
            [
                {"text": "👥 کاربران", "callback_data": "adm:users"},
                {"text": "📦 پلن‌ها", "callback_data": "adm:plans"},
            ],
            [
                {"text": "🎟 کد تخفیف", "callback_data": "adm:coupons"},
                {"text": f"💬 تیکت‌ها ({open_t})", "callback_data": "adm:tickets"},
            ],
            [{"text": "⚙️ تنظیمات", "callback_data": "adm:settings"}],
            [
                {"text": "📢 همگانی", "callback_data": "adm:bcast"},
                {"text": "📜 لاگ", "callback_data": "adm:log"},
            ],
            [{"text": "🔙 منو", "callback_data": "menu"}],
        ]
    }
    role = "Owner" if get_role(tg) == "owner" else "Admin"
    try:
        send_message(
            chat,
            (
                f"👑 پنل مدیریت — {role}\n\n"
                f"🧾 رسید در انتظار: {pending}\n"
                f"👥 کاربران: {users_n}\n"
                f"💬 تیکت باز: {open_t}"
            ),
            reply_markup=kb,
        )
    except Exception as e:
        # اگر HTML/کیبورد مشکل داشت، ساده بفرست
        send_message(
            chat,
            f"پنل مدیریت ({role})\nرسید:{pending} کاربران:{users_n} تیکت:{open_t}\nخطا: {e}",
        )


# ================================================== روتر

def route_callback(cbq, data):
    chat = str(cbq.get("message", {}).get("chat", {}).get("id", ""))
    cbq_id = str(cbq.get("id", ""))
    if not chat or not data:
        return
    if not _ok_role(chat):
        answer_cbq(cbq_id, "⛔ فقط مدیران")
        return

    tg = int(chat)
    p = data.split(":")

    try:
        if data == "adm:menu":
            answer_cbq(cbq_id)
            cmd_panel(chat)

        elif data == "adm:rcps":
            answer_cbq(cbq_id)
            rcps_list(tg)
        elif len(p) >= 4 and p[1] == "rcp":
            rid = int(p[2])
            if p[3] == "ok":
                rcp_approve(tg, rid, cbq_id)
            elif p[3] == "no":
                rcp_reject_start(tg, rid)
                answer_cbq(cbq_id, "دلیل رد را بفرست (یا /cancel)")

        elif data == "adm:stats":
            answer_cbq(cbq_id)
            stats(tg)
        elif data == "adm:users":
            answer_cbq(cbq_id)
            user_find(tg)
        elif len(p) >= 3 and p[1] == "user":
            answer_cbq(cbq_id)
            user_card(tg, int(p[2]))
        elif len(p) >= 3 and p[1] == "uchg":
            with _states_lock:
                _states[tg] = {
                    "step": STEP_ADMIN_INPUT,
                    "data": {"action": "chg", "uid": int(p[2])},
                }
            answer_cbq(cbq_id)
            send_message(
                tg,
                "💵 مبلغ (مثبت=شارژ، منفی=کسر) به تومان:\n"
                "مثال: <code>50000</code> یا <code>-20000</code>",
            )
        elif len(p) >= 3 and p[1] == "ublk":
            answer_cbq(cbq_id)
            user_block(tg, int(p[2]))
        elif len(p) >= 3 and p[1] == "umsg":
            with _states_lock:
                _states[tg] = {
                    "step": STEP_ADMIN_INPUT,
                    "data": {"action": "umsg", "uid": int(p[2])},
                }
            answer_cbq(cbq_id)
            send_message(tg, "✉️ پیام برای کاربر را بفرست:")

        elif data == "adm:plans":
            answer_cbq(cbq_id)
            plans_list(tg)
        elif data == "adm:planadd":
            with _states_lock:
                _states[tg] = {
                    "step": STEP_ADMIN_INPUT,
                    "data": {"action": "planadd"},
                }
            answer_cbq(cbq_id)
            send_message(
                tg,
                "📦 پلن جدید — ۴ خط:\n"
                "<code>عنوان\nروز\nگیگ\nقیمت</code>\n"
                "مثال:\n<code>۱ ساله\n365\n200\n449000</code>",
            )
        elif len(p) >= 3 and p[1] == "plantgl":
            answer_cbq(cbq_id)
            sdb.ex(
                "UPDATE plans SET is_active=1-is_active WHERE id=?",
                (int(p[2]),),
            )
            plans_list(tg)
        elif len(p) >= 3 and p[1] == "plandel":
            answer_cbq(cbq_id, "حذف شد")
            sdb.ex("DELETE FROM plans WHERE id=?", (int(p[2]),))
            plans_list(tg)

        elif data == "adm:coupons":
            answer_cbq(cbq_id)
            coupons_list(tg)
        elif data == "adm:coupadd":
            with _states_lock:
                _states[tg] = {
                    "step": STEP_ADMIN_INPUT,
                    "data": {"action": "coupadd"},
                }
            answer_cbq(cbq_id)
            send_message(
                tg,
                "🎟 کد تخفیف — به این شکل:\n"
                "<code>code|نوع|مقدار|حداقل|سقف‌استفاده|روزانقضا</code>\n"
                "نوع: percent یا fixed · بقیه اختیاری (0)\n"
                "مثال: <code>NOROOZ|percent|30|50000|100|14</code>\n"
                "مثال مبلغی: <code>WELCOME|fixed|20000|30000|0|0</code>",
            )
        elif len(p) >= 3 and p[1] == "couptgl":
            answer_cbq(cbq_id)
            sdb.ex(
                "UPDATE coupons SET is_active=1-is_active WHERE id=?",
                (int(p[2]),),
            )
            coupons_list(tg)
        elif len(p) >= 3 and p[1] == "couprem":
            answer_cbq(cbq_id, "حذف شد")
            sdb.ex("DELETE FROM coupons WHERE id=?", (int(p[2]),))
            coupons_list(tg)

        elif data == "adm:tickets":
            answer_cbq(cbq_id)
            tickets_list(tg)
        elif len(p) >= 3 and p[1] == "tik":
            with _states_lock:
                _states[tg] = {
                    "step": STEP_ADMIN_INPUT,
                    "data": {"action": "tik", "tid": int(p[2])},
                }
            answer_cbq(cbq_id)
            send_message(tg, "↩️ متن پاسخ را بفرست:")

        elif data == "adm:settings":
            answer_cbq(cbq_id)
            settings_menu(tg)
        elif len(p) >= 3 and p[1] == "set":
            key = p[2]
            with _states_lock:
                _states[tg] = {
                    "step": STEP_ADMIN_INPUT,
                    "data": {"action": "set", "key": key},
                }
            answer_cbq(cbq_id)
            labels = {
                "card": "شماره کارت",
                "name": "نام صاحب حساب",
                "ref": "درصد ریفرال",
                "tgb": "گیگ تست",
                "tdays": "روز تست",
                "tcool": "فاصله تست (روز)",
                "mindep": "حداقل شارژ",
                "title": "عنوان فروشگاه",
            }
            send_message(
                tg, f"⚙️ مقدار جدید «{labels.get(key, key)}» را بفرست:"
            )

        elif data == "adm:bcast":
            if get_role(tg) != "owner":
                answer_cbq(cbq_id, "⛔ فقط Owner")
                return
            with _states_lock:
                _states[tg] = {
                    "step": STEP_ADMIN_INPUT,
                    "data": {"action": "bcast"},
                }
            answer_cbq(cbq_id)
            send_message(tg, "📢 متن پیام همگانی را بفرست:")
        elif data == "adm:log":
            if get_role(tg) != "owner":
                answer_cbq(cbq_id, "⛔ فقط Owner")
                return
            answer_cbq(cbq_id)
            admin_log_view(tg)
        else:
            answer_cbq(cbq_id)
    except Exception as e:
        from core import database as db
        db.log_event(f"admin cb {data}: {e}", "err")
        answer_cbq(cbq_id, "خطا")


# ================================================== رسیدها

def rcps_list(tg: int):
    rows = sdb.q(
        "SELECT * FROM receipts WHERE status='pending' ORDER BY id LIMIT 15"
    )
    if not rows:
        send_message(tg, "🧾 رسید در انتظاری نیست. ✅", reply_markup=main_kb())
        return
    for r in rows:
        u = sdb.q(
            "SELECT username FROM users WHERE tg_id=?",
            (r["user_id"],),
            one=True,
        )
        uname = ("@" + u["username"]) if u and u.get("username") else "—"
        kb = {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ تایید",
                        "callback_data": f"adm:rcp:{r['id']}:ok",
                    },
                    {
                        "text": "❌ رد",
                        "callback_data": f"adm:rcp:{r['id']}:no",
                    },
                ]
            ]
        }
        send_message(
            tg,
            (
                f"🧾 <b>رسید #{r['id']}</b>\n"
                f"👤 <code>{r['user_id']}</code> {uname}\n"
                f"💰 <b>{_toman(r['amount'])}</b>"
            ),
            reply_markup=kb,
        )


def rcp_approve(tg: int, rid: int, cbq_id=""):
    r = sdb.q(
        "SELECT * FROM receipts WHERE id=? AND status='pending'",
        (rid,),
        one=True,
    )
    if not r:
        answer_cbq(cbq_id, "قبلاً تعیین شده")
        return

    sdb.ex(
        "UPDATE receipts SET status='approved', admin_id=?, "
        "decided_at=? WHERE id=?",
        (tg, now_ms(), rid),
    )
    sdb.balance_add(
        r["user_id"], r["amount"], "deposit", f"تایید رسید #{rid}"
    )
    send_message(
        r["user_id"],
        texts.T["receipt_ok"].format(amount=r["amount"]),
    )
    sdb.log_admin(
        tg, "receipt_approve", f"#{rid} +{r['amount']} برای {r['user_id']}"
    )
    answer_cbq(cbq_id, "✅ تایید و شارژ شد")


def rcp_reject_start(tg: int, rid: int):
    with _states_lock:
        _states[tg] = {
            "step": STEP_ADMIN_INPUT,
            "data": {"action": "rcp_reason", "rid": rid},
        }


def rcp_reject(tg: int, rid: int, reason: str):
    r = sdb.q(
        "SELECT * FROM receipts WHERE id=? AND status='pending'",
        (rid,),
        one=True,
    )
    if not r:
        return
    sdb.ex(
        "UPDATE receipts SET status='rejected', admin_id=?, "
        "reason=?, decided_at=? WHERE id=?",
        (tg, reason[:300], now_ms(), rid),
    )
    reason_txt = f"\n❗ دلیل: {reason}" if reason else ""
    send_message(
        r["user_id"],
        texts.T["receipt_rej"].format(
            amount=r["amount"], reason=reason_txt
        ),
    )
    sdb.log_admin(tg, "receipt_reject", f"#{rid} {reason[:100]}")
    send_message(
        tg, "❌ رد شد و به کاربر اطلاع داده شد.", reply_markup=main_kb()
    )


# ================================================== کاربران

def user_find(tg: int):
    with _states_lock:
        _states[tg] = {
            "step": STEP_ADMIN_INPUT,
            "data": {"action": "find_user"},
        }
    send_message(tg, "🔍 آیدی عددی کاربر یا @یوزرنیم را بفرست:")


def _find_user(qry: str):
    qry = qry.strip().lstrip("@")
    if qry.lstrip("-").isdigit():
        return sdb.q(
            "SELECT * FROM users WHERE tg_id=?", (int(qry),), one=True
        )
    return sdb.q(
        "SELECT * FROM users WHERE username=? COLLATE NOCASE",
        (qry,),
        one=True,
    )


def user_card(tg: int, uid: int):
    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (uid,), one=True)
    if not u:
        send_message(tg, "کاربر یافت نشد.")
        return

    buys = sdb.q(
        "SELECT COUNT(*) n FROM bot_accounts WHERE user_id=?",
        (uid,),
        one=True,
    )["n"]
    accs = sdb.q(
        "SELECT email FROM bot_accounts "
        "WHERE user_id=? ORDER BY id DESC LIMIT 10",
        (uid,),
    )
    accs_txt = (
        "\n".join(f"  · <code>{_esc(a['email'])}</code>" for a in accs)
        or "  —"
    )
    refs = sdb.q(
        "SELECT COUNT(*) n FROM users WHERE ref_by=?", (uid,), one=True
    )["n"]

    kb = {
        "inline_keyboard": [
            [
                {
                    "text": "💵 تغییر موجودی",
                    "callback_data": f"adm:uchg:{uid}",
                },
                {
                    "text": "✉️ پیام",
                    "callback_data": f"adm:umsg:{uid}",
                },
            ],
            [
                {
                    "text": (
                        "⛔ مسدود"
                        if not u.get("is_blocked")
                        else "✅ رفع مسدود"
                    ),
                    "callback_data": f"adm:ublk:{uid}",
                }
            ],
            [{"text": "🔙 پنل", "callback_data": "adm:menu"}],
        ]
    }
    send_message(
        tg,
        (
            f"👤 <b>کاربر</b> <code>{uid}</code>"
            f" @{_esc(u.get('username') or '—')}\n"
            f"💰 موجودی: <b>{_toman(u.get('balance'))}</b>\n"
            f"🛒 خرید: {buys} · 🎁 ریفرال: {refs}"
            f" (+{_toman(u.get('ref_earnings'))})\n"
            f"📅 عضویت: {time.strftime('%Y-%m-%d', time.localtime((u.get('joined_at') or 0)/1000))}\n"
            f"{'⛔ <b>مسدود</b>' if u.get('is_blocked') else ''}\n"
            f"🔗 کد: <code>{u.get('ref_code')}</code>\n"
            f"📦 اکانت‌ها:\n{accs_txt}"
        ),
        reply_markup=kb,
    )


def user_block(tg: int, uid: int):
    u = sdb.q(
        "SELECT is_blocked FROM users WHERE tg_id=?", (uid,), one=True
    )
    if not u:
        return
    new = 0 if u.get("is_blocked") else 1
    sdb.ex("UPDATE users SET is_blocked=? WHERE tg_id=?", (new, uid))
    sdb.log_admin(tg, "user_block" if new else "user_unblock", str(uid))
    send_message(
        uid,
        "⛔ شما توسط مدیر مسدود شدید."
        if new
        else "✅ مسدودی شما برداشته شد.",
    )
    user_card(tg, uid)


# ================================================== پلن‌ها

def plans_list(tg: int):
    rows = sdb.q("SELECT * FROM plans ORDER BY sort, id")
    if not rows:
        send_message(tg, "پلنی نیست.")
    for p in rows:
        kb = {
            "inline_keyboard": [
                [
                    {
                        "text": (
                            "✅ فعال" if p["is_active"] else "🚫 غیرفعال"
                        ),
                        "callback_data": f"adm:plantgl:{p['id']}",
                    },
                    {
                        "text": "🗑",
                        "callback_data": f"adm:plandel:{p['id']}",
                    },
                ]
            ]
        }
        send_message(
            tg,
            (
                f"📦 <b>{_esc(p['title'])}</b>\n"
                f"⏳ {p['days']} روز · 💾 {p['limit_gb']} گیگ · "
                f"💰 {_toman(p['price'])}"
            ),
            reply_markup=kb,
        )
    send_message(
        tg,
        "➕ افزودن پلن جدید:",
        reply_markup={
            "inline_keyboard": [
                [
                    {
                        "text": "📦 پلن جدید",
                        "callback_data": "adm:planadd",
                    },
                    {"text": "🔙 پنل", "callback_data": "adm:menu"},
                ]
            ]
        },
    )


# ================================================== کد تخفیف

def coupons_list(tg: int):
    rows = sdb.q("SELECT * FROM coupons ORDER BY id DESC LIMIT 15")
    if not rows:
        send_message(tg, "کدی وجود ندارد.")
    for c in rows:
        kb = {
            "inline_keyboard": [
                [
                    {
                        "text": ("✅" if c["is_active"] else "🚫"),
                        "callback_data": f"adm:couptgl:{c['id']}",
                    },
                    {
                        "text": "🗑",
                        "callback_data": f"adm:couprem:{c['id']}",
                    },
                ]
            ]
        }
        val = (
            f"{c['value']}%"
            if c["kind"] == "percent"
            else _toman(c["value"])
        )
        exp = (
            time.strftime(
                "%m-%d", time.localtime(c["expires_at"] / 1000)
            )
            if c["expires_at"]
            else "∞"
        )
        uses = (
            f"{c['used']}/{c['max_uses']}"
            if c["max_uses"]
            else str(c["used"])
        )
        send_message(
            tg,
            (
                f"🎟 <code>{_esc(c['code'])}</code> — {val}\n"
                f"حداقل خرید: {_toman(c['min_amount'])} · "
                f"استفاده: {uses} · انقضا: {exp}"
            ),
            reply_markup=kb,
        )
    send_message(
        tg,
        "➕ ساخت کد جدید:",
        reply_markup={
            "inline_keyboard": [
                [
                    {
                        "text": "🎟 کد جدید",
                        "callback_data": "adm:coupadd",
                    },
                    {"text": "🔙 پنل", "callback_data": "adm:menu"},
                ]
            ]
        },
    )


# ================================================== تیکت‌ها

def tickets_list(tg: int):
    rows = sdb.q(
        "SELECT * FROM tickets WHERE status='open' "
        "ORDER BY id DESC LIMIT 10"
    )
    if not rows:
        send_message(
            tg, "💬 تیکت بازی نیست. ✅", reply_markup=main_kb()
        )
        return
    for t in rows:
        send_message(
            tg,
            (
                f"💬 <b>تیکت #{t['id']}</b> — <code>{t['user_id']}</code>\n"
                f"{_esc(t['message'][:300])}"
            ),
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": "↩️ پاسخ",
                            "callback_data": f"adm:tik:{t['id']}",
                        }
                    ]
                ]
            },
        )


def ticket_reply(tg: int, tid: int, text: str):
    t = sdb.q("SELECT * FROM tickets WHERE id=?", (tid,), one=True)
    if not t:
        return
    sdb.ex("UPDATE tickets SET status='answered' WHERE id=?", (tid,))
    send_message(
        t["user_id"],
        f"💬 <b>پاسخ پشتیبانی:</b>\n\n{_esc(text[:800])}",
    )
    sdb.log_admin(tg, "ticket_reply", f"#{tid}")
    send_message(tg, "✅ پاسخ ارسال شد.", reply_markup=main_kb())


# ================================================== تنظیمات

def settings_menu(tg: int):
    card = sdb.get_setting("card_number")
    name = sdb.get_setting("card_name")
    kb = {
        "inline_keyboard": [
            [
                {
                    "text": "💳 شماره کارت",
                    "callback_data": "adm:set:card",
                },
                {
                    "text": "👤 نام صاحب حساب",
                    "callback_data": "adm:set:name",
                },
            ],
            [
                {
                    "text": "🤝 درصد ریفرال",
                    "callback_data": "adm:set:ref",
                },
                {
                    "text": "🎁 گیگ تست",
                    "callback_data": "adm:set:tgb",
                },
            ],
            [
                {
                    "text": "⏳ روز تست",
                    "callback_data": "adm:set:tdays",
                },
                {
                    "text": "🕐 فاصله تست (روز)",
                    "callback_data": "adm:set:tcool",
                },
            ],
            [
                {
                    "text": "💵 حداقل شارژ",
                    "callback_data": "adm:set:mindep",
                },
                {
                    "text": "🏷 عنوان فروشگاه",
                    "callback_data": "adm:set:title",
                },
            ],
            [{"text": "🔙 پنل", "callback_data": "adm:menu"}],
        ]
    }
    send_message(
        tg,
        f"⚙️ <b>تنظیمات</b>\n\n💳 <code>{_esc(card)}</code> — {_esc(name)}",
        reply_markup=kb,
    )


def set_value(tg: int, key: str, value: str):
    v = value.strip()
    mapping = {
        "card": "card_number",
        "name": "card_name",
        "ref": "ref_percent",
        "tgb": "trial_gb",
        "tdays": "trial_days",
        "tcool": "trial_cooldown",
        "mindep": "min_deposit",
        "title": "shop_title",
    }
    real_key = mapping.get(key, key)

    if key in ("ref", "tgb", "tdays", "tcool", "mindep"):
        if not v.replace(",", "").isdigit():
            send_message(tg, "❌ باید عدد باشد.")
            return

    sdb.set_setting(real_key, v)
    sdb.log_admin(tg, "setting", f"{real_key}={v[:50]}")
    send_message(tg, "✅ ذخیره شد.", reply_markup=main_kb())
    settings_menu(tg)


# ================================================== آمار

def stats(tg: int):
    deposits = sdb.q(
        "SELECT COALESCE(SUM(amount),0) s, COUNT(*) n "
        "FROM transactions WHERE kind='deposit'",
        one=True,
    )
    sales = sdb.q(
        "SELECT COALESCE(SUM(-amount),0) s, COUNT(*) n "
        "FROM transactions WHERE kind='purchase'",
        one=True,
    )
    day_ms = now_ms() - 86400000
    today_sales = sdb.q(
        "SELECT COALESCE(SUM(-amount),0) s, COUNT(*) n "
        "FROM transactions WHERE kind='purchase' AND ts>?",
        (day_ms,),
        one=True,
    )
    users_n = sdb.q("SELECT COUNT(*) n FROM users", one=True)["n"]
    new_today = sdb.q(
        "SELECT COUNT(*) n FROM users WHERE joined_at>?",
        (day_ms,),
        one=True,
    )["n"]
    top = sdb.q(
        "SELECT p.title, COUNT(*) n FROM bot_accounts b "
        "JOIN plans p ON p.id=b.plan_id WHERE b.plan_id>0 "
        "GROUP BY b.plan_id ORDER BY n DESC LIMIT 3"
    )
    top_txt = (
        "\n".join(f"  · {_esc(t['title'])} ({t['n']})" for t in top)
        or "  —"
    )
    send_message(
        tg,
        (
            f"📊 <b>آمار فروشگاه</b>\n\n"
            f"💰 درآمد کل: <b>{_toman(sales['s'])}</b> "
            f"({sales['n']} فروش)\n"
            f"📈 فروش ۲۴ ساعت: {_toman(today_sales['s'])} "
            f"({today_sales['n']})\n"
            f"💳 واریز تاییدشده: {_toman(deposits['s'])}\n"
            f"👥 کاربران: {users_n} (جدید امروز: {new_today})\n\n"
            f"🏆 پرفروش‌ها:\n{top_txt}"
        ),
        reply_markup=main_kb(),
    )


# ================================================== Broadcast / لاگ

def bcast_send(tg: int, text: str):
    if get_role(tg) != "owner":
        send_message(tg, "⛔ فقط Owner")
        return
    rows = sdb.q("SELECT tg_id FROM users WHERE is_blocked=0")
    n = 0
    for r in rows:
        send_message(r["tg_id"], text[:MSG_MAX])
        n += 1
        time.sleep(0.06)
    sdb.log_admin(tg, "broadcast", f"{n} نفر")
    send_message(tg, f"📢 به {n} کاربر ارسال شد.", reply_markup=main_kb())


def admin_log_view(tg: int):
    rows = sdb.q("SELECT * FROM admin_log ORDER BY id DESC LIMIT 15")
    txt = (
        "\n".join(
            f"· [{time.strftime('%m-%d %H:%M', time.localtime(r['ts']/1000))}] "
            f"<code>{r['admin_id']}</code> {r['action']} {_esc(r['detail'][:60])}"
            for r in rows
        )
        or "—"
    )
    send_message(
        tg, f"📜 <b>لاگ ادمین‌ها</b>\n{txt}", reply_markup=main_kb()
    )


# ================================================== ورودی‌های متنی (FSM)

def fsm_input(tg: int, text: str, states: dict, st, data) -> bool:
    action = data.get("action")

    if action == "find_user":
        u = _find_user(text)
        with _states_lock:
            states.pop(tg, None)
        if u:
            user_card(tg, u["tg_id"])
        else:
            send_message(tg, "یافت نشد. آیدی عددی یا @یوزرنیم را دوباره بفرست:")
            with _states_lock:
                states[tg] = {
                    "step": STEP_ADMIN_INPUT,
                    "data": {"action": "find_user"},
                }
        return True

    if action == "chg":
        uid = data["uid"]
        try:
            amount = int(text.strip().replace(",", "").replace("،", ""))
        except ValueError:
            send_message(tg, "❌ عدد نامعتبر. مثال: 50000 یا -20000")
            return True
        u = sdb.q(
            "SELECT balance FROM users WHERE tg_id=?", (uid,), one=True
        )
        if not u:
            with _states_lock:
                states.pop(tg, None)
            return True
        if u["balance"] + amount < 0:
            send_message(tg, "❌ موجودی منفی می‌شود.")
            return True
        sdb.balance_add(uid, amount, "adjust", f"توسط ادمین {tg}")
        sdb.log_admin(tg, "balance_adjust", f"{uid} {amount}")
        sign = "+" if amount >= 0 else ""
        send_message(
            uid,
            f"💵 موجودی شما به مقدار <b>{sign}{amount:,}</b> تومان تغییر کرد.",
        )
        with _states_lock:
            states.pop(tg, None)
        user_card(tg, uid)
        return True

    if action == "umsg":
        uid = data["uid"]
        send_message(
            uid, f"✉️ <b>پیام مدیر:</b>\n\n{_esc(text[:800])}"
        )
        with _states_lock:
            states.pop(tg, None)
        send_message(tg, "✅ ارسال شد.", reply_markup=main_kb())
        return True

    if action == "planadd":
        lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
        if len(lines) < 4 or not all(
            x.replace(",", "").isdigit() for x in lines[1:]
        ):
            send_message(
                tg, "❌ ۴ خط: عنوان/روز/گیگ/قیمت (اعداد صحیح)"
            )
            return True
        title = lines[0]
        days = int(lines[1].replace(",", ""))
        gb = int(lines[2].replace(",", ""))
        price = int(lines[3].replace(",", ""))
        sort = 1 + (
            sdb.q(
                "SELECT COALESCE(MAX(sort),0) s FROM plans", one=True
            )["s"]
        )
        sdb.ex(
            "INSERT INTO plans(title,days,limit_gb,price,is_active,sort) "
            "VALUES(?,?,?,?,1,?)",
            (title, days, gb, price, sort),
        )
        sdb.log_admin(tg, "plan_add", f"{title} {price}")
        with _states_lock:
            states.pop(tg, None)
        send_message(tg, "✅ پلن ساخته شد.")
        plans_list(tg)
        return True

    if action == "coupadd":
        parts = [x.strip() for x in text.strip().split("|")]
        if len(parts) < 3:
            send_message(
                tg, "❌ قالب: code|نوع|مقدار|حداقل|سقف|روز"
            )
            return True
        code = parts[0].upper()
        kind = parts[1].lower()
        if kind not in ("percent", "fixed"):
            send_message(tg, "❌ نوع باید percent یا fixed باشد.")
            return True
        if not parts[2].isdigit():
            send_message(tg, "❌ مقدار عدد نیست.")
            return True
        value = int(parts[2])
        if kind == "percent" and not (1 <= value <= 99):
            send_message(tg, "❌ درصد بین ۱ تا ۹۹.")
            return True
        mn = (
            int(parts[3])
            if len(parts) > 3 and parts[3].isdigit()
            else 0
        )
        mx = (
            int(parts[4])
            if len(parts) > 4 and parts[4].isdigit()
            else 0
        )
        dy = (
            int(parts[5])
            if len(parts) > 5 and parts[5].isdigit()
            else 0
        )
        exp = now_ms() + dy * 86400000 if dy else 0
        if sdb.q(
            "SELECT id FROM coupons WHERE code=?", (code,), one=True
        ):
            send_message(tg, "❌ این کد قبلاً ساخته شده.")
            return True
        sdb.ex(
            "INSERT INTO coupons(code,kind,value,min_amount,max_uses,"
            "expires_at,is_active) VALUES(?,?,?,?,?,?,1)",
            (code, kind, value, mn, mx, exp),
        )
        sdb.log_admin(tg, "coupon_add", code)
        with _states_lock:
            states.pop(tg, None)
        send_message(
            tg,
            f"✅ کد <code>{_esc(code)}</code> ساخته شد.",
            reply_markup=main_kb(),
        )
        return True

    if action == "tik":
        with _states_lock:
            states.pop(tg, None)
        ticket_reply(tg, data["tid"], text)
        return True

    if action == "set":
        with _states_lock:
            states.pop(tg, None)
        set_value(tg, data["key"], text)
        return True

    if action == "bcast":
        with _states_lock:
            states.pop(tg, None)
        bcast_send(tg, text)
        return True

    if action == "rcp_reason":
        with _states_lock:
            states.pop(tg, None)
        rcp_reject(tg, data["rid"], text.strip())
        return True

    return False

