# -*- coding: utf-8 -*-
"""CRUD کاربران — اعتبارسنجی، لینک‌ها، آمار روزانه."""

import re
import uuid as uuidlib

from core import config as cfg
from core import database as db
from core.security import random_password
from core.utils import load_json, dump_json, now_ms
from core.link_builder import client_links, resolve_public_host

from .common import (json_ok, json_err, body_json, auth_required,
                     path_int, apply_config)

_EMAIL_RE = re.compile(r"^[\w.\-@ ]{1,64}$", re.UNICODE)
_FLOWS = ("", "xtls-rprx-vision")


def _parse_client(d: dict):
    """→ (خطا | None, payload | None)"""
    email = str(d.get("email") or "").strip()
    if not _EMAIL_RE.match(email):
        return "نام کاربر (ایمیل) نامعتبر است — حروف، عدد، @ . - _", None

    uuid_v = str(d.get("uuid") or "").strip()
    if uuid_v:
        try:
            uuid_v = str(uuidlib.UUID(uuid_v))
        except ValueError:
            return "UUID نامعتبر است.", None
    else:
        uuid_v = str(uuidlib.uuid4())

    inb = []
    for x in (d.get("inbounds") or []):
        try:
            inb.append(int(x))
        except (TypeError, ValueError):
            pass
    valid_ids = {r["id"] for r in db.q("SELECT id FROM inbounds")}
    inb = [x for x in dict.fromkeys(inb) if x in valid_ids]
    if not inb:
        return "حداقل یک اینباند انتخاب کنید.", None

    try:
        expiry = max(0, int(d.get("expiry") or 0))
        limit_bytes = max(0, int(d.get("limit_bytes") or 0))
    except (TypeError, ValueError):
        return "مقادیر حجم/انقضا نامعتبر است.", None

    flow = str(d.get("flow") or "").strip()
    if flow not in _FLOWS:
        return "فلوِ فقط می‌تواند xtls-rprx-vision یا خالی باشد.", None

    password = str(d.get("password") or "").strip() or random_password(16)

    return None, {
        "email": email, "uuid": uuid_v, "password": password, "flow": flow,
        "inbounds": inb, "expiry": expiry, "limit_bytes": limit_bytes,
        "tg_id": str(d.get("tg_id") or "").strip()[:32],
        "note": str(d.get("note") or "").strip()[:200],
        "enable": 1 if d.get("enable", True) else 0,
    }


def _ss_conflict(inbound_ids, exclude_client=None):
    ss_ids = {r["id"] for r in db.q("SELECT id, protocol FROM inbounds")
              if r["protocol"] == "shadowsocks" and r["id"] in inbound_ids}
    if not ss_ids:
        return None
    for c in db.q("SELECT id, inbounds FROM clients"):
        if exclude_client and c["id"] == exclude_client:
            continue
        if ss_ids & set(load_json(c["inbounds"], [])):
            return "اینباند Shadowsocks تک‌کاربره است و قبلاً کاربر دارد."
    return None


_CLIENT_COLS = ("email,uuid,password,flow,inbounds,expiry,limit_bytes,"
                "up,down,enable,tg_id,sub_id,note,notify80,notify_exp,"
                "last_seen,created_at")


@auth_required
async def api_list(request):
    names = {i["id"]: i["remark"] for i in
             db.q("SELECT id, remark FROM inbounds")}
    out = []
    for c in db.q("SELECT * FROM clients ORDER BY id DESC"):
        arr = load_json(c["inbounds"], [])
        out.append({
            "id": c["id"], "email": c["email"], "uuid": c["uuid"],
            "password": c["password"], "flow": c["flow"],
            "inbounds": arr,
            "inbound_names": [names.get(i, "؟") for i in arr],
            "expiry": c["expiry"], "limit_bytes": c["limit_bytes"],
            "up": c["up"], "down": c["down"], "used": c["up"] + c["down"],
            "enable": bool(c["enable"]), "tg_id": c["tg_id"],
            "sub_id": c["sub_id"], "note": c["note"],
            "last_seen": c["last_seen"], "created_at": c["created_at"],
        })
    return json_ok(out)


@auth_required
async def api_create(request):
    d = await body_json(request)
    err, p = _parse_client(d)
    if err:
        return json_err(err)
    if db.q("SELECT id FROM clients WHERE email=?", (p["email"],), one=True):
        return json_err("این نام کاربر قبلاً استفاده شده است.")
    if db.q("SELECT id FROM clients WHERE uuid=?", (p["uuid"],), one=True):
        return json_err("این UUID تکراری است.")
    serr = _ss_conflict(p["inbounds"])
    if serr:
        return json_err(serr)

    from core.security import random_token
    sub_id = random_token(9)
    while db.q("SELECT id FROM clients WHERE sub_id=?", (sub_id,), one=True):
        sub_id = random_token(9)

    cid = db.ex(
        f"INSERT INTO clients({_CLIENT_COLS}) "
        f"VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (p["email"], p["uuid"], p["password"], p["flow"],
         dump_json(p["inbounds"]), p["expiry"], p["limit_bytes"],
         0, 0, p["enable"], p["tg_id"], sub_id, p["note"],
         0, 0, 0, now_ms()))

    ok, xerr = await apply_config()
    if not ok:
        return json_err(f"کاربر ذخیره شد اما هسته خطا داد: {xerr}", 500)
    db.log_event(f"کاربر «{p['email']}» اضافه شد", "ok")
    return json_ok({"id": cid})


