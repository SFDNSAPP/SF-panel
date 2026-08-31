# -*- coding: utf-8 -*-
"""ابزارهای مشترک API — پاسخ JSON، احراز هویت، IP کلاینت، اجرای executor."""

import asyncio
import functools
import json

from aiohttp import web

from core import config as cfg
from core import database as db
from core.security import verify_token
from core.xray import xray
from core.router import router

_bg_tasks = set()


def _dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False)


def json_ok(data, status: int = 200) -> web.Response:
    return web.json_response(data, status=status, dumps=_dumps)


def json_err(msg, status: int = 400) -> web.Response:
    return web.json_response({"error": msg}, status=status, dumps=_dumps)


async def body_json(request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def client_ip(request) -> str:
    """IP واقعی — در حالت PaaS روتر آن را در XFF تزریق می‌کند."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return request.remote or "?"


def bearer_token(request) -> str:
    h = request.headers.get("Authorization", "")
    if h.startswith("Bearer "):
        return h[7:].strip()
    return ""


def auth_required(fn):
    @functools.wraps(fn)
    async def wrapped(request):
        user = verify_token(bearer_token(request), db.get_setting("secret"))
        if not user:
            return json_err("نشست نامعتبر یا منقضی است.", 401)
        request["user"] = user
        return await fn(request)
    return wrapped


def path_int(request, key: str = "id"):
    try:
        return int(request.match_info[key])
    except (KeyError, ValueError):
        return None


async def run_ex(fn, *args, **kwargs):
    """اجرای تابع سنگین/همگام در thread pool تا event loop قفل نشود."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))


def spawn_bg(coro) -> None:
    """اجرای coroutine در پس‌زمینه بدون بلاک کردن پاسخ."""
    loop = asyncio.get_running_loop()
    t = loop.create_task(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)


async def apply_config():
    """اعمال کانفیگ جدید روی هسته + رفرش مسیرهای روتر. → (ok, error)"""
    ok, err = await run_ex(xray.restart, "تغییر پیکربندی")
    router.refresh()
    return ok, err