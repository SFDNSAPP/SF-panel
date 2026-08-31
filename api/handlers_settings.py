# -*- coding: utf-8 -*-
"""تنظیمات پنل، رمز، TOTP، ربات، پشتیبان‌گیری/بازیابی."""

import re
import secrets
import time

from aiohttp import web
import requests

from core import config as cfg
from core import database as db
from core.security import (hash_password, verify_password, issue_token,
                           totp_generate_secret, totp_verify, totp_uri)

from .common import (json_ok, json_err, body_json, auth_required,
                     run_ex, apply_config)

_RESET_MODES = ("off", "daily", "monthly")


@auth_required
async def api_get(request):
    return json_ok({
        "admin_user": db.get_setting("admin_user"),
        "public_domain": db.get_setting("public_domain"),
        "tg_token": db.get_setting("tg_token"),
        "tg_admins": db.get_setting("tg_admins"),
        "tg_notify": db.get_bool("tg_notify", True),
        "sub_title": db.get_setting("sub_title") or cfg.APP_NAME,
        "reset_mode": db.get_setting("reset_mode") or "off",
        "reset_day": db.get_int("reset_day", 1),
        "xray_version": db.get_setting("xray_version"),
        "totp_enabled": db.get_bool("totp_enabled", False),
    })


@auth_required
async def api_set(request):
    d = await body_json(request)

    if "public_domain" in d:
        dom = str(d.get("public_domain") or "").strip()
        if dom and not re.match(r"^[A-Za-z0-9.\-:]+$", dom):
            return json_err("دامنه/آدرس نامعتبر است.")
        db.set_setting("public_domain", dom)
        db.set_setting("host_cache", "")

    if "tg_token" in d:
        tok = str(d.get("tg_token") or "").strip()
        if tok and not re.match(r"^\d+:[\w\-]{30,}$", tok):
            return json_err("قالب توکن تلگرام نامعتبر است.")
        db.set_setting("tg_token", tok)

    if "tg_admins" in d:
        admins = str(d.get("tg_admins") or "").strip()
        for part in admins.split(","):
            if part.strip() and not part.strip().lstrip("-").isdigit():
                return json_err("شناسه‌های تلگرام باید عددی باشند.")
        db.set_setting("tg_admins", admins)

    if "tg_notify" in d:
        db.set_setting("tg_notify", "1" if d.get("tg_notify") else "0")

    if "sub_title" in d:
        db.set_setting("sub_title", str(d.get("sub_title") or "").strip()[:60])

    if "reset_mode" in d:
        mode = str(d.get("reset_mode") or "off").strip().lower()
        if mode not in _RESET_MODES:
            return json_err("حالت ریست نامعتبر است.")
        db.set_setting("reset_mode", mode)

    if "reset_day" in d:
        try:
            day = int(d.get("reset_day"))
        except (TypeError, ValueError):
            day = 0
        if not 1 <= day <= 28:
            return json_err("روز ریست باید بین ۱ تا ۲۸ باشد.")
        db.set_setting("reset_day", day)

    if "xray_version" in d:
        db.set_setting("xray_version",
                       str(d.get("xray_version") or "").strip()[:20])

    db.log_event("تنظیمات بروزرسانی شد", "info")
    return json_ok({"ok": True})


@auth_required
async def api_password(request):
    d = await body_json(request)
    old_ok = await run_ex(verify_password, str(d.get("old") or ""),
                          db.get_setting("admin_pass"))
    if not old_ok:
        return json_err("رمز فعلی نادرست است.")
    new = str(d.get("new") or "")
    if len(new) < 6:
        return json_err("رمز جدید حداقل ۶ کاراکتر باشد.")

    db.set_setting("admin_pass", await run_ex(hash_password, new))
    # چرخش کلید امضا → همه نشست‌های قبلی باطل می‌شوند
    db.set_setting("secret", secrets.token_hex(32))
    token = issue_token(request["user"], db.get_setting("secret"))
    db.log_event("رمز عبور تغییر کرد؛ نشست‌ها باطل شدند", "warn")
    return json_ok({"ok": True, "token": token})


# ---------------- TOTP ----------------

@auth_required
async def api_totp_setup(request):
    if db.get_bool("totp_enabled", False):
        return json_err("دومرحله‌ای فعال است؛ ابتدا غیرفعال کنید.")
    secret = totp_generate_secret()
    db.set_setting("totp_pending", secret)
    uri = totp_uri(secret, db.get_setting("admin_user") or "admin")
    return json_ok({"secret": secret, "uri": uri})


@auth_required
async def api_totp_enable(request):
    d = await body_json(request)
    secret = db.get_setting("totp_pending")
    if not secret:
        return json_err("ابتدا مرحله راه‌اندازی (setup) را انجام دهید.")
    if not totp_verify(secret, str(d.get("code") or "")):
        return json_err("کد نادرست است.")
    db.set_setting("totp_secret", secret)
    db.set_setting("totp_enabled", "1")
    db.set_setting("totp_pending", "")
    db.log_event("ورود دومرحله‌ای فعال شد", "ok")
    return json_ok({"ok": True})


@auth_required
async def api_totp_disable(request):
    d = await body_json(request)
    pw_ok = await run_ex(verify_password, str(d.get("password") or ""),
                         db.get_setting("admin_pass"))
    if not pw_ok:
        return json_err("رمز عبور نادرست است.")
    db.set_setting("totp_enabled", "0")
    db.set_setting("totp_secret", "")
    db.set_setting("totp_pending", "")
    db.log_event("ورود دومرحله‌ای غیرفعال شد", "warn")
    return json_ok({"ok": True})


# ---------------- تلگرام ----------------

@auth_required
async def api_tg_test(request):
    tok = db.get_setting("tg_token")
    if not tok:
        return json_err("ابتدا توکن ربات را ذخیره کنید.")
    try:
        r = requests.get(f"https://api.telegram.org/bot{tok}/getMe",
                         timeout=12).json()
    except Exception as e:
        return json_err(f"خطای اتصال به تلگرام: {e}")
    if r.get("ok"):
        return json_ok({"ok": True,
                        "bot": "@" + str(r["result"].get("username", ""))})
    return json_err("پاسخ تلگرام: " + str(r.get("description", "خطا")))


# ---------------- پشتیبان‌گیری ----------------

@auth_required
async def api_backup(request):
    data = db.export_all()
    fname = f"sfpanel-backup-{time.strftime('%Y%m%d-%H%M%S')}.json"
    return web.json_response(
        data, headers={"Content-Disposition":
                       f'attachment; filename="{fname}"'})


@auth_required
async def api_restore(request):
    try:
        data = await request.json()
    except Exception:
        return json_err("فایل JSON نامعتبر است.")
    try:
        counts = await run_ex(db.import_all, data)
    except ValueError as e:
        return json_err(str(e))
    except Exception as e:
        return json_err(f"بازیابی ناموفق: {e}")

    ok, xerr = await apply_config()
    db.log_event(f"بازیابی پشتیبان: {counts}", "warn")
    return json_ok({"ok": True, **counts,
                    "xray_error": None if ok else xerr})