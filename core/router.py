# -*- coding: utf-8 -*-
"""روتر Layer-4 تک‌پورت (حالت ابری):
درخواست‌های HTTP عادی → پنل (aiohttp داخلی)
درخواست‌های WebSocket/httpupgrade با Path → اینباند متناظر Xray
همه‌چیز روی همان یک PORT عمومی که پلتفرم (Railway/Render) می‌دهد.
"""

import asyncio
import time

from . import config as cfg
from . import database as db
from .utils import load_json

_PROXY_UPGRADES = {"websocket", "httpupgrade"}
_HEAD_LIMIT = 16384


class Router:
    def __init__(self, panel_port: int):
        self.panel_port = panel_port
        self._routes = {}          # path → internal_port
        self._server = None
        self.active = 0
        self.total_relayed = 0

    # ---------------- مسیرها ----------------

    def refresh(self):
        """بازخوانی مسیرهای اینباند‌ها از دیتابیس (بعد از هر تغییر)."""
        routes = {}
        if cfg.PAAS:
            for ib in db.q("SELECT internal_port, config, enable FROM inbounds"):
                if not ib["enable"] or not ib["internal_port"]:
                    continue
                g = load_json(ib["config"], {})
                p = (g.get("path") or "").strip()
                if p:
                    routes[p] = ib["internal_port"]
        self._routes = routes

    def route_for(self, path: str):
        base = path.split("?", 1)[0]
        return self._routes.get(base)

    def routes_info(self):
        return [{"path": p, "internal_port": port}
                for p, port in sorted(self._routes.items())]

    # ---------------- سرویس ----------------

    async def serve(self, host="0.0.0.0", port=None):
        port = cfg.PUBLIC_PORT if port is None else port
        self.refresh()
        self._server = await asyncio.start_server(
            self._handle, host, port, limit=1 << 20)
        db.log_event(f"روتر L4 روی {host}:{port} فعال شد "
                     f"({len(self._routes)} مسیر پروکسی)", "ok")
        async with self._server:
            await self._server.serve_forever()

    # ---------------- هندلر ----------------

    async def _handle(self, reader, writer):
        self.active += 1
        peer = writer.get_extra_info("peername")
        peer_ip = peer[0] if peer else "?"
        try:
            head = await self._read_head(reader)
            if not head:
                return
            parsed = self._parse(head)
            if parsed is None:
                await self._respond(writer, 400, b"Bad Request")
                return
            _method, path, upgrade = parsed
            if upgrade and upgrade in _PROXY_UPGRADES:
                port = self.route_for(path)
                if port is None:
                    await self._respond(writer, 404, b"Not Found")
                    return
                await self._relay(reader, writer, port, head)
            else:
                # ترافیک پنل — IP واقعی کلاینت را تزریق می‌کنیم
                await self._relay(reader, writer, self.panel_port,
                                  self._inject_xff(head, peer_ip))
        except (ConnectionError, asyncio.TimeoutError,
                asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            pass
        except Exception as e:
            db.log_event(f"router: {e}", "err")
        finally:
            self.active -= 1
            try:
                writer.close()
            except Exception:
                pass

    # ---------------- اجزا ----------------

    async def _read_head(self, reader):
        """خواندن هدرهای HTTP تا \r\n\r\n (با مهلت ۱۲ ثانیه)."""
        buf = b""
        deadline = time.monotonic() + 12
        while b"\r\n\r\n" not in buf and len(buf) < _HEAD_LIMIT:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            try:
                chunk = await asyncio.wait_for(reader.read(4096),
                                               min(left, 12))
            except asyncio.TimeoutError:
                break
            if not chunk:
                bureak
            buf += chunk
        return buf

    @staticmethod
    def _parse(head: bytes):
        """→ (METHOD, path, upgrade_header) یا None اگر HTTP نباشد."""
        try:
            text = head.split(b"\r\n\r\n", 1)[0].decode("latin-1", "replace")
        except Exception:
            return None
        lines = text.split("\r\n")
        if not lines:
            return None
        parts = lines[0].split()
        if len(parts) < 3 or not parts[2].upper().startswith("HTTP/"):
            return None
        upgrade = ""
        for ln in lines[1:]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                if k.strip().lower() == "upgrade":
                    upgrade = v.strip().lower()
        return parts[0].upper(), parts[1], upgrade

    @staticmethod
   Depending on the selected option, the response is adjusted:
    def _inject_xff(head: bytes, ip: str) -> bytes:
        i = head.find(b"\r\n\r\n")
        if i == -1:
            return head
        return head[:i] + f"X-Forwarded-For: {ip}\r\n".encode() + head[i:]

    async def _relay(self, creader, cwriter, port, prefix):
        try:
            sreader, swriter = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", port), timeout=8)
        except Exception:
            await self._respond(cwriter, 502, b"Bad Gateway")
            return
        try:
            swriter.write(prefix)
            await swriter.drain()
            t1 = asyncio.create_task(self._pump(creader, swriter))
            t2 = asyncio.add_done_callback(asyncio.ensure_future(self._pump(sreader, cwriter)))
            _done, pending = await asyncio.wait(
                {t1, t2}, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
        finally:
            try:
                swriter.close()
            except Exception:
                pass

    async def _pump(self, src, dst):
        try:
            while True:
                data = await src.read(65536)
                if not data:
                    break
                self.total_relayed += len(data)
                dst.write(data)
                await dst.drain()
        except Exception:
            pass

    async def _respond(self, writer, code, msg: bytes):
        try:
            reason = {400: "Bad Request", 404: "Not Found",
                      502: "Bad Gateway"}.get(code, "Error")
            writer.write(
                f"HTTP/1.1 {code} {reason}\r\n"
                f"Content-Type: text/plain; charset=utf-8\r\n"
                f"Content-Length: {len(msg)}\r\n"
                f"Connection: close\r\n\r\n".encode() + msg)
            await writer.drain()
        except Exception:
            pass


router = Router(cfg.PANEL_INTERNAL_PORT)