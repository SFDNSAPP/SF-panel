# -*- coding: utf-8 -*-
"""دکمه‌های فروش
کیف پول · خرید · اکانت تست · ریفرال · نمایندگی · پشتیبانی
"""

from . import db as sdb
from . import texts
from . import panel_link
from .bot import (
    send_message,
    main_kb,
    back_kb,
    _states,
    _states_lock,
    now_ms,
    base_url,
    _bot_username,
)
from .handlers_fsm import (
    STEP_DEPOSIT,
    STEP_COUPON,
    STEP_AGENT,
    STEP_SUPPORT,
)


def _fmt_toman(n) -> str:
    return f"{int(n or 0):,} تومان"


def _send_account_details(tg: int, acc: dict, days, gb):
    """ارسال کامل اطلاعات اکانت: ساب + کانفیگ‌ها + QR"""
    base = base_url()
    sub_url = f"{base}/sub/{acc['sub_id']}"

    # پیام اصلی موفقیت
    send_message(
        tg,
        texts.T["buy_success"].format(
            email=acc["email"],
            days=days or "∞",
            gb=gb or "∞",
            sub=sub_url,
        ),
        reply_markup=main_kb(),
    )

    # ارسال لینک‌های کانفیگ (vless / vmess / ...)
    links = acc.get("links") or []
    if links:
        configs_txt = "📡 <b>کانفیگ‌های مستقیم:</b>\n\n"
        for i, lk in enumerate(links[:6], 1):  # حداکثر ۶ تا
            name = texts.esc(lk.get("remark") or lk.get("name") or f"#{i}")
            link = lk.get("link") or ""
            configs_txt += f"<b>{i}. {name}</b>\n<code>{link}</code>\n\n"
        send_message(tg, configs_txt)

    # ارسال QR کد (اولین لینک یا ساب)
    try:
        import io
        import qrcode
        import requests
        from core import database as panel_db

        qr_data = links[0]["link"] if links else sub_url
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        token = panel_db.get_setting("tg_token")
        if token:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={
                    "chat_id": tg,
                    "caption": "📱 QR Code — اسکن کن یا لینک ساب رو کپی کن",
                },
                files={"photo": ("qr.png", buf, "image/png")},
                timeout=20,
            )
    except Exception:
        # اگر qrcode نصب نبود یا خطا خورد، فقط لینک ساب کافیست
        pass


def route_callback(data: str, chat, cbq):
    tg = int(chat)
    sdb.ensure_user(tg)

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
    kb = {
        "inline_keyboard": [
            [{"text": "➕ افزایش موجودی", "callback_data": "deposit"}],
            [{"text": "🔙 منو", "callback_data": "menu"}],
        ]
    }
    send_message(
        tg,
        texts.T["wallet"].format(balance=u["balance"] if u else 0),
        reply_markup=kb,
    )


def cb_deposit(tg: int):
    with _states_lock:
        _states[tg] = {"step": STEP_DEPOSIT, "data": {}}
    send_message(
        tg,
        texts.T["deposit_ask"].format(
            min_deposit=int(sdb.get_setting("min_deposit", "10000"))
        ),
    )


# ---------------- خرید ----------------

def cb_shop(tg: int):
    plans = sdb.q(
        "SELECT * FROM plans WHERE is_active=1 ORDER BY sort, id"
    )
    if not plans:
        send_message(
            tg, "فعلاً پلنی موجود نیست. با پشتیبانی در تماس باش."
        )
        return
    rows = []
    for p in plans:
        rows.append(
            [
                {
                    "text": f"{p['title']} — {p['price']:,} ت",
                    "callback_data": f"shop:plan:{p['id']}",
                }
            ]
        )
    rows.append([{"text": "🔙 منو", "callback_data": "menu"}])
    send_message(
        tg,
        texts.T["plans_title"],
        reply_markup={"inline_keyboard": rows},
    )


def _plan(pid):
    return sdb.q(
        "SELECT * FROM plans WHERE id=? AND is_active=1", (pid,), one=True
    )


