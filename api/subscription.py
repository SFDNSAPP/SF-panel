# -*- coding: utf-8 -*-
"""Subscription endpoint — /sub/{token}
اپ‌ها: لینک‌ها + هدر Subscription-Userinfo
مرورگر: صفحه داشبورد (قالب از web/sub_page.html خوانده می‌شود)"""

import base64
import json
import os
import re

from aiohttp import web

from core import config as cfg
from core import database as db
from core.utils import now_ms
from core.link_builder import client_links, resolve_public_host

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-]{4,64}$")
_PAGE_PATH = os.path.join(cfg.BASE_DIR, "web", "sub_page.html")

_APP_UA = ("v2ray", "hiddify", "sing-box", "singbox", "clash",
           "shadowrocket", "streisand", "nekobox", "nekoray", "karing",
           "husi", "loon", "quantumult", "surge", "okhttp", "ktor",
           "dart", "curl", "wget", "python-requests",
           "python-urllib", "axios", "java/", "go-http-client",
           "apache-httpclient")

_I18N = {
    "en": {
        "subscription": "Subscription", "status": "Status",
        "st_active": "Active", "st_disabled": "Disabled",
        "st_expired": "Expired", "st_limit": "Data limit reached",
        "usage": "Data usage", "remaining": "Remaining",
        "unlimited": "Unlimited", "upload": "Upload",
        "download": "Download", "expiry": "Expiry",
        "never": "Never expires", "expired": "Expired",
        "days": "days", "hours": "hours", "minutes": "minutes",
        "left": "left", "expireDate": "Expires on",
        "serverLatency": "Server latency", "measuring": "measuring…",
        "subscriptionUrl": "Subscription URL",
        "copySub": "Copy subscription URL",
        "tip": "Add this URL to your app (v2rayNG / Hiddify / etc.) to "
               "auto-update configs and see usage inside the app.",
        "configs": "Configurations", "noConfigs": "No active configurations",
        "copy": "Copy", "copied": "Copied ✓", "showQr": "Show QR",
        "hideQr": "Hide QR", "refresh": "Refresh",
        "poweredBy": "Powered by SF-Panel",
        "tipExpired": "This subscription has expired. Contact your "
                      "provider to renew.",
        "tipLimit": "Data limit reached. The configuration is disabled.",
        "tipDisabled": "This subscription is disabled by the administrator.",
    },
    "fa": {
        "subscription": "اشتراک", "status": "وضعیت",
        "st_active": "فعال", "st_disabled": "غیرفعال",
        "st_expired": "منقضی شده", "st_limit": "حجم تمام شده",
        "usage": "مصرف داده", "remaining": "باقی‌مانده",
        "unlimited": "نامحدود", "upload": "آپلود", "download": "دانلود",
        "expiry": "اعتبار", "never": "بدون انقضا", "expired": "منقضی",
        "days": "روز", "hours": "ساعت", "minutes": "دقیقه",
        "left": "مانده", "expireDate": "تاریخ انقضا",
        "serverLatency": "تاخیر سرور", "measuring": "در حال اندازه‌گیری…",
        "subscriptionUrl": "لینک اشتراک",
        "copySub": "کپی لینک اشتراک",
        "tip": "این لینک را در اپ خود (v2rayNG / Hiddify و…) به‌عنوان "
               "Subscription اضافه کن تا کانفیگ‌ها خودکار بروز شوند و "
               "مصرف داخل اپ هم نمایش داده شود.",
        "configs": "کانفیگ‌ها", "noConfigs": "کانفیگ فعالی وجود ندارد",
        "copy": "کپی", "copied": "کپی شد ✓", "showQr": "نمایش QR",
        "hideQr": "بستن QR", "refresh": "بروزرسانی",
        "poweredBy": "قدرت‌گرفته از SF-Panel",
        "tipExpired": "این اشتراک منقضی شده است. برای تمدید با "
                      "فروشنده خود تماس بگیر.",
        "tipLimit": "حجم مصرفی به پایان رسید و کانفیگ غیرفعال شد.",
        "tipDisabled": "این اشتراک توسط مدیر غیرفعال شده است.",
    },
}


