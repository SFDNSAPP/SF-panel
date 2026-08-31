# -*- coding: utf-8 -*-
"""CRUD اینباند‌ها — اعتبارسنجی کامل + اعمال روی هسته."""

import re
import uuid as uuidlib

from core import config as cfg
from core import database as db
from core import inbound_builder as ibld
from core.security import random_token, random_password
from core.utils import load_json, dump_json, to_int, now_ms

from .common import (json_ok, json_err, body_json, auth_required,
                     path_int, apply_config)


def _taken_paths(exclude_id=None):
    out = {}
    for r in db.q("SELECT id, config FROM inbounds"):
        if exclude_id is not None and r["id"] == exclude_id:
            continue
        g = load_json(r["config"], {})
        out[r["id"]] = (g.get("path") or "")
    return out


def _port_conflict(port, exclude_id=None):
    """فقط حالت VPS — پورت‌ها واقعی‌اند و نباید تکراری شوند."""
    if cfg.PAAS:
        return None
    for r in db.q("SELECT id, config FROM inbounds"):
        if exclude_id is not None and r["id"] == exclude_id:
            continue
        g = load_json(r["config"], {})
        if to_int(g.get("port"), -1) == port:
            return f"پورت {port} در اینباند دیگری استفاده شده است."
    return None


def _create_ss_client(iid: int, remark: str, g: dict) -> None:
    """Shadowsocks تک‌کاربره است؛ کاربر اختصاصی می‌سازیم."""
    base = re.sub(r"[^\w\-]", "-", remark).strip("-") or "ss"
    email = base
    while db.q("SELECT id FROM clients WHERE email=?", (email,), one=True):
        email = base + "-" + random_token(3)
    db.ex(
        "INSERT INTO clients(email,uuid,password,flow,inbounds,expiry,limit_bytes,"
        "up,down,enable,tg_id,sub_id,note,notify80,notify_exp,last_seen,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (email, str(uuidlib.uuid4()), g.get("password") or random_password(16),
         "", dump_json([iid]), 0, 0, 0, 0, 1, "", random_token(9),
         "", 0, 0, 0, now_ms()))


@auth_required
async def api_list(request):
    clients = db.q("SELECT inbounds FROM clients")
    out = []
    for r in db.q("SELECT * FROM inbounds ORDER BY id"):
        out.append({
            "id": r["id"],
            "remark": r["remark"],
            "protocol": r["protocol"],
            "enable": bool(r["enable"]),
            "config": load_json(r["config"], {}),
            "up": r["up_total"],
            "down": r["down_total"],
            "clients": sum(1 for c in clients
                           if r["id"] in load_json(c["inbounds"], [])),
            "created_at": r["created_at"],
        })
    return json_ok(out)


@auth_required
async def api_create(request):
    d = await body_json(request)
    remark = (d.get("remark") or "").strip()[:60] or ("inbound-" + random_token(3))
    err, g = ibld.normalize_inbound(d.get("config") or {},
                                    cfg.PAAS, _taken_paths(), None)
    if err:
        return json_err(err)
    perr = _port_conflict(to_int(g.get("port"), 0))
    if perr:
        return json_err(perr)

    iid = db.ex(
        "INSERT INTO inbounds(remark,protocol,config,enable,internal_port,created_at) "
        "VALUES(?,?,?,?,1,?)",
        (remark, g["protocol"], dump_json(g),
         db.next_internal_port(), now_ms()))
    if g["protocol"] == "shadowsocks":
        _create_ss_client(iid, remark, g)

    ok, xerr = await apply_config()
    if not ok:
        return json_err(f"ذخیره شد اما هسته خطا داد: {xerr}", 500)
    db.log_event(f"اینباند «{remark}» ساخته شد", "ok")
    return json_ok({"id": iid})


@auth_required
async def api_update(request):
    iid = path_int(request)
    row = db.q("SELECT * FROM inbounds WHERE id=?", (iid,), one=True) \
        if iid is not None else None
    if not row:
        return json_err("اینباند یافت نشد.", 404)

    d = await body_json(request)
    remark = row["remark"]
    if d.get("remark") is not None:
        remark = (d.get("remark") or "").strip()[:60] or row["remark"]

    config = load_json(row["config"], {})
    if isinstance(d.get("config"), dict):
        config.update(d["config"])

    err, g = ibld.normalize_inbound(config, cfg.PAAS, _taken_paths(iid), iid)
    if err:
        return json_err(err)
    perr = _port_conflict(to_int(g.get("port"), 0), iid)
    if perr:
        return json_err(perr)

    db.ex("UPDATE inbounds SET remark=?, protocol=?, config=? WHERE id=?",
          (remark, g["protocol"], dump_json(g), iid))
    ok, xerr = await apply_config()
    if not ok:
        return json_err(f"بروزرسانی شد اما هسته خطا داد: {xerr}", 500)
    db.log_event(f"اینباند «{remark}» ویرایش شد", "info")
    return json_ok({"ok": True})


@auth_required
async def api_delete(request):
    iid = path_int(request)
    row = db.q("SELECT * FROM inbounds WHERE id=?", (iid,), one=True) \
        if iid is not None else None
    if not row:
        return json_err("اینباند یافت نشد.", 404)

    for c in db.q("SELECT id, inbounds FROM clients"):
        arr = load_json(c["inbounds"], [])
        if iid in arr:
            new = [x for x in arr if x != iid]
            db.ex("UPDATE clients SET inbounds=? WHERE id=?",
                  (dump_json(new), c["id"]))
    db.ex("DELETE FROM inbounds WHERE id=?", (iid,))
    ok, xerr = await apply_config()
    db.log_event(f"اینباند «{row['remark']}» حذف شد", "warn")
    return json_ok({"ok": True, "xray_error": None if ok else xerr})


@auth_required
async def api_toggle(request):
    iid = path_int(request)
    row = db.q("SELECT enable FROM inbounds WHERE id=?", (iid,), one=True) \
        if iid is not None else None
    if not row:
        return json_err("اینباند یافت نشد.", 404)
    new = 0 if row["enable"] else 1
    db.ex("UPDATE inbounds SET enable=? WHERE id=?", (new, iid))
    await apply_config()
    return json_ok({"ok": True, "enable": bool(new)})