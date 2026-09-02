# -*- coding: utf-8 -*-
"""ط±ظˆطھط± Layer-4 â€” v4 SELF-HEALING
ظ‡ط± ط§طھطµط§ظ„طŒ ظ…ط³غŒط±ظ‡ط§ ط±ط§ ط¨ط§ ع©ط´ غ³ ط«ط§ظ†غŒظ‡ ط§ط² ط¯غŒطھط§ط¨غŒط³ ظ…غŒâ€Œط®ظˆط§ظ†ط¯ â€”
ظ‡ط± طھط؛غŒغŒط±غŒ (ط­طھغŒ ط§ط² ع©ظ†ط³ظˆظ„) ط¨ظ„ط§ظپط§طµظ„ظ‡ ط±ظˆغŒ ط±ظˆطھط± ط²ظ†ط¯ظ‡ ط§ط¹ظ…ط§ظ„ ظ…غŒâ€Œط´ظˆط¯.
"""

import asyncio
import time

from . import config as cfg
from . import database as db
from .utils import load_json

_PROXY_UPGRADES = {"websocket", "httpupgrade"}
_HEAD_LIMIT = 16384
_REFRESH_EVERY = 3.0


class Router:
    def __init__(self, panel_port: int):
        self.panel_port = panel_port
        self._routes = {}
        self._server = None
        self.active = 0
        self.total_relayed = 0
        self._last_refresh = 0.0

    # ---------------- ظ…ط³غŒط±ظ‡ط§ ----------------

    def refresh(self):
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
        self._last_refresh = time.time()

    def _maybe_refresh(self):
        if time.time() - self._last_refresh > _REFRESH_EVERY:
            try:
                self.refresh()
            except Exception:
                pass

    def route_for(self, path: str):
        self._maybe_refresh()
        return self._routes.get(path.split("?", 1)[0])

    def routes_info(self):
        self._maybe_refresh()
        return [{"path": p, "internal_port": port}
                for p, port in sorted(self._routes.items())]

    # ---------------- ط³ط±ظˆغŒط³ ----------------

    async def serve(self, host="0.0.0.0", port=None):
        port = cfg.PUBLIC_PORT if port is None else port
        self.refresh()
        self._server = await asyncio.start_server(
            self._handle, host, port, limit=1 << 20)
        db.log_event(f"ط±ظˆطھط± L4 ط±ظˆغŒ {host}:{port} ظپط¹ط§ظ„ ط´ط¯ "
                     f"({len(self._routes)} ظ…ط³غŒط± ظ¾ط±ظˆع©ط³غŒ)", "ok")
        async with self._server:
            await self._server.serve_forever()

    # ---------------- ظ‡ظ†ط¯ظ„ط± ----------------

    async def _handle(self, reader, writer):
        self.active += 1
        peer = writer.get_extra_info("peername")
        try:
            head = await self._read_head(reader)
            if not head:
                db.log_event(f"DEBUG router: empty head from {peer}", "warn")
                return
            parsed = self._parse(head)
            if parsed is None:
                preview = head[:300].decode("latin-1", "replace")
                db.log_event(
                    f"DEBUG router: PARSE FAILED from {peer} | "
                    f"raw_head={preview!r}", "err")
                await self._respond(writer, 400, b"SF-Router: Bad Request")
                return
            _method, path, upgrade = parsed
            db.log_event(
                f"DEBUG router: from {peer} method={_method} path={path} "
                f"upgrade={upgrade!r}", "info")
            if upgrade in _PROXY_UPGRADES:
                port = self.route_for(path)
                if port is None:
                    db.log_event(
                        f"DEBUG router: NO ROUTE for path={path} "
                        f"known_routes={list(self._routes.keys())}", "err")
                    await self._respond(writer, 404, b"SF-Router: Not Found")
                    return
                db.log_event(
                    f"DEBUG router: relaying {peer} path={path} "
                    f"-> 127.0.0.1:{port}", "info")
                await self._relay(reader, writer, port, head)
            else:
                await self._relay(reader, writer, self.panel_port, head)
        except (ConnectionError, asyncio.TimeoutError,
                asyncio.IncompleteReadError, asyncio.LimitOverrunError) as e:
            db.log_event(f"DEBUG router: conn error from {peer}: "
                         f"{type(e).__name__}", "warn")
        except Exception as e:
            db.log_event(f"router: {e}", "err")
        finally:
            self.active -= 1
            try:
                writer.close()
            except Exception:
                pass

    # ---------------- ط§ط¬ط²ط§ ----------------

    async def _read_head(self, reader):
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
                break
            buf += chunk
        return buf

    @staticmethod
    def _parse(head: bytes):
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

    async def _relay(self, creader, cwriter, port, prefix):
        try:
            sreader, swriter = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", port), timeout=8)
        except Exception:
            await self._respond(cwriter, 502, b"SF-Router: Bad Gateway")
            return
        try:
            swriter.write(prefix)
            await swriter.drain()
            t1 = asyncio.ensure_future(self._pump(creader, swriter))
            t2 = asyncio.ensure_future(self._pump(sreader, cwriter))
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