def cb_plan(tg: int, pid: str):
    p = _plan(pid)
    if not p:
        send_message(tg, "این پلن دیگر فعال نیست.")
        return

    with _states_lock:
        _states[tg] = {
            "step": STEP_COUPON,
            "data": {"plan": dict(p), "price": p["price"]},
        }

    kb = {
        "inline_keyboard": [
            [
                {
                    "text": "🚫 بدون کد تخفیف",
                    "callback_data": f"shop:nocoupon:{pid}",
                }
            ],
            [{"text": "🔙 انصراف", "callback_data": "menu"}],
        ]
    }
    send_message(
        tg,
        texts.T["plan_detail"].format(
            title=p["title"],
            days=p["days"],
            gb=p["limit_gb"],
            price=p["price"],
        ),
        reply_markup=kb,
    )


def cb_plan_direct(tg: int, pid: str):
    """بدون کد تخفیف → مستقیم فاکتور"""
    p = _plan(pid)
    if not p:
        send_message(tg, "این پلن دیگر فعال نیست.")
        return

    # data را با تخفیف صفر نگه می‌داریم
    with _states_lock:
        _states[tg] = {
            "step": None,
            "data": {
                "plan": dict(p),
                "price": p["price"],
                "coupon_code": None,
                "discount": 0,
                "final": p["price"],
            },
        }

    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    kb = {
        "inline_keyboard": [
            [
                {
                    "text": f"💳 پرداخت ({p['price']:,} تومان)",
                    "callback_data": f"shop:pay:{pid}",
                }
            ],
            [{"text": "🔙 انصراف", "callback_data": "menu"}],
        ]
    }
    send_message(
        tg,
        texts.T["invoice"].format(
            title=p["title"],
            price=p["price"],
            discount=0,
            final=p["price"],
            balance=u["balance"] if u else 0,
        ),
        reply_markup=kb,
    )


def cb_pay(tg: int, pid: str):
    """پرداخت atomic — اول پول کم می‌شود، بعد اکانت ساخته می‌شود"""
    p = _plan(pid)
    if not p:
        send_message(tg, "این پلن دیگر فعال نیست.")
        return

    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    if not u or u.get("is_blocked"):
        return

    # خواندن اطلاعات کوپن از state (پاک نمی‌کنیم تا بعد از موفقیت)
    with _states_lock:
        st = _states.get(tg) or {}
        data = st.get("data") or {}

    discount = int(data.get("discount") or 0)
    coupon_code = data.get("coupon_code")
    final = max(0, p["price"] - discount)

    # اگر state خالی بود (مثلاً کاربر دکمه قدیمی زده)، قیمت اصلی را بگیر
    if "final" in data:
        final = max(0, int(data["final"]))

    if u["balance"] < final:
        send_message(
            tg,
            texts.T["no_balance"].format(need=final - u["balance"]),
        )
        return

    # ۱. کسر امن موجودی
    ok = sdb.balance_deduct_safe(
        tg,
        final,
        "purchase",
        f"پلن {p['title']}",
    )
    if not ok:
        send_message(
            tg,
            texts.T["no_balance"].format(need=final - u["balance"]),
        )
        return

    # ۲. ساخت اکانت
    acc, err = panel_link.create_account(tg, p["days"], p["limit_gb"])
    if err or not acc:
        # برگشت پول
        sdb.balance_add(tg, final, "refund", f"خطا در ساخت اکانت: {err}")
        send_message(tg, f"❌ {err or 'خطا در ساخت اکانت'}\nموجودی برگشت داده شد.")
        return

    # ۳. ثبت کوپن (اگر بود)
    if coupon_code:
        try:
            sdb.coupon_commit(coupon_code, tg)
        except Exception:
            pass

    # ۴. ثبت اکانت در دیتابیس ربات
    sdb.ex(
        "UPDATE users SET buys_count = buys_count + 1 WHERE tg_id=?",
        (tg,),
    )
    sdb.ex(
        "INSERT INTO bot_accounts(user_id,plan_id,email,sub_id,"
        "expires_at,limit_bytes,ts) VALUES(?,?,?,?,?,?,?)",
        (
            tg,
            p["id"],
            acc["email"],
            acc["sub_id"],
            acc["expires_at"],
            acc["limit_bytes"],
            now_ms(),
        ),
    )

    # ۵. پاداش ریفرال
    if u.get("ref_by"):
        try:
            percent = int(sdb.get_setting("ref_percent", "20"))
            reward = final * percent // 100
            if reward > 0:
                sdb.balance_add(
                    u["ref_by"],
                    reward,
                    "referral",
                    f"خرید زیرمجموعه {tg}",
                )
                sdb.ex(
                    "UPDATE users SET ref_earnings = ref_earnings + ? "
                    "WHERE tg_id=?",
                    (reward, u["ref_by"]),
                )
                send_message(
                    u["ref_by"],
                    f"🤝 خرید زیرمجموعه‌ات ثبت شد!\n"
                    f"<b>{reward:,} تومان</b> به کیف پولت اضافه شد.",
                )
        except Exception:
            pass

    # ۶. پاک کردن state
    with _states_lock:
        _states.pop(tg, None)

    _send_account_details(tg, acc, p["days"], p["limit_gb"])


# ---------------- اکانت تست ----------------

def cb_trial(tg: int):
    u = sdb.q("SELECT * FROM users WHERE tg_id=?", (tg,), one=True)
    if not u:
        return
    cd_days = int(sdb.get_setting("trial_cooldown", "7"))
    if u.get("trial_last"):
        passed = (now_ms() - u["trial_last"]) / 86400000
        if passed < cd_days:
            send_message(
                tg,
                texts.T["trial_wait"].format(
                    days=max(1, int(cd_days - passed) + 1)
                ),
            )
            return

    send_message(
        tg,
        texts.T["trial_get"],
        reply_markup={
            "inline_keyboard": [
                [
                    {"text": "🎁 دریافت", "callback_data": "trial:go"},
                    {"text": "🔙 منو", "callback_data": "menu"},
                ]
            ]
        },
    )


def cb_trial_go(tg: int):
    gb = int(sdb.get_setting("trial_gb", "1"))
    days = int(sdb.get_setting("trial_days", "1"))

    # جلوگیری از چندبار زدن دکمه
    u = sdb.q("SELECT trial_last FROM users WHERE tg_id=?", (tg,), one=True)
    cd_days = int(sdb.get_setting("trial_cooldown", "7"))
    if u and u.get("trial_last"):
        passed = (now_ms() - u["trial_last"]) / 86400000
        if passed < cd_days:
            send_message(tg, "⏳ قبلاً اکانت تست گرفته‌ای.")
            return

    acc, err = panel_link.create_account(tg, days, gb)
    if err or not acc:
        send_message(tg, f"❌ {err}")
        return

    sdb.ex(
        "UPDATE users SET trial_last=? WHERE tg_id=?", (now_ms(), tg)
    )
    sdb.ex(
        "INSERT INTO bot_accounts(user_id,plan_id,email,sub_id,"
        "expires_at,limit_bytes,ts) VALUES(?,0,?,?,?,?,?)",
        (
            tg,
            acc["email"],
            acc["sub_id"],
            acc["expires_at"],
            acc["limit_bytes"],
            now_ms(),
        ),
    )

    _send_account_details(tg, acc, days, gb)


# ---------------- ریفرال ----------------

def cb_referral(tg: int):
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
        tg,
        texts.T["referral"].format(
            ref=ref,
            percent=sdb.get_setting("ref_percent", "20"),
            refs=refs,
            earn=u.get("ref_earnings") or 0,
        ),
        reply_markup=back_kb(),
    )


# ---------------- نمایندگی / پشتیبانی ----------------

def cb_agent(tg: int):
    with _states_lock:
        _states[tg] = {"step": STEP_AGENT, "data": {}}
    send_message(tg, texts.T["agent_form"])


def cb_support(tg: int):
    with _states_lock:
        _states[tg] = {"step": STEP_SUPPORT, "data": {}}
    send_message(tg, texts.T["support_ask"])
