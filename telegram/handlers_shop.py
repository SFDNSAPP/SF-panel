#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""دکمه‌های فروش — بخش ۴ از ۶
کیف پول · خرید · اکانت تست · ریفرال · نمایندگی · پشتیبانی
"""

import re
import time

from core.utils import fmt_bytes
from . import db as sdb
from . import texts
from . import panel_link
from .bot import (send_message, main_kb, back_kb, _states, now_ms,
                  base_url, _bot_username)
from .handlers_fsm import (STEP_DEPOSIT, STEP_COUPON, STEP_AGENT,
                           STEP_SUPPORT)

# حروف فارسی-انگلیسی اعداد
_FA = "۰۱۲۳۴۵۶۷۸۹"


def _fmt_toman(n) -> str:
    return f"{int(n or 0):,} تومان"


def route_callback(data: str, chat, cbq):
    tg = int(chat)
    u = sdb.ensure_user(tg)

    if data == "wallet":
        cb_wallet(tg)
    elif data == "deposit":
        cb_deposit(tg)
    elif data == "shop":
        cb_shop(tg)
    elif data.startswith("shop:plan:"):
        cb_plan(tg, data.split(":")[2])
    elif data.startswith("shop:nocoupon:"):
        cb_plan_direct(tg, data.split(":")[2])
    elif data.startswith("shop:pay:"):
        cb_pay(tg, data.split(":")[2])
    elif data == "trial":
        cb_trial(tg)
    elif data.startswith("trial:go"):
        cb_trial_go(tg)
    elif data == "referral":
        cb_referral(tg)
    elif data == "agent":
        cb_agent(tg)
    elif data == "support":
        cb_support(tg)


# ---------------- کیف پول ----------------

def cb_wallet(tg: int):
    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    kb = {"inline_keyboard": [
        [{"text": "➕ افزایش موجودی", "callback_data": "deposit"}],
        [{"text": "🔙 منو", "callback_data": "menu"}],
    ]}
    send_message(tg, texts.T["wallet"].format(
        balance=u["balance"] if u else 0), reply_markup=kb)


def cb_deposit(tg: int):
    _states[tg] = {"step": STEP_DEPOSIT, "data": {}}
    send_message(tg, texts.T["deposit_ask"].format(
        min_deposit=int(sdb.get_setting("min_deposit", "10000"))))


# ---------------- خرید ----------------

def cb_shop(tg: int):
    plans = sdb.q("SELECT * FROM plans WHERE is_active=1 ORDER BY sort, id")
    if not plans:
        send_message(tg, "فعلاً پلنی موجود نیست. با پشتیبانی در تماس باش.")
        return
    rows = []
    for p in plans:
        rows.append([{"text": f"{p['title']} — {p['price']:,} ت",
                      "callback_data": f"shop:plan:{p['id']}"}])
    rows.append([{"text": "🔙 منو", "callback_data": "menu"}])
    send_message(tg, texts.T["plans_title"],
                 reply_markup={"inline_keyboard": rows})


def _plan(pid):
    return sdb.q("SELECT * FROM plans WHERE id=? AND is_active=1",
                 (pid,), one=True)


def cb_plan(tg: int, pid: str):
    p = _plan(pid)
    if not p:
        send_message(tg, "این پلن دیگر فعال نیست.")
        return
    _states[tg] = {"step": STEP_COUPON,
                   "data": {"plan": dict(p), "price": p["price"]}}
    kb = {"inline_keyboard": [
        [{"text": "🚫 بدون کد تخفیف", "callback_data": f"shop:nocoupon:{pid}"}],
        [{"text": "🔙 انصراف", "callback_data": "menu"}],
    ]}
    send_message(tg, texts.T["plan_detail"].format(
        title=p["title"], days=p["days"], gb=p["limit_gb"],
        price=p["price"]), reply_markup=kb)


def cb_plan_direct(tg: int, pid: str):
    """بدون کد تخفیف → مستقیم فاکتور"""
    p = _plan(pid)
    if not p:
        send_message(tg, "این پلن دیگر فعال نیست.")
        return
    _states.pop(tg, None)
    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    kb = {"inline_keyboard": [
        [{"text": f"💳 پرداخت ({p['price']:,} تومان)",
          "callback_data": f"shop:pay:{pid}"}],
        [{"text": "🔙 انصراف", "callback_data": "menu"}],
    ]}
    send_message(tg, texts.T["invoice"].format(
        title=p["title"], price=p["price"], discount=0,
        final=p["price"], balance=u["balance"] if u else 0),
        reply_markup=kb)


def cb_pay(tg: int, pid: str):
    p = _plan(pid)
    if not p:
        send_message(tg, "این پلن دیگر فعال نیست.")
        return
    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    if not u or u["is_blocked"]:
        return

    # کد تخفیف؟
    st = _states.pop(tg, None)
    discount = 0
    coupon_code = None
    if st and st.get("data"):
        coupon_code = st["data"].get("coupon_code")
        if coupon_code:
            err, discount = sdb.check_coupon(coupon_code, p["price"], tg)
            if err:
                discount = 0
                coupon_code = None

    final = max(0, p["price"] - discount)

    if u["balance"] < final:
        send_message(tg, texts.T["no_balance"].format(
            need=final - u["balance"]))
        return

    # ساخت اکانت
    acc, err = panel_link.create_account(tg, p["days"], p["limit_gb"])
    if err or not acc:
        send_message(tg, f"❌ {err}")
        return

    # مالی: کسر + ثبت
    sdb.balance_add(tg, -final, "purchase",
                    f"پلن {p['title']} — اکانت {acc['email']}")
    if coupon_code:
        sdb.coupon_commit(coupon_code, tg)
    sdb.ex("UPDATE users SET buys_count=buys_count+1 WHERE tg_id=?", (tg,))
    sdb.ex("INSERT INTO bot_accounts(user_id,plan_id,email,sub_id,"
           "expires_at,limit_bytes,ts) VALUES(?,?,?,?,?,?,?)",
           (tg, p["id"], acc["email"], acc["sub_id"],
            acc["expires_at"], acc["limit_bytes"], now_ms()))

    # پاداش ریفرال
    if u["ref_by"]:
        percent = int(sdb.get_setting("ref_percent", "20"))
        reward = final * percent // 100
        if reward > 0:
            sdb.balance_add(u["ref_by"], reward, "referral",
                            f"خرید زیرمجموعه {tg}")
            sdb.ex("UPDATE users SET ref_earnings=ref_earnings+? "
                   "WHERE tg_id=?", (reward, u["ref_by"]))
            send_message(u["ref_by"],
                         f"🤝 خرید زیرمجموعه‌ات ثبت شد! "
                         f"<b>{reward:,} تومان</b> به کیف پولت اضافه شد.")

    base = base_url()
    send_message(tg, texts.T["buy_success"].format(
        email=acc["email"], days=p["days"] or "∞",
        gb=p["limit_gb"] or "∞",
        sub=f"{base}/sub/{acc['sub_id']}"), reply_markup=main_kb())


# ---------------- اکانت تست ----------------

def cb_trial(tg: int):
    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    cd_days = int(sdb.get_setting("trial_cooldown", "7"))
    if u["trial_last"]:
        passed = (now_ms() - u["trial_last"]) / 86400000
        if passed < cd_days:
            send_message(tg, texts.T["trial_wait"].format(
                days=int(cd_days - passed) + 1))
            return
    send_message(tg, texts.T["trial_get"],
                 reply_markup={"inline_keyboard": [[
                     {"text": "🎁 دریافت", "callback_data": "trial:go"},
                     {"text": "🔙 منو", "callback_data": "menu"}]]})


def cb_trial_go(tg: int):
    gb = int(sdb.get_setting("trial_gb", "1"))
    days = int(sdb.get_setting("trial_days", "1"))
    acc, err = panel_link.create_account(tg, days, gb)
    if err or not acc:
        send_message(tg, f"❌ {err}")
        return
    sdb.ex("UPDATE users SET trial_last=? WHERE tg_id=?", (now_ms(), tg))
    sdb.ex("INSERT INTO bot_accounts(user_id,plan_id,email,sub_id,"
           "expires_at,limit_bytes,ts) VALUES(0,0,?,?,?,?,?)",
           (acc["email"], acc["sub_id"], acc["expires_at"],
            acc["limit_bytes"], now_ms()))
    base = base_url()
    send_message(tg, texts.T["trial_ok"].format(
        email=acc["email"], gb=gb, days=days,
        sub=f"{base}/sub/{acc['sub_id']}"), reply_markup=main_kb())


# ---------------- ریفرال ----------------

def cb_referral(tg: int):
    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    refs = sdb.q("SELECT COUNT(*) n FROM users WHERE ref_by=?",
                 (tg,), one=True)["n"]
    bu = _bot_username()
    ref = (f"https://t.me/{bu}?start={u['ref_code']}"
           if bu else u["ref_code"])
    send_message(tg, texts.T["referral"].format(
        ref=ref, percent=sdb.get_setting("ref_percent", "20"),
        refs=refs, earn=u["ref_earnings"]), reply_markup=back_kb())


# ---------------- نمایندگی / پشتیبانی ----------------

def cb_agent(tg: int):
    _states[tg] = {"step": STEP_AGENT, "data": {}}
    send_message(tg, texts.T["agent_form"])


def cb_support(tg: int):
    _states[tg] = {"step": STEP_SUPPORT, "data": {}}
    send_message(tg, texts.T["support_ask"])