@auth_required
async def api_update(request):
    cid = path_int(request)
    c = db.q("SELECT * FROM clients WHERE id=?", (cid,), one=True) \
        if cid is not None else None
    if not c:
        return json_err("کاربر یافت نشد.", 404)

    d = await body_json(request)
    merged = {
        "email": d.get("email", c["email"]),
        "uuid": d.get("uuid", c["uuid"]),
        "password": d.get("password", c["password"]),
        "flow": d.get("flow", c["flow"]),
        "inbounds": d.get("inbounds", load_json(c["inbounds"], [])),
        "expiry": d.get("expiry", c["expiry"]),
        "limit_bytes": d.get("limit_bytes", c["limit_bytes"]),
        "tg_id": d.get("tg_id", c["tg_id"]),
        "note": d.get("note", c["note"]),
        "enable": d.get("enable", bool(c["enable"])),
    }
    err, p = _parse_client(merged)
    if err:
        return json_err(err)

    if db.q("SELECT id FROM clients WHERE email=? AND id<>?",
            (p["email"], cid), one=True):
        return json_err("این نام کاربر قبلاً استفاده شده است.")
    if db.q("SELECT id FROM clients WHERE uuid=? AND id<>?",
            (p["uuid"], cid), one=True):
        return json_err("این UUID تکراری است.")
    serr = _ss_conflict(p["inbounds"], cid)
    if serr:
        return json_err(serr)

    db.ex(
        "UPDATE clients SET email=?,uuid=?,password=?,flow=?,inbounds=?,"
        "expiry=?,limit_bytes=?,enable=?,tg_id=?,note=? WHERE id=?",
        (p["email"], p["uuid"], p["password"], p["flow"],
         dump_json(p["inbounds"]), p["expiry"], p["limit_bytes"],
         p["enable"], p["tg_id"], p["note"], cid))

    ok, xerr = await apply_config()
    if not ok:
        return json_err(f"ذخیره شد اما هسته خطا داد: {xerr}", 500)
    db.log_event(f"کاربر «{p['email']}» ویرایش شد", "info")
    return json_ok({"ok": True})


@auth_required
async def api_delete(request):
    cid = path_int(request)
    c = db.q("SELECT email FROM clients WHERE id=?", (cid,), one=True) \
        if cid is not None else None
    if not c:
        return json_err("کاربر یافت نشد.", 404)
    db.ex("DELETE FROM clients WHERE id=?", (cid,))
    db.ex("DELETE FROM daily_clients WHERE email=?", (c["email"],))
    ok, xerr = await apply_config()
    db.log_event(f"کاربر «{c['email']}» حذف شد", "warn")
    return json_ok({"ok": True, "xray_error": None if ok else xerr})


@auth_required
async def api_toggle(request):
    cid = path_int(request)
    row = db.q("SELECT enable FROM clients WHERE id=?", (cid,), one=True) \
        if cid is not None else None
    if not row:
        return json_err("کاربر یافت نشد.", 404)
    new = 0 if row["enable"] else 1
    if new == 1:
        c = db.q("SELECT * FROM clients WHERE id=?", (cid,), one=True)
        if ((c["limit_bytes"] and c["up"] + c["down"] >= c["limit_bytes"])
                or (c["expiry"] and c["expiry"] <= now_ms())):
            return json_err("حجم یا اعتبار این کاربر تمام است؛ "
                            "ابتدا ریست یا افزایش دهید.")
    db.ex("UPDATE clients SET enable=? WHERE id=?", (new, cid))
    await apply_config()
    return json_ok({"ok": True, "enable": bool(new)})


@auth_required
async def api_reset(request):
    cid = path_int(request)
    if not cid or not db.q("SELECT id FROM clients WHERE id=?",
                           (cid,), one=True):
        return json_err("کاربر یافت نشد.", 404)
    db.ex("UPDATE clients SET up=0, down=0, notify80=0, notify_exp=0 "
          "WHERE id=?", (cid,))
    db.log_event("آمار کاربر ریست شد", "info")
    return json_ok({"ok": True})


@auth_required
async def api_links(request):
    cid = path_int(request)
    c = db.q("SELECT * FROM clients WHERE id=?", (cid,), one=True) \
        if cid is not None else None
    if not c:
        return json_err("کاربر یافت نشد.", 404)

    host = resolve_public_host(request.host)
    links = client_links(c, host=host)

    if cfg.PAAS:
        sub_url = f"https://{host}/sub/{c['sub_id']}"
    else:
        sub_url = f"{request.scheme}://{request.host}/sub/{c['sub_id']}"

    return json_ok({
        "email": c["email"],
        "links": links,
        "sub_url": sub_url,
        "bind_code": c["sub_id"],
        "up": c["up"],
        "used": c["up"] + c["down"],
        "total": c["limit_bytes"],
        "expire": c["expiry"] // 1000 if c["expiry"] else 0,
        "enabled": bool(c["enable"]),
    })


@auth_required
async def api_traffic(request):
    cid = path_int(request)
    c = db.q("SELECT email FROM clients WHERE id=?", (cid,), one=True) \
        if cid is not None else None
    if not c:
        return json_err("کاربر یافت نشد.", 404)
    rows = db.q("SELECT day, up, down FROM daily_clients WHERE email=? "
                "ORDER BY day DESC LIMIT 30", (c["email"],))
    rows.reverse()
    return json_ok({"email": c["email"], "days": rows})