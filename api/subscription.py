# -*- coding: utf-8 -*-
"""Subscription endpoint — SF-Panel v2

GET /sub/{token}
  • اپ‌های پروکسی → لیست لینک‌ها (base64) + هدر Subscription-Userinfo
    (مصرف/حجم/انقضا داخل خود اپ نمایش داده می‌شود)
  • مرورگر → صفحه داشبورد HTML: نوار مصرف، حجم/زمان باقی‌مانده،
    QR هر کانفیگ، کپی، تاخیر زنده سرور
  • ?raw=1 → متن خام   • ?web=1 → اجبار صفحه HTML
"""

import base64
import json
import re

from aiohttp import web

from core import config as cfg
from core import database as db
from core.utils import now_ms
from core.link_builder import client_links, resolve_public_host

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-]{4,64}$")

_APP_UA = ("v2ray", "hiddify", "sing-box", "singbox", "clash",
           "shadowrocket", "streisand", "nekobox", "nekoray", "karing",
           "husi", "fairvpn", "loon", "quantumult", "surge", "okhttp",
           "ktor", "dart", "curl", "wget", "python-requests",
           "python-urllib", "axios", "java/", "go-http-client",
           "apache-httpclient")


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

_PAGE = """<!doctype html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#030807">
<title>SF · Subscription</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%2300ff9d'/%3E%3Ctext x='32' y='43' font-size='24' font-family='monospace' font-weight='bold' fill='%2304231a' text-anchor='middle'%3ESF%3C/text%3E%3C/svg%3E">
<link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;600;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
::selection{background:rgba(0,255,157,.35)}
body{font-family:Vazirmatn,Inter,system-ui,sans-serif;background:#030807;
color:#e8fff4;min-height:100vh;background-image:
radial-gradient(900px 420px at 85% -5%,rgba(0,255,157,.13),transparent 60%),
radial-gradient(700px 420px at -5% 105%,rgba(0,212,170,.09),transparent 60%)}
.wrap{max-width:680px;margin:0 auto;padding:28px 18px 44px}
header{display:flex;align-items:center;gap:14px;margin-bottom:18px}
.logo{width:52px;height:52px;border-radius:14px;
background:linear-gradient(135deg,#00ff9d,#00d4aa);color:#04231a;
font-weight:800;font-size:1.25rem;display:flex;align-items:center;
justify-content:center;box-shadow:0 0 24px rgba(0,255,157,.45);flex-shrink:0}
h1{font-size:1.28rem;font-weight:800;color:#d9ffee}
.email{color:#84a394;font-size:.8rem;margin-top:3px;word-break:break-all}
#langBtn{margin-inline-start:auto}
.card{background:rgba(0,255,157,.045);border:1px solid rgba(0,255,157,.16);
border-radius:16px;padding:18px;margin-bottom:14px;backdrop-filter:blur(10px)}
.lbl{font-size:.76rem;color:#84a394;margin-bottom:10px;letter-spacing:.3px}
.bar{height:10px;border-radius:99px;background:rgba(0,255,157,.12);overflow:hidden}
.bar i{display:block;height:100%;border-radius:99px;
background:linear-gradient(90deg,#00ff9d,#00ffd1);
box-shadow:0 0 12px rgba(0,255,157,.5);transition:width .6s}
.bar i.warn{background:linear-gradient(90deg,#ffb84d,#ff9d3d)}
.bar i.bad{background:linear-gradient(90deg,#ff5d73,#ff2e55)}
.nums{display:flex;justify-content:space-between;margin-top:8px;font-size:.85rem}
.nums b{color:#00ff9d}
.kv{display:flex;justify-content:space-between;padding:7px 0;
border-bottom:1px dashed rgba(0,255,157,.12);font-size:.82rem}
.kv:last-child{border-bottom:none}
.kv span{color:#84a394}
.big{font-size:1.5rem;font-weight:800;color:#00ff9d;
text-shadow:0 0 14px rgba(0,255,157,.35)}
.pill{display:inline-flex;align-items:center;gap:8px;padding:6px 14px;
border-radius:99px;font-size:.75rem;font-weight:700;border:1px solid;margin-bottom:14px}
.pill.ok{color:#00ff9d;border-color:rgba(0,255,157,.4);background:rgba(0,255,157,.08)}
.pill.bad{color:#ff5d73;border-color:rgba(255,93,115,.4);background:rgba(255,93,115,.08)}
.pill.warn{color:#ffb84d;border-color:rgba(255,184,77,.4);background:rgba(255,184,77,.08)}
.pill .dot{width:8px;height:8px;border-radius:50%;background:currentColor;
box-shadow:0 0 8px currentColor;animation:pulse 2s infinite}
@keyframes pulse{50%{opacity:.4}}
.btn{font-family:inherit;font-size:.8rem;font-weight:700;padding:8px 16px;
border-radius:10px;border:1px solid rgba(0,255,157,.3);
background:rgba(0,255,157,.07);color:#00ff9d;cursor:pointer;transition:.2s}
.btn:hover{background:rgba(0,255,157,.16);box-shadow:0 0 16px rgba(0,255,157,.25)}
.btn.primary{background:linear-gradient(135deg,#00ff9d,#00d4aa);color:#04231a;border:none}
.url{direction:ltr;text-align:left;font-family:ui-monospace,Consolas,monospace;
font-size:.72rem;color:#7dffd0;word-break:break-all;background:#051510;
border:1px dashed rgba(0,255,157,.3);padding:10px 12px;border-radius:10px;user-select:all}
.cfg{background:rgba(0,255,157,.04);border:1px solid rgba(0,255,157,.14);
border-radius:12px;padding:14px;margin-bottom:10px}
.cfg-head{display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap}
.badge{padding:3px 9px;border-radius:7px;font-size:.65rem;font-weight:800}
.b-vless{background:rgba(0,255,157,.16);color:#00ff9d}
.b-vmess{background:rgba(0,255,209,.14);color:#00ffd1}
.b-trojan{background:rgba(255,184,77,.15);color:#ffb84d}
.b-shadowsocks{background:rgba(255,93,115,.15);color:#ff8296}
.cfg-name{font-size:.8rem;font-weight:600}
.cfg-link{direction:ltr;text-align:left;font-family:ui-monospace,Consolas,monospace;
font-size:.66rem;color:#84a394;word-break:break-all;background:#04120d;
padding:8px 10px;border-radius:8px;user-select:all;margin-bottom:10px}
.row{display:flex;gap:8px}
.qrbox{margin-top:10px;text-align:center}
.qrbox svg{width:190px;height:190px;background:#fff;border-radius:12px;
padding:8px;border:1px solid rgba(0,255,157,.2)}
.tip{font-size:.75rem;color:#84a394;line-height:1.9;margin-top:12px}
.notice{padding:16px;border-radius:12px;background:rgba(255,93,115,.07);
border:1px solid rgba(255,93,115,.3);color:#ff8296;font-size:.85rem;line-height:1.9}
footer{text-align:center;color:#5d7a6b;font-size:.7rem;margin-top:18px}
footer button{background:none;border:none;color:#00ff9d;cursor:pointer;
font-family:inherit;font-size:.7rem}
.toast{position:fixed;bottom:20px;inset-inline-start:20px;background:#06231a;
color:#00ff9d;border:1px solid rgba(0,255,157,.4);padding:10px 18px;
border-radius:10px;font-size:.8rem;opacity:0;transform:translateY(10px);
transition:.25s;pointer-events:none;box-shadow:0 0 20px rgba(0,255,157,.2);z-index:9}
.toast.show{opacity:1;transform:none}
.hidden{display:none}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="logo">SF</div>
    <div>
