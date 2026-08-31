# -*- coding: utf-8 -*-
"""نصب اولیه، ورود (+TOTP)، وضعیت عمومی."""

import uuid as uuidlib

from core import config as cfg
from core import database as db
from core import inbound_builder as ibld
from core.security import (hash_password, verify_password, issue_token,
                           totp_verify, login_limiter, random_token,
                           random_password)
from core.utils import dump_json, now_ms
from core.xray import xray

from .common import (json_ok, json_err, body_json, client_ip,
                     auth_required, run_ex, spawn_bg)


async def api_status(request):
    """عمومی — وضعیت کلی برای صفحه ورود (بدون اطلاعات حساس)."""
    xs = xray.state()
    return json_ok({
        "app": cfg.APP_NAME,
        "version": cfg.APP_VERSION,
        "paas": cfg.PAAS,
        "setup_done": bool(db.get_setting("admin_pass")),
        "xray": {"running": xs["running"], "starting": xs["starting"],
                 "version": xs["version"]},
    })


def seed_first_data() -> None:
    """اینباند و کاربر پیش‌فرض — فقط در اولین نصب."""
    if db.q("SELECT id FROM inbounds LIMIT 1", one=True):
        return
    g = ibld.seed_default(cfg.PAAS)
    iid = db.ex(
        "INSERT INTO inbounds(remark,protocol,config,enable,internal_port,created_at) "
        "VALUES(?,?,?,?,1,?)",
        ("SF-Default", g["protocol"], dump_json(g),
         db.next_internal_port(), now_ms()))
    db.ex(
        "INSERT INTO clients(email,uuid,password,flow,inbounds,expiry,limit_bytes,"
        "up,down,enable,tg_id,sub_id,note,notify80,notify_exp,last_seen,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("client-1", str(uuidlib.uuid4()), random_password(16), "",
         dump_json([iid]), 0, 0, 0, 0, 1, "", random_token(9),
         "", 0, 0, 0, now_ms()))
    db.log_event("اینباند و کاربر پیش‌فرض ساخته شد", "ok")


async def api_setup(request):
    if db.get_setting("admin_pass"):
        return json_err("نصب قبلاً انجام شده است.", 403)
    d = await body_json(request)
    username = (d.get("username") or "").strip()
    password = str(d.get("password") or "")
    if len(username) < 3:
        return json_err("نام کاربری حداقل ۳ کاراکتر باشد.")
    if len(password) < 6:
        return json_err("رمز عبور حداقل ۶ کاراکتر باشد.")
    db.set_setting("admin_user", username)
    db.set_setting("admin_pass", await run_ex(hash_password, password))
    seed_first_data()
    db.log_event(f"نصب تکمیل شد؛ مدیر: {username}", "ok")
    # راه‌اندازی هسته در پس‌زمینه (پاسخ سریع برمی‌گردد)
    spawn_bg(run_ex(xray.start))
    return json_ok({
        "token": issue_token(username, db.get_setting("secret")),
        "username": username,
    })


async def api_login(request):
    ip = client_ip(request)
    if not login_limiter.check(ip):
        return json_err("تلاش بیش از حد؛ چند دقیقه دیگر امتحان کنید.", 429)
    if not db.get_setting("admin_pass"):
        return json_err("نصب اولیه انجام نشده است.", 403)

    d = await body_json(request)
    username = (d.get("username") or "").strip()
    password = str(d.get("password") or "")

    stored_user = db.get_setting("admin_user")
    stored_pass = db.get_setting("admin_pass")
    pw_ok = (username == stored_user and stored_pass and
             await run_ex(verify_password, password, stored_pass))
    if not pw_ok:
        login_limiter.fail(ip)
        db.log_event(f"تلاش ورود ناموفق از {ip}", "warn")
        return json_err("نام کاربری یا رمز عبور نادرست است.", 401)

    if db.get_bool("totp_enabled", False):
        code = str(d.get("code") or "")
        if not totp_verify(db.get_setting("totp_secret"), code):
            login_limiter.fail(ip)
            return json_err("کد تأیید دومرحله‌ای نادرست است.", 401)

    login_limiter.reset(ip)
    db.log_event(f"ورود موفق: {username} ({ip})", "ok")
    return json_ok({
        "token": issue_token(username, db.get_setting("secret")),
        "username": username,
        "totp_enabled": db.get_bool("totp_enabled", False),
    })


@auth_required
async def api_me(request):
    return json_ok({
        "username": request["user"],
        "paas": cfg.PAAS,
        "totp_enabled": db.get_bool("totp_enabled", False),
    })