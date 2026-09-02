# -*- coding: utf-8 -*-
"""سازنده اینباند Xray — v2.2
جدید: XHTTP · Sniffing کامل · ProxyProtocol · Extra JSON"""

import json
import re
import secrets

from . import config as cfg
from . import database as db
from .utils import load_json, to_int, deep_merge, is_safe_path

PROTOCOLS = ("vless", "vmess", "trojan", "shadowsocks")
PAAS_TRANSPORTS = ("ws", "httpupgrade")
VPS_TRANSPORTS = ("tcp", "ws", "grpc", "httpupgrade", "xhttp")
SS_METHODS = ("aes-256-gcm", "aes-128-gcm", "chacha20-poly1305",
              "xchacha20-poly1305", "none")
ALLOWED_FLOWS = ("", "xtls-rprx-vision")
XHTTP_MODES = ("auto", "packet-up", "stream-up", "stream-one")
SNIFF_DESTS = ("http", "tls", "quic", "bittorrent")

RESERVED_PATHS = ("/", "/api", "/sub", "/assets", "/panel",
                  "/healthz", "/favicon.ico", "/logs")
RESERVED_PREFIXES = ("/api/", "/sub/", "/assets/", "/panel/")


def effective_flow(client_flow, proto, transport, security):
    """Vision فقط روی VLESS + TCP + TLS/Reality."""
    if proto != "vless" or transport != "tcp":
        return ""
    if security not in ("tls", "reality"):
        return ""
    f = (client_flow or "").strip()
    if security == "reality" and not f:
        return "xtls-rprx-vision"
    return f if f in ALLOWED_FLOWS else ""


