# -*- coding: utf-8 -*-
"""تولید لینک‌های اشتراک — v2.2.1
FIX: دیگر inbound_builder را import نمی‌کند (رفع circular import)؛
effective_flow از utils می‌آد."""

import base64
import json
import socket
from urllib.parse import quote

from . import config as cfg
from . import database as db
from .utils import load_json, to_int, effective_flow

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "")


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _is_local(h: str) -> bool:
    return h in _LOCAL_HOSTS or h.startswith("127.")


def resolve_public_host(request_host=None) -> str:
    dom = (db.get_setting("public_domain") or "").strip()
    if dom:
        dom = dom.replace("https://", "").replace("http://", "")
        dom = dom.split("/")[0].split(":")[0].strip()
        if dom:
            return dom
    if request_host:
        h = str(request_host).split(":")[0].strip()
        if h and not _is_local(h):
            if not (db.get_setting("host_cache") or "").strip():
                db.set_setting("host_cache", h)
            return h
    cached = (db.get_setting("host_cache") or "").strip()
    if cached:
        return cached
    return local_ip()


def _qs(params: dict) -> str:
    return "&".join(f"{k}={quote(str(v), safe='')}"
                    for k, v in params.items()
                    if v not in ("", None))


def _conn(g, proto, c, host, paas):
    """پارامترهای مشترک اتصال از دید کلاینت."""
    if paas:
        return {"net": g.get("transport", "ws"), "sec": "tls", "port": 443,
                "path": g.get("path", "/"), "hh": host, "sni": host,
                "flow": "", "selfsigned": False,
                "xhttp_mode": "auto"}
    net = g.get("transport", "tcp")
    sec = g.get("security", "none")
    r = g.get("reality") or {}
    sni = g.get("sni") or (r.get("serverNames") or [host])[0] or host
    return {"net": net, "sec": sec, "port": to_int(g.get("port"), 443),
            "path": g.get("path", ""), "hh": g.get("host") or host,
            "sni": sni,
            "flow": effective_flow(c.get("flow"), proto, net, sec),
            "selfsigned": bool(g.get("selfsigned")),
            "xhttp_mode": g.get("xhttpMode") or "auto"}


# ---------------- سازنده‌های لینک ----------------

def _vless(c, host, k, g, name):
    p = {"encryption": "none", "security": k["sec"], "type": k["net"]}
    if k["sec"] in ("tls", "reality"):
        p["fp"] = "chrome"
    if k["flow"]:
        p["flow"] = k["flow"]
    if k["net"] == "ws":
        p["path"] = k["path"]
        p["host"] = k["hh"]
    elif k["net"] == "grpc":
        p["serviceName"] = k["path"]
        p["mode"] = "gun"
    elif k["net"] == "httpupgrade":
        p["path"] = k["path"]
        p["host"] = k["hh"]
    elif k["net"] == "xhttp":
        p["path"] = k["path"]
        p["mode"] = k["xhttp_mode"]
    if k["sec"] == "tls":
        p["sni"] = k["sni"]
        p["alpn"] = g.get("alpn") or "http/1.1"
        if k["selfsigned"]:
            p["allowInsecure"] = "1"
    if k["sec"] == "reality":
        r = g.get("reality") or {}
        p["sni"] = k["sni"]
        if r.get("publicKey"):
            p["pbk"] = r["publicKey"]
        p["sid"] = (r.get("shortIds") or [""])[0]
    return f"vless://{c['uuid']}@{host}:{k['port']}?{_qs(p)}#{quote(name)}"


def _vmess(c, host, k, g, name):
    v = {
        "v": "2", "ps": name, "add": host, "port": str(k["port"]),
        "id": c["uuid"], "aid": "0", "scy": "auto",
        "net": k["net"], "type": "none",
        "host": k["hh"] if k["net"] in ("ws", "httpupgrade", "xhttp") else "",
        "path": k["path"] if k["net"] in ("ws", "grpc", "httpupgrade",
                                          "xhttp") else "",
        "tls": "tls" if k["sec"] in ("tls", "reality") else "",
        "sni": k["sni"] if k["sec"] != "none" else "",
        "alpn": g.get("alpn") or "",
        "fp": "chrome" if k["sec"] != "none" else "",
    }
    return "vmess://" + base64.b64encode(
        json.dumps(v, ensure_ascii=False).encode()).decode()


def _trojan(c, host, k, name):
    pw = c["password"] or c["uuid"]
    p = {"security": k["sec"], "type": k["net"]}
    if k["net"] == "ws":
        p["path"] = k["path"]
        p["host"] = k["hh"]
    elif k["net"] == "grpc":
        p["serviceName"] = k["path"]
        p["mode"] = "gun"
    elif k["net"] == "httpupgrade":
        p["path"] = k["path"]
        p["host"] = k["hh"]
    elif k["net"] == "xhttp":
        p["path"] = k["path"]
        p["mode"] = k["xhttp_mode"]
    if k["sec"] != "none":
        p["sni"] = k["sni"]
        if k["selfsigned"]:
            p["allowInsecure"] = "1"
    return f"trojan://{quote(pw, safe='')}@{host}:{k['port']}?{_qs(p)}#{quote(name)}"


def _ss(c, host, k, g, name):
    pw = c["password"] or c["uuid"]
    method = g.get("method") or "aes-256-gcm"
    userinfo = base64.urlsafe_b64encode(
        f"{method}:{pw}".encode()).decode().rstrip("=")
    return f"ss://{userinfo}@{host}:{k['port']}#{quote(name)}"


# ---------------- API عمومی ----------------

def client_links(c, host=None, paas=None):
    """همه لینک‌های یک کلاینت → [{'name','link','protocol',...}]"""
    paas = cfg.PAAS if paas is None else paas
    host = host or resolve_public_host()
    own = load_json(c["inbounds"], [])
    out = []
    for ib in db.q("SELECT * FROM inbounds WHERE enable=1 ORDER BY id"):
        if own and ib["id"] not in own:
            continue
        g = load_json(ib["config"], {})
        proto = ib["protocol"]
        k = _conn(g, proto, c, host, paas)
        name = f"{ib['remark'] or ('ib' + str(ib['id']))} | {c['email']}"
        if proto == "vless":
            link = _vless(c, host, k, g, name)
        elif proto == "vmess":
            link = _vmess(c, host, k, g, name)
        elif proto == "trojan":
            link = _trojan(c, host, k, name)
        else:
            link = _ss(c, host, k, g, name)
        out.append({"name": name, "link": link, "protocol": proto,
                    "inbound_id": ib["id"],
                    "remark": ib["remark"] or ""})
    return out


def subscription_body(c, host=None, raw=False) -> str:
    links = [x["link"] for x in client_links(c, host)]
    joined = "\n".join(links)
    return joined if raw else base64.b64encode(joined.encode()).decode()


def subscription_headers(c) -> dict:
    expire = c["expiry"] // 1000 if c["expiry"] else 0
    title = db.get_setting("sub_title") or cfg.APP_NAME
    return {
        "Content-Type": "text/plain; charset=utf-8",
        "Subscription-Userinfo":
            f"upload={c['up']}; download={c['down']}; "
            f"total={c['limit_bytes']}; expire={expire}",
        "Profile-Title": base64.b64encode(title.encode()).decode(),
        "Profile-Update-Interval": "6",
    }
