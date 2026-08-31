# -*- coding: utf-8 -*-
"""ابزارهای کوچک مشترک."""
import json
import time


def now_ms() -> int:
    return int(time.time() * 1000)


def load_json(text, default):
    if not text:
        return default
    try:
        v = json.loads(text)
        return v if v is not None else default
    except (ValueError, TypeError):
        return default


def dump_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def to_int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def fmt_bytes(n) -> str:
    n = float(n or 0)
    neg = n < 0
    n = abs(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if n < 1024 or unit == "PB":
            s = f"{n:.2f}".rstrip("0").rstrip(".")
            return ("-" if neg else "") + (f"{s} {unit}" if unit != "B" else f"{int(n)} B")
        n /= 1024
    return "0 B"


def fmt_duration(seconds) -> str:
    seconds = int(seconds or 0)
    if seconds <= 0:
        return "0s"
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s and not d: parts.append(f"{s}s")
    return " ".join(parts) or "0s"


def deep_merge(base: dict, patch: dict) -> dict:
    """ادغام عمیق؛ patch روی base برنده است."""
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def is_safe_path(path: str) -> bool:
    """مسیر WS/گرپ‌سی امن برای اینباند."""
    import re
    return bool(re.match(r"^/[A-Za-z0-9_\-./]{1,120}$", path or "")) \
        and ".." not in path and not path.endswith("/")