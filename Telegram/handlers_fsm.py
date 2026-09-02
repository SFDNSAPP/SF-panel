# -*- coding: utf-8 -*-
"""گفتگوهای ربات فروش (FSM)
مبلغ شارژ · ارسال رسید · کد تخفیف · فرم نمایندگی · پیام پشتیبانی · ورودی ادمین
"""

from core import database as db
from . import db as sdb
from . import texts
from .bot import (
    send_message,
    main_kb,
    _states,
    _states_lock,
    now_ms,
    _admins_all,
    forward_photo_or_file,
)

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

    if text.strip().lower() in ("/cancel", "cancel", "انصراف"):
        with _states_lock:
            states.pop(tg, None)
        send_message(tg, texts.T["cancelled"], reply_markup=main_kb())
        return True

    step = st.get("step")
    data = st.setdefault("data", {})

    if step == STEP_DEPOSIT:
        return _fsm_deposit(tg, text, states)
    if step == STEP_RECEIPT:
        send_message(
            tg,
            "لطفاً <b>عکس یا فایل</b> رسید را بفرست (نه متن).\n"
            "برای انصراف /cancel بزن.",
        )
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
        amount = int(
            text.strip()
            .replace(",", "")
            .replace("،", "")
            .replace(" ", "")
        )
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

    with _states_lock:
        states[tg] = {"step": STEP_RECEIPT, "data": {"amount": amount}}

    send_message(
        tg,
        texts.T["deposit_card"].format(
            card=sdb.get_setting("card_number"),
            name=sdb.get_setting("card_name"),
            amount=amount,
        ),
    )
    return True


# ---------------- دریافت فایل رسید ----------------

def handle_media(msg: dict, chat: str):
    """عکس/فایل — اگر در حالت receipt بود → ثبت و اطلاع به ادمین‌ها"""
    tg = int(chat)
    with _states_lock:
        st = _states.get(tg)
        if not st or st.get("step") != STEP_RECEIPT:
            return
        amount = st.get("data", {}).get("amount", 0)
        if not amount:
            _states.pop(tg, None)
            return
        # state را اینجا پاک می‌کنیم تا دوباره ارسال نشود
        _states.pop(tg, None)

    file_id = ""
    if msg.get("photo"):
        file_id = msg["photo"][-1].get("file_id", "")
    elif msg.get("document"):
        file_id = msg["document"].get("file_id", "")

    rid = sdb.ex(
        "INSERT INTO receipts(user_id,amount,file_id,status,ts) "
        "VALUES(?,?,?,?,?)",
        (tg, amount, file_id, "pending", now_ms()),
    )

    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    uname = ("@" + u["username"]) if u and u.get("username") else "—"

    kb = {
        "inline_keyboard": [
            [
                {"text": "✅ تایید", "callback_data": f"adm:rcp:{rid}:ok"},
                {"text": "❌ رد", "callback_data": f"adm:rcp:{rid}:no"},
            ]
        ]
    }
    caption = (
        f"🧾 <b>رسید #{rid}</b>\n\n"
        f"👤 کاربر: <code>{tg}</code> {uname}\n"
        f"💰 مبلغ: <b>{amount:,} تومان</b>"
    )

    for admin in _admins_all():
        try:
            forward_photo_or_file(admin, int(chat), msg["message_id"])
            send_message(admin, caption, reply_markup=kb)
        except Exception:
            pass

    send_message(tg, texts.T["receipt_sent"], reply_markup=main_kb())


# ---------------- کد تخفیف ----------------

def _fsm_coupon(tg: int, text: str, states: dict, st, data) -> bool:
    raw = text.strip()
    discount = 0
    coupon_code = None

    if raw.lower() not in ("بدون", "skip", "ندارم", "no", "-", "بدون کد"):
        err, discount = sdb.check_coupon(raw, data.get("price", 0), tg)
        if err:
            send_message(
                tg,
                f"❌ {err}\n\nکد دیگری بفرست یا «بدون» بنویس:",
            )
            return True
        coupon_code = raw

    plan = data.get("plan", {})
    price = data.get("price", 0)
    final = max(0, price - discount)

    # مهم: کوپن را در data نگه می‌داریم تا موقع پرداخت استفاده شود
    data["coupon_code"] = coupon_code
    data["discount"] = discount
    data["final"] = final

    with _states_lock:
        # step را None می‌کنیم ولی data را نگه می‌داریم
        states[tg] = {"step": None, "data": data}

    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    kb = {
        "inline_keyboard": [
            [
                {
                    "text": f"💳 پرداخت ({final:,} تومان)",
                    "callback_data": f"shop:pay:{plan.get('id')}",
                }
            ],
            [{"text": "🔙 انصراف", "callback_data": "menu"}],
        ]
    }

    extra = (
        f"\n\n🎟 کد: <code>{texts.esc(coupon_code)}</code>"
        if coupon_code
        else ""
    )
    send_message(
        tg,
        texts.T["invoice"].format(
            title=plan.get("title", "?"),
            price=price,
            discount=discount,
            final=final,
            balance=u["balance"] if u else 0,
        )
        + extra,
        reply_markup=kb,
    )
    return True


# ---------------- نمایندگی ----------------

def _fsm_agent(tg: int, text: str, states: dict) -> bool:
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 3:
        send_message(
            tg,
            "❌ سه خط لازم است:\n"
            "<code>نام\nشماره تماس\nتوضیحات</code>",
        )
        return True

    name, phone, desc = lines[0], lines[1], " ".join(lines[2:])
    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    uname = ("@" + u["username"]) if u and u.get("username") else "—"

    for admin in _admins_all():
        send_message(
            admin,
            (
                f"🏪 <b>درخواست نمایندگی</b>\n\n"
                f"👤 <code>{tg}</code> {uname}\n"
                f"📛 نام: {texts.esc(name)}\n"
                f"📞 تماس: {texts.esc(phone)}\n"
                f"📝 {texts.esc(desc[:400])}"
            ),
        )

    with _states_lock:
        states.pop(tg, None)
    send_message(tg, texts.T["agent_sent"], reply_markup=main_kb())
    return True


# ---------------- پشتیبانی ----------------

def _fsm_support(tg: int, text: str, states: dict) -> bool:
    tid = sdb.ex(
        "INSERT INTO tickets(user_id,message,ts) VALUES(?,?,?)",
        (tg, text[:1000], now_ms()),
    )
    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    uname = ("@" + u["username"]) if u and u.get("username") else "—"

    for admin in _admins_all():
        send_message(
            admin,
            (
                f"💬 <b>تیکت #{tid}</b>\n"
                f"👤 <code>{tg}</code> {uname}\n\n"
                f"{texts.esc(text[:800])}"
            ),
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": "↩️ پاسخ",
                            "callback_data": f"adm:tik:{tid}",
                        }
                    ]
                ]
            },
        )

    with _states_lock:
        states.pop(tg, None)
    send_message(tg, texts.T["support_sent"], reply_markup=main_kb())
    return True


# ---------------- ورودی ادمین ----------------

def _fsm_admin_input(tg: int, text: str, states: dict, st, data) -> bool:
    try:
        from .handlers_admin import fsm_input
        return fsm_input(tg, text, states, st, data)
    except Exception:
        with _states_lock:
            states.pop(tg, None)
        return False
