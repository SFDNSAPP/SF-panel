#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""گفتگوهای ربات فروش (FSM) — بخش ۴ از ۶
مبلغ شارژ · ارسال رسید · کد تخفیف · فرم نمایندگی · پیام پشتیبانی
حالت‌ها از bot._states خوانده/نوشته می‌شوند.
"""

import time

from core import database as db
from . import db as sdb
from . import texts
from .bot import (send_message, main_kb, _states, now_ms,
                  get_role, _admins_all, forward_photo_or_file)

# گام‌های FSM
STEP_DEPOSIT = "deposit_amount"
STEP_RECEIPT = "receipt_file"
STEP_COUPON = "coupon"
STEP_AGENT = "agent_form"
STEP_SUPPORT = "support_message"
STEP_ADMIN_INPUT = "admin_input"


def route_fsm(tg: int, text: str, states: dict) -> bool:
    """→ True اگر پیام در FSM مصرف شد."""
    st = states.get(tg)
    if not st:
        return False

    if text.strip().lower() == "/cancel":
        states.pop(tg, None)
        send_message(tg, texts.T["cancelled"], reply_markup=main_kb())
        return True

    step = st.get("step")
    data = st.setdefault("data", {})

    if step == STEP_DEPOSIT:
        return _fsm_deposit(tg, text, states)
    if step == STEP_RECEIPT:
        # متن به‌جای فایل رسید — راهنمایی
        send_message(tg, "لطفاً <b>عکس یا فایل</b> رسید را بفرست "
                         "(نه متن). /cancel برای انصراف.")
        return True
    if step == STEP_COUPON:
        return _fsm_coupon(tg, text, states, st, data)
    if step == STEP_AGENT:
        return _fsm_agent(tg, text, states)
    if step == STEP_SUPPORT:
        return _fsm_support(tg, text, states)
    if step == STEP_ADMIN_INPUT:
        return _fsm_admin_input(tg, text, states, st, data)
    return False


# ---------------- شارژ (مبلغ) ----------------

def _fsm_deposit(tg: int, text: str, states: dict) -> bool:
    try:
        amount = int(text.strip().replace(",", ""))
    except ValueError:
        send_message(tg, "❌ مبلغ باید عدد باشد. مثال: <code>50000</code>")
        return True
    if amount <= 0:
        send_message(tg, "❌ مبلغ نامعتبر است.")
        return True
    min_d = int(sdb.get_setting("min_deposit", "10000"))
    if amount < min_d:
        send_message(tg, f"❌ حداقل مبلغ {min_d:,} تومان است.")
        return True
    if amount > 100_000_000:
        send_message(tg, "❌ مبلغ بیش از حد مجاز است.")
        return True

    states[tg] = {"step": STEP_RECEIPT,
                  "data": {"amount": amount}}
    send_message(tg, texts.T["deposit_card"].format(
        card=sdb.get_setting("card_number"),
        name=sdb.get_setting("card_name"),
        amount=amount))
    return True


# ---------------- رسیدهایی که ادمین تایید/رد می‌کند (دریافت فایل) ----------------

def handle_media(msg: dict, chat: str):
    """عکس/فایل — اگر در حالت receipt بود → ثبت و فوروارد به ادمین‌ها"""
    tg = int(chat)
    st = _states.get(tg)
    if not st or st.get("step") != STEP_RECEIPT:
        return
    amount = st.get("data", {}).get("amount", 0)
    if not amount:
        _states.pop(tg, None)
        return

    # file_id از بزرگ‌ترین عکس یا document
    file_id = ""
    if msg.get("photo"):
        file_id = msg["photo"][-1].get("file_id", "")
    elif msg.get("document"):
        file_id = msg["document"].get("file_id", "")

    rid = sdb.ex(
        "INSERT INTO receipts(user_id,amount,file_id,status,ts) "
        "VALUES(?,?,?,?,?)",
        (tg, amount, file_id, "pending", now_ms()))
    _states.pop(tg, None)

    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    uname = ("@" + u["username"]) if u and u["username"] else "—"

    kb = {"inline_keyboard": [
        [{"text": "✅ تایید", "callback_data": f"adm:rcp:{rid}:ok"},
         {"text": "❌ رد", "callback_data": f"adm:rcp:{rid}:no"}],
    ]}
    caption = (
        f"🧾 <b>رسید #{rid}</b>\n\n"
        f"👤 کاربر: <code>{tg}</code> {uname}\n"
        f"💰 مبلغ: <b>{amount:,} تومان</b>"
    )
    for admin in _admins_all():
        # فوروارد رسیده
        forward_photo_or_file(admin, int(chat), msg["message_id"])
        # پیام با دکمه‌ها روی همان رسیده
        send_message(admin, caption, reply_markup=kb)
    send_message(tg, texts.T["receipt_sent"], reply_markup=main_kb())


# ---------------- کد تخفیف ----------------

def _fsm_coupon(tg: int, text: str, states: dict, st, data) -> bool:
    raw = text.strip()
    if raw.lower() in ("بدون", "skip", "ندارم", "no", "-"):
        discount = 0
    else:
        err, discount = sdb.check_coupon(raw, data.get("price", 0), tg)
        if err:
            send_message(tg, f"❌ {err}\nکد دیگری بفرست یا «بدون کد»:")
            return True
        data["coupon_code"] = raw

    plan = data.get("plan", {})
    price = data.get("price", 0)
    final = max(0, price - discount)
    states[tg] = {"step": None, "data": data}   # FSM تمام — منتظر دکمه خرید

    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    kb = {"inline_keyboard": [
        [{"text": f"💳 پرداخت ({final:,} تومان)",
          "callback_data": f"shop:pay:{plan.get('id')}"}],
        [{"text": "🔙 انصراف", "callback_data": "menu"}],
    ]}
    send_message(tg, texts.T["invoice"].format(
        title=plan.get("title", "?"), price=price, discount=discount,
        final=final, balance=u["balance"] if u else 0,
    ) + ("\n\n🎟 کد: <code>" + data["coupon_code"] + "</code>"
         if data.get("coupon_code") else ""), reply_markup=kb)
    return True


# ---------------- نمایندگی ----------------

def _fsm_agent(tg: int, text: str, states: dict) -> bool:
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 3:
        send_message(tg, "❌ سه خط لازم است:\n"
                         "<code>نام\nشماره تماس\nتوضیحات</code>")
        return True
    name, phone, desc = lines[0], lines[1], " ".join(lines[2:])
    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    uname = ("@" + u["username"]) if u and u["username"] else "—"
    for admin in _admins_all():
        send_message(admin, (
            f"🏪 <b>درخواست نمایندگی</b>\n\n"
            f"👤 <code>{tg}</code> {uname}\n"
            f"📛 نام: {texts.esc(name)}\n"
            f"📞 تماس: {texts.esc(phone)}\n"
            f"📝 {texts.esc(desc[:400])}"))
    states.pop(tg, None)
    send_message(tg, texts.T["agent_sent"], reply_markup=main_kb())
    return True


# ---------------- پشتیبانی ----------------

def _fsm_support(tg: int, text: str, states: dict) -> bool:
    tid = sdb.ex("INSERT INTO tickets(user_id,message,ts) VALUES(?,?,?)",
                 (tg, text[:1000], now_ms()))
    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    uname = ("@" + u["username"]) if u and u["username"] else "—"
    for admin in _admins_all():
        send_message(admin, (
            f"💬 <b>تیکت #{tid}</b>\n"
            f"👤 <code>{tg}</code> {uname}\n\n"
            f"{texts.esc(text[:800])}"),
            reply_markup={"inline_keyboard": [[
                {"text": "↩️ پاسخ", "callback_data": f"adm:tik:{tid}"}]]})
    states.pop(tg, None)
    send_message(tg, texts.T["support_sent"], reply_markup=main_kb())
    return True


# ---------------- ورودی ادمین (بخش ۵ استفاده می‌کند) ----------------

def _fsm_admin_input(tg: int, text: str, states: dict, st, data) -> bool:
    try:
        from .handlers_admin import fsm_input
        return fsm_input(tg, text, states, st, data)
    except ImportError:
        states.pop(tg, None)
        return False