def _wants_html(request) -> bool:
    if request.query.get("web") == "1":
        return True
    if request.query.get("raw") == "1":
        return False
    ua = (request.headers.get("User-Agent") or "").lower()
    if not ua:
        return False
    if any(k in ua for k in _APP_UA):
        return False
    return "mozilla" in ua


def _qr_svg(text: str) -> str:
    try:
        import qrcode
        qr = qrcode.QRCode(border=2,
                           error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(text)
        qr.make(fit=True)
        m = qr.get_matrix()
        n = len(m)
        rects = "".join(
            f'<rect x="{x}" y="{y}" width="1" height="1"/>'
            for y, row in enumerate(m) for x, v in enumerate(row) if v)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'viewBox="0 0 {n} {n}" shape-rendering="crispEdges">'
                f'<rect width="{n}" height="{n}" fill="#ffffff"/>'
                f'<g fill="#03110b">{rects}</g></svg>')
    except Exception:
        return ""


def _render_page(c, links, sub_url, blocked):
    remaining_ms = (c["expiry"] - now_ms()) if c["expiry"] else None
    expired = bool(c["expiry"] and c["expiry"] <= now_ms())
    over = bool(c["limit_bytes"]
                and (c["up"] + c["down"]) >= c["limit_bytes"])
    status = ("expired" if expired else
              "limit" if over else
              "disabled" if not c["enable"] else "active")
    data = {
        "email": c["email"], "status": status,
        "used": c["up"] + c["down"], "total": c["limit_bytes"],
        "up": c["up"], "down": c["down"],
        "expire": c["expiry"] // 1000 if c["expiry"] else 0,
        "remaining_ms": remaining_ms,
        "links": [{"name": l["name"], "link": l["link"],
                   "protocol": l["protocol"], "qr": _qr_svg(l["link"])}
                  for l in links],
        "qr_sub": _qr_svg(sub_url), "sub_url": sub_url,
        "title": db.get_setting("sub_title") or cfg.APP_NAME,
        "blocked": blocked,
    }
    try:
        with open(_PAGE_PATH, "r", encoding="utf-8") as f:
            tpl = f.read()
    except OSError:
        # قالب موجود نیست → متن خام برگردان
        return None
    blob = json.dumps({"d": data, "i": _I18N},
                      ensure_ascii=False).replace("</", "<\\/")
    return (tpl.replace("__BLOB__", blob)
               .replace("__VER__", cfg.APP_VERSION))


def _sub_headers(c, sub_url):
    expire = c["expiry"] // 1000 if c["expiry"] else 0
    title = db.get_setting("sub_title") or cfg.APP_NAME
    return {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-store",
        "Subscription-Userinfo":
            f"upload={c['up']}; download={c['down']}; "
            f"total={c['limit_bytes']}; expire={expire}",
        "Profile-Title": base64.b64encode(title.encode()).decode(),
        "Profile-Web-Page-URL": sub_url,
        "Profile-Update-Interval": "6",
    }


async def sub_handler(request):
    token = request.match_info.get("token", "")
    if not _TOKEN_RE.match(token):
        return web.Response(status=404, text="Not Found")
    c = db.q("SELECT * FROM clients WHERE sub_id=?", (token,), one=True)
    if not c:
        return web.Response(status=404, text="Not Found")

    db.ex("UPDATE clients SET last_seen=? WHERE id=?", (now_ms(), c["id"]))

    host = resolve_public_host(request.host)
    scheme = "https" if cfg.PAAS else request.scheme
    sub_url = f"{scheme}://{host}/sub/{token}"

    expired = bool(c["expiry"] and c["expiry"] <= now_ms())
    over = bool(c["limit_bytes"]
                and (c["up"] + c["down"]) >= c["limit_bytes"])
    blocked = (not c["enable"]) or expired or over
    links = client_links(c, host=host) if not blocked else []

    if _wants_html(request):
        html = _render_page(c, links, sub_url, blocked)
        if html is not None:
            return web.Response(
                text=html, content_type="text/html", charset="utf-8",
                headers={"Cache-Control": "no-store"})

    raw = "\n".join(l["link"] for l in links)
    body = (raw if request.query.get("raw") == "1"
            else base64.b64encode(raw.encode()).decode())
    return web.Response(body=body.encode("utf-8"),
                        headers=_sub_headers(c, sub_url))
