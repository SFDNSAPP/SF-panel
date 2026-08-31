# -*- coding: utf-8 -*-
"""داشبورد، اطلاعات سرور، لاگ‌ها، مدیریت هسته، QR."""

import platform
import shutil
import time

import qrcode

from aiohttp import web

from core import config as cfg
from core import database as db
from core.scheduler import SERIES
from core.xray import xray
from core.router import router
from core.link_builder import resolve_public_host

from .common import (json_ok, json_err, body_json, auth_required,
                     run_ex)

START_TS = time.time()


# ---------------- آمار سیستم ----------------

class SysStats:
    _cpu_prev = None
    _net_prev = None
    _net_time = 0.0

    @classmethod
    def snapshot(cls):
        return {"cpu": cls._cpu(), "mem": cls._mem(), "disk": cls._disk(),
                "net": cls._net(), "uptime": cls._uptime()}

    @classmethod
    def _cpu(cls):
        try:
            with open("/proc/stat") as f:
                vals = [int(x) for x in f.readline().split()[1:]]
            total, idle = sum(vals), vals[3] + (vals[4] if len(vals) > 4 else 0)
            prev, cls._cpu_prev = cls._cpu_prev, (total, idle)
            if prev:
                dt, di = total - prev[0], idle - prev[1]
                return round((dt - di) * 100 / dt) if dt > 0 else 0
            return 0
        except Exception:
            return 0

    @classmethod
    def _mem(cls):
        try:
            info = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, v = line.split(":")
                    info[k] = int(v.split()[0]) * 1024
                    if len(info) > 4:
                        break
            total = info.get("MemTotal", 0)
            used = total - info.get("MemAvailable", 0)
            return {"total": total, "used": used,
                    "pct": round(used * 100 / total) if total else 0}
        except Exception:
            return {"total": 0, "used": 0, "pct": 0}

    @staticmethod
    def _disk():
        try:
            du = shutil.disk_usage(cfg.DATA_DIR)
            return {"total": du.total, "used": du.used,
                    "pct": round(du.used * 100 / du.total)}
        except Exception:
            return {"total": 0, "used": 0, "pct": 0}

    @classmethod
    def _net(cls):
        try:
            up = down = 0
            with open("/proc/net/dev") as f:
                for line in f.readlines()[2:]:
                    if ":" not in line:
                        continue
                    iface, data = line.split(":", 1)
                    if iface.strip() == "lo":
                        continue
                    cols = data.split()
                    down += int(cols[0])
                    up += int(cols[8])
            now = time.monotonic()
            out = {"up": 0, "down": 0}
            if cls._net_prev and now > cls._net_time:
                dt = now - cls._net_time
                out = {"up": int((up - cls._net_prev[0]) / dt),
                       "down": int((down - cls._net_prev[1]) / dt)}
            cls._net_prev, cls._net_time = (up, down), now
            return out
        except Exception:
            return {"up": 0, "down": 0}

    @staticmethod
    def _uptime():
        try:
            with open("/proc/uptime") as f:
                return int(float(f.read().split()[0]))
        except Exception:
            return 0


# ---------------- داشبورد ----------------

@auth_required
async def api_dashboard(request):
    day = time.strftime("%Y-%m-%d", time.gmtime())
    daily = db.q("SELECT * FROM daily_totals WHERE day=?", (day,), one=True) \
        or {"up": 0, "down": 0}
    totals = db.q("SELECT COALESCE(SUM(up),0) AS u, COALESCE(SUM(down),0) AS d, "
                  "COUNT(*) AS n, COALESCE(SUM(enable),0) AS e "
                  "FROM clients", one=True)
    inb = db.q("SELECT COUNT(*) AS n, COALESCE(SUM(enable),0) AS e "
               "FROM inbounds", one=True)

    xs = {}
    if xray.alive():
        try:
            xs = await run_ex(xray.stats.sys_stats)
        except Exception:
            xs = {}

    state = xray.state()
    state["goroutines"] = xs.get("goroutines", 0)
    state["alloc"] = xs.get("alloc", 0)

    return json_ok({
        "sys": SysStats.snapshot(),
        "panel_uptime": int(time.time() - START_TS),
        "xray": state,
        "traffic": {"up": totals["u"], "down": totals["d"],
                    "today_up": daily["up"], "today_down": daily["down"]},
        "counts": {
            "inbounds": inb["n"], "inbounds_active": inb["e"],
            "clients": totals["n"], "clients_active": totals["e"],
            "conns": router.active if cfg.PAAS else 0,
            "relayed": router.total_relayed if cfg.PAAS else 0,
        },
        "top": db.q("SELECT email, up, down, limit_bytes, expiry, enable "
                    "FROM clients ORDER BY (up+down) DESC LIMIT 6"),
        "events": db.q("SELECT ts, level, msg FROM events "
                       "ORDER BY id DESC LIMIT 8"),
        "series": [{"t": t, "up": u, "d": dn} for (t, u, dn) in SERIES],
        "interval": max(2, cfg.STATS_INTERVAL),
        "paas": cfg.PAAS,
        "host": resolve_public_host(request.host),
    })


@auth_required
async def api_info(request):
    host = resolve_public_host(request.host)
    scheme = "https" if cfg.PAAS else request.scheme
    return json_ok({
        "mode": "paas" if cfg.PAAS else "vps",
        "public_port": cfg.PUBLIC_PORT,
        "host": host,
        "panel_url": f"{scheme}://{host}",
        "xray": xray.state(),
        "routes": router.routes_info() if cfg.PAAS else [],
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
    })


@auth_required
async def api_logs(request):
    if request.query.get("type") == "xray":
        return json_ok({"type": "xray",
                        "lines": xray.tail_log(250) or "— خالی —"})
    rows = db.q("SELECT ts, level, msg FROM events "
                "ORDER BY id DESC LIMIT 200")
    lines = []
    for r in rows:
        ts = time.strftime("%m-%d %H:%M:%S", time.localtime(r["ts"] / 1000))
        lines.append(f"[{ts}] {r['level'].upper():5} │ {r['msg']}")
    return json_ok({"type": "panel",
                    "lines": "\n".join(lines) or "— خالی —"})


# ---------------- مدیریت هسته ----------------

@auth_required
async def api_xray_restart(request):
    ok, err = await run_ex(xray.restart, "دستور ادمین")
    if ok:
        return json_ok({"ok": True, "state": xray.state()})
    return json_err(f"خطا در راه‌اندازی مجدد: {err}", 500)


@auth_required
async def api_xray_keys(request):
    try:
        keys = await run_ex(xray.x25519)
    except Exception as e:
        return json_err(f"تولید کلید ناموفق: {e}")
    return json_ok(keys)


@auth_required
async def api_xray_cert(request):
    d = await body_json(request)
    domain = str(d.get("domain") or "").strip() \
        or resolve_public_host(request.host)
    try:
        res = await run_ex(xray.gen_selfsigned_cert, domain)
    except Exception as e:
        return json_err(str(e))
    return json_ok(res)


@auth_required
async def api_xray_update(request):
    ok, info = await run_ex(xray.update_core)
    if ok:
        return json_ok({"ok": True, "version": xray.version})
    return json_err(f"به‌روزرسانی ناموفق: {info}", 500)


# ---------------- QR ----------------

@auth_required
async def api_qr(request):
    text = request.query.get("text") or ""
    if not text or len(text) > 2000:
        return json_err("متن نامعتبر است.")
    qr = qrcode.QRCode(border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(text)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)
    rects = "".join(f'<rect x="{x}" y="{y}" width="1" height="1"/>'
                    for y, row in enumerate(matrix)
                    for x, v in enumerate(row) if v)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" '
           f'shape-rendering="crispEdges">'
           f'<rect width="{n}" height="{n}" fill="#ffffff"/>'
           f'<g fill="#0b0f1a">{rects}</g></svg>')
    return web.Response(text=svg, content_type="image/svg+xml",
                        headers={"Cache-Control": "private, max-age=600"})