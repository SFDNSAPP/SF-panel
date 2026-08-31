# -*- coding: utf-8 -*-
"""اندپوینت عمومی اشتراک — /sub/{token}"""

import re

from aiohttp import web

from core import database as db
from core.utils import now_ms
from core.link_builder import subscription_body, subscription_headers, \
    resolve_public_host

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-]{4,64}$")


async def sub_handler(request):
    token = request.match_info.get("token", "")
    if not _TOKEN_RE.match(token):
        return web.Response(status=404, text="Not Found")

    c = db.q("SELECT * FROM clients WHERE sub_id=?", (token,), one=True)
    if not c or not c["enable"]:
        return web.Response(status=404, text="Not Found")

    blocked = False
    if c["limit_bytes"] and (c["up"] + c["down"]) >= c["limit_bytes"]:
        blocked = True
    if c["expiry"] and c["expiry"] <= now_ms():
        blocked = True

    raw = request.query.get("raw") == "1"
    body = "" if blocked else subscription_body(
        c, host=resolve_public_host(request.host), raw=raw)

    db.ex("UPDATE clients SET last_seen=? WHERE id=?", (now_ms(), c["id"]))
    return web.Response(text=body, headers=subscription_headers(c))