def _as_list(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return []


def _extra(payload):
    """Extra JSON — هرچه کاربر حرفه‌ای بخواهد داخل اینباند ادغام می‌شود."""
    e = payload.get("extra")
    if isinstance(e, dict):
        return e
    if isinstance(e, str) and e.strip():
        try:
            v = json.loads(e)
            return v if isinstance(v, dict) else {}
        except ValueError:
            return {}
    return {}


def _norm_sniff(payload):
    """تنظیمات Sniffing — destOverride و routeOnly."""
    s = payload.get("sniff")
    if not isinstance(s, dict):
        s = {}
    dest = s.get("destOverride")
    if isinstance(dest, str):
        dest = [x.strip() for x in dest.split(",") if x.strip()]
    if not isinstance(dest, list):
        dest = ["http", "tls"]
    dest = [d for d in dest if d in SNIFF_DESTS] or ["http", "tls"]
    return {"enabled": bool(s.get("enabled", True)),
            "destOverride": dest,
            "routeOnly": bool(s.get("routeOnly", False))}


def _norm_path(path, default=None):
    path = str(path or "").strip()
    if not path and default:
        return default
    if path == "/":                       # مسیر ریشه برای ws/xhttp معتبر است
        return "/"
    return path


def normalize_inbound(payload, paas, taken_paths=None, self_id=None):
    """→ (پیام_خطا | None, کانفیگ_نرمال | None)"""
    taken_paths = taken_paths or {}
    proto = str(payload.get("protocol") or "vless").strip().lower()
    if proto not in PROTOCOLS:
        return "پروتکل باید vless / vmess / trojan / shadowsocks باشد.", None

    out = {
        "sniff": _norm_sniff(payload),
        "proxyProtocol": bool(payload.get("proxyProtocol")),
        "xhttpMode": "auto",
        "extra": _extra(payload),
        "reality": {}, "method": "", "password": "",
    }

    if paas:
        # ---------- حالت ابری ----------
        if proto == "shadowsocks":
            return "در حالت ابری Shadowsocks پشتیبانی نمی‌شود.", None
        transport = str(payload.get("transport") or "ws").strip().lower()
        if transport not in PAAS_TRANSPORTS:
            return "در حالت ابری فقط ws یا httpupgrade مجاز است.", None
        path = _norm_path(payload.get("path"),
                          "/sf-" + secrets.token_hex(3))
        if path != "/" and not is_safe_path(path):
            return "مسیر نامعتبر است.", None
        if path in RESERVED_PATHS or any(path.startswith(p)
                                         for p in RESERVED_PREFIXES):
            return "این مسیر برای پنل رزرو شده است.", None
        for pid, p in taken_paths.items():
            if pid != self_id and p == path:
                return "این مسیر در اینباند دیگری استفاده شده است.", None
        out.update({
            "protocol": proto, "port": 443, "transport": transport,
            "path": path, "host": "", "security": "none", "sni": "",
            "alpn": "http/1.1", "certFile": "", "keyFile": "",
            "selfsigned": False,
        })
    else:
        # ---------- حالت سرور ----------
        transport = str(payload.get("transport") or "tcp").strip().lower()
        if transport not in VPS_TRANSPORTS:
            return "ترنسپورت نامعتبر است.", None
        if transport == "xhttp" and proto == "shadowsocks":
            return "xhttp با Shadowsocks کار نمی‌کند.", None
        port = to_int(payload.get("port"), 0)
        if not (1 <= port <= 65535):
            return "پورت باید بین ۱ تا ۶۵۵۳۵ باشد.", None

        if transport == "tcp":
            path = ""
        elif transport == "grpc":
            path = str(payload.get("path") or "").strip()
            if not re.match(r"^[A-Za-z0-9_\-]{1,64}$", path):
                return "نام سرویس gRPC نامعتبر است.", None
        else:                              # ws / httpupgrade / xhttp
            path = _norm_path(payload.get("path"), "/")
            if path != "/" and not is_safe_path(path):
                return "مسیر نامعتبر است.", None

        security = str(payload.get("security") or "none").strip().lower()
        if security not in ("none", "tls", "reality"):
            return "نوع امنیت نامعتبر است.", None
        if security == "reality" and transport not in ("tcp", "grpc"):
            return "Reality فقط با ترنسپورت tcp یا grpc کار می‌کند.", None

        out.update({
            "protocol": proto, "port": port, "transport": transport,
            "path": path, "host": str(payload.get("host") or "").strip(),
            "security": security,
            "sni": str(payload.get("sni") or "").strip(),
            "alpn": str(payload.get("alpn") or "http/1.1").strip(),
            "certFile": str(payload.get("certFile") or "").strip(),
            "keyFile": str(payload.get("keyFile") or "").strip(),
            "selfsigned": bool(payload.get("selfsigned")),
        })
        if transport == "xhttp":
            import os as _os
            mode = str(payload.get("xhttpMode") or "auto").strip().lower()
            if mode not in XHTTP_MODES:
                return f"حالت xhttp باید یکی از {XHTTP_MODES} باشد.", None
            out["xhttpMode"] = mode

        if security == "tls":
            if not out["certFile"] or not out["keyFile"]:
                return ("برای TLS فایل گواهی و کلید لازم است "
                        "(دکمه «گواهی خودامضا» را بزنید)."), None
            import os as _os
            if not _os.path.isfile(out["certFile"]) \
                    or not _os.path.isfile(out["keyFile"]):
                return "فایل گواهی/کلید روی سرور یافت نشد.", None

        if security == "reality":
            r = payload.get("reality") or {}
            dest = str(r.get("dest") or "www.microsoft.com:443").strip()
            sn = _as_list(r.get("serverNames")) or [dest.split(":")[0]]
            si = _as_list(r.get("shortIds")) or [secrets.token_hex(4)]
            for s in si:
                if not re.match(r"^[0-9a-fA-F]{0,16}$", s):
                    return "shortId نامعتبر است (حداکثر ۱۶ کاراکتر hex).", None
            out["reality"] = {
                "dest": dest, "serverNames": sn,
                "privateKey": str(r.get("privateKey") or "").strip(),
                "publicKey": str(r.get("publicKey") or "").strip(),
                "shortIds": si,
            }
            if not out["reality"]["privateKey"]:
                return "کلید خصوصی Reality لازم است (دکمه «تولید x25519»).", None

    if proto == "shadowsocks":
        method = str(payload.get("method") or "aes-256-gcm").strip()
        if method not in SS_METHODS:
            return "روش رمزنگاری Shadowsocks پشتیبانی نمی‌شود.", None
        out["method"] = method
        out["password"] = str(payload.get("password") or "").strip() \
            or secrets.token_hex(12)
    return None, out


def seed_default(paas):
    if paas:
        return {"protocol": "vless", "port": 443, "transport": "ws",
                "path": "/sf-" + secrets.token_hex(3), "host": "",
                "security": "none", "sni": "", "alpn": "http/1.1",
                "certFile": "", "keyFile": "", "selfsigned": False,
                "reality": {}, "method": "", "password": "",
                "sniff": {"enabled": True, "destOverride": ["http", "tls"],
                          "routeOnly": False},
                "proxyProtocol": False, "xhttpMode": "auto", "extra": {}}
    return {"protocol": "vless", "port": 8443, "transport": "tcp", "path": "",
            "host": "", "security": "none", "sni": "", "alpn": "http/1.1",
            "certFile": "", "keyFile": "", "selfsigned": False,
            "reality": {}, "method": "", "password": "",
            "sniff": {"enabled": True, "destOverride": ["http", "tls"],
                      "routeOnly": False},
            "proxyProtocol": False, "xhttpMode": "auto", "extra": {}}


# ---------------- ساخت بخش‌های کانفیگ ----------------

def _client_entities(proto, clients, transport, security):
    ents = []
    for c in clients:
        e = {"email": c["email"], "level": 0}
        if proto == "vless":
            e["id"] = c["uuid"]
            fl = effective_flow(c.get("flow"), proto, transport, security)
            if fl:
                e["flow"] = fl
        elif proto == "vmess":
            e["id"] = c["uuid"]
            e["alterId"] = 0
        elif proto == "trojan":
            e["password"] = c["password"] or c["uuid"]
        ents.append(e)
    return ents


def _stream_settings(g, paas):
    if paas:
        t = g.get("transport", "ws")
        ss = {"network": t}
        if t == "ws":
            ss["wsSettings"] = {"path": g.get("path") or "/"}
        elif t == "httpupgrade":
            ss["httpupgradeSettings"] = {"path": g.get("path") or "/",
                                         "host": g.get("host") or ""}
        return ss

    t = g.get("transport", "tcp")
    ss = {"network": t}
    if t == "ws":
        w = {"path": g.get("path") or "/"}
        if g.get("host"):
            w["headers"] = {"Host": g["host"]}
        ss["wsSettings"] = w
    elif t == "grpc":
        ss["grpcSettings"] = {"serviceName": g.get("path") or "",
                              "multiMode": False}
    elif t == "httpupgrade":
        ss["httpupgradeSettings"] = {"path": g.get("path") or "/",
                                     "host": g.get("host") or ""}
    elif t == "xhttp":
        ss["xhttpSettings"] = {"path": g.get("path") or "/",
                               "mode": g.get("xhttpMode") or "auto"}

    security = g.get("security", "none")
    if security == "tls":
        ss["security"] = "tls"
        tls = {"alpn": [x.strip() for x in (g.get("alpn") or "http/1.1")
                        .split(",") if x.strip()]}
        if g.get("sni"):
            tls["serverName"] = g["sni"]
        if g.get("certFile") and g.get("keyFile"):
            tls["certificates"] = [{"certificateFile": g["certFile"],
                                    "keyFile": g["keyFile"]}]
        ss["tlsSettings"] = tls
    elif security == "reality":
        r = g.get("reality") or {}
        ss["security"] = "reality"
        ss["realitySettings"] = {
            "show": False, "dest": r.get("dest") or "www.microsoft.com:443",
            "xver": 0, "serverNames": r.get("serverNames") or [],
            "privateKey": r.get("privateKey") or "",
            "shortIds": r.get("shortIds") or [""],
        }
    return ss


def _sniffing(g):
    s = g.get("sniff") or {}
    dest = s.get("destOverride") or ["http", "tls"]
    sn = {"enabled": bool(s.get("enabled", True)),
          "destOverride": list(dest)}
    if s.get("routeOnly"):
        sn["routeOnly"] = True
    return sn


def _protocol_settings(proto, g, clients, transport, security):
    if proto == "vless":
        return {"clients": _client_entities(proto, clients, transport,
                                            security),
                "decryption": "none"}
    if proto == "vmess":
        return {"clients": _client_entities(proto, clients, transport,
                                            security),
                "disableInsecureEncryption": True}
    if proto == "trojan":
        return {"clients": _client_entities(proto, clients, transport,
                                            security)}
    pw = ""
    if clients:
        pw = clients[0].get("password") or clients[0].get("uuid") or ""
    if not pw:
        pw = g.get("password") or ""
    return {"method": g.get("method") or "aes-256-gcm",
            "password": pw, "network": "tcp,udp", "ivCheck": True}


def build_inbound(ib, clients, paas):
    """یک اینباند کامل Xray از ردیف DB."""
    g = load_json(ib["config"], {})
    proto = ib["protocol"]
    listen = "127.0.0.1" if paas else "0.0.0.0"
    port = ib["internal_port"] if paas else to_int(g.get("port"), 443)
    ss = _stream_settings(g, paas)
    if g.get("proxyProtocol"):
        ss["acceptProxyProtocol"] = True
    xi = {
        "tag": f"ib{ib['id']}",
        "listen": listen,
        "port": port,
        "protocol": proto,
        "settings": _protocol_settings(proto, g, clients,
                                       g.get("transport", "tcp"),
                                       g.get("security", "none")),
        "sniffing": _sniffing(g),
        "streamSettings": ss,
    }
    extra = g.get("extra")
    if isinstance(extra, dict) and extra:
        xi = deep_merge(xi, extra)       # تزریق تنظیمات پیشرفته کاربر
    return xi


def build_full_config(paas):
    """کل کانفیگ هسته — با CIDRهای صریح (بدون نیاز به geoip.dat)."""
    inbounds = db.q("SELECT * FROM inbounds WHERE enable=1 ORDER BY id")
    clients = db.q("SELECT * FROM clients WHERE enable=1")

    xr = [{
        "tag": "api", "listen": "127.0.0.1", "port": cfg.XRAY_API_PORT,
        "protocol": "dokodemo-door", "settings": {"address": "127.0.0.1"},
        "streamSettings": {"network": "tcp"},
        "sniffing": {"enabled": False},
    }]
    for ib in inbounds:
        if paas and not ib["internal_port"]:
            continue
        cl = [c for c in clients if ib["id"] in load_json(c["inbounds"], [])]
        if ib["protocol"] == "shadowsocks":
            cl = cl[:1]
        xr.append(build_inbound(ib, cl, paas))

    config = {
        "log": {"loglevel": "warning", "error": cfg.XRAY_LOG},
        "api": {"tag": "api", "services": ["StatsService"]},
        "stats": {},
        "policy": {
            "levels": {"0": {"statsUserUplink": True,
                             "statsUserDownlink": True}},
            "system": {"statsInboundUplink": True,
                       "statsInboundDownlink": True,
                       "statsOutboundUplink": True,
                       "statsOutboundDownlink": True},
        },
        "inbounds": xr,
        "outbounds": [
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole",
             "settings": {"response": {"type": "http"}}},
        ],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {"type": "field", "inboundTag": ["api"], "outboundTag": "api"},
                {"type": "field", "ip": [
                    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12",
                    "192.168.0.0/16", "169.254.0.0/16",
                    "::1/128", "fc00::/7", "fe80::/10",
                ], "outboundTag": "block"},
                {"type": "field", "protocol": ["bittorrent"],
                 "outboundTag": "block"},
            ],
        },
    }
    return json.dumps(config, ensure_ascii=False, indent=2)
