# -*- coding: utf-8 -*-
"""پل مستقیم ربات↔پنل (همان پروسه — بدون API/توکن):
ساخت/تمدید اکانت، لینک‌ها، مصرف — مستقیم از core"""

import uuid as uuidlib

from core import database as pdb
from core import xray
from core.security import random_token, random_password
from core.utils import dump_json, now_ms
from core.link_builder import client_links


def create_account(tg_id: int, days: int, limit_gb: int):
    """→ (account_dict | None, error | None)"""
    inbs = [r["id"] for r in pdb.q("SELECT id FROM inbounds WHERE enable=1")]
    if not inbs:
        return None, "هیچ اینباند فعالی روی سرور وجود ندارد."

    base = f"shop{tg_id}"
    email = base
    n = 1
    while pdb.q("SELECT id FROM clients WHERE email=?", (email,), one=True):
        n += 1
        email = f"{base}-{n}"

    sub_id = random_token(9)
    while pdb.q("SELECT id FROM clients WHERE sub_id=?",
                (sub_id,), one=True):
        sub_id = random_token(9)

    limit = int(limit_gb) * 1073741824
    expiry = now_ms() + days * 86400000 if days else 0

    cid = pdb.ex(
        "INSERT INTO clients(email,uuid,password,flow,inbounds,expiry,"
        "limit_bytes,up,down,enable,tg_id,sub_id,note,notify80,notify_exp,"
        "last_seen,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (email, str(uuidlib.uuid4()), random_password(16), "",
         dump_json(inbs), expiry, limit, 0, 0, 1, "", sub_id,
         "خرید از ربات", 0, 0, 0, now_ms()))

    ok, err = xray.restart("خرید از ربات")
    if not ok:
        # rollback — پنل پاک بماند
        pdb.ex("DELETE FROM clients WHERE id=?", (cid,))
        try:
            xray.restart("rollback خرید")
        except Exception:
            pass
        return None, "خطای سرور در فعال‌سازی (هسته). لحظه‌ای بعد دوباره بزن."

    c = pdb.q("SELECT * FROM clients WHERE id=?", (cid,), one=True)
    return {"email": email, "sub_id": sub_id, "client": c,
            "expires_at": expiry, "limit_bytes": limit}, None


def extend_account(email: str, days: int = 0, add_gb: int = 0) -> bool:
    c = pdb.q("SELECT * FROM clients WHERE email=?", (email,), one=True)
    if not c:
        return False
    new_exp = (max(c["expiry"], now_ms()) + days * 86400000) \
        if days else c["expiry"]
    new_lim = (c["limit_bytes"] + add_gb * 1073741824) \
        if add_gb else c["limit_bytes"]
    pdb.ex("UPDATE clients SET expiry=?, limit_bytes=?, enable=1, "
           "notify80=0, notify_exp=0 WHERE id=?",
           (new_exp, new_lim, c["id"]))
    try:
        xray.restart("تمدید از ربات")
    except Exception:
        pass
    return True


def account_links(sub_id: str):
    c = pdb.q("SELECT * FROM clients WHERE sub_id=?", (sub_id,), one=True)
    if not c:
        return []
    return client_links(c)


def account_info(sub_id: str):
    c = pdb.q("SELECT * FROM clients WHERE sub_id=?", (sub_id,), one=True)
    if not c:
        return None
    return {"email": c["email"], "enable": bool(c["enable"]),
            "used": c["up"] + c["down"], "total": c["limit_bytes"],
            "expiry": c["expiry"]}
