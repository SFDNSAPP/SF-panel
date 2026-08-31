# -*- coding: utf-8 -*-
"""امنیت — هش رمز، توکن HMAC، TOTP (RFC 6238)، rate-limiter."""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import threading
import time

from . import config as cfg

# ---------------- رمز عبور (PBKDF2) ----------------

_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, dk_hex = stored.split("$", 3)
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, AttributeError):
        return False


# ---------------- توکن نشست (HMAC-SHA256) ----------------

def issue_token(user: str, secret: str, ttl: int = None) -> str:
    ttl = ttl or cfg.SESSION_TTL
    payload = base64.urlsafe_b64encode(json.dumps({
        "u": user,
        "exp": int(time.time()) + ttl,
        "jti": secrets.token_hex(8),
    }, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_token(token: str, secret: str):
    """در صورت اعتبار → username، وگرنه None."""
    if not token or not secret:
        return None
    try:
        payload, sig = token.rsplit(".", 1)
        expect = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expect, sig):
            return None
        pad = "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload + pad))
        if data.get("exp", 0) < time.time():
            return None
        return data.get("u")
    except (ValueError, KeyError, TypeError):
        return None


# ---------------- TOTP (Google Authenticator سازگار) ----------------

def totp_generate_secret(length: int = 20) -> str:
    return base64.b32encode(secrets.token_bytes(length)).decode().rstrip("=")


def totp_code(secret: str, at: float = None, step: int = 30, digits: int = 6) -> str:
    if at is None:
        at = time.time()
    counter = int(at // step)
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    val = (struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(val).zfill(digits)


def totp_verify(secret: str, code: str, window: int = 1) -> bool:
    if not secret or not code or not code.strip().isdigit():
        return False
    code = code.strip()
    now = time.time()
    return any(hmac.compare_digest(totp_code(secret, now + d * 30), code)
               for d in range(-window, window + 1))


def totp_uri(secret: str, account: str, issuer: str = "SF-Panel") -> str:
    from urllib.parse import quote
    return (f"otpauth://totp/{quote(issuer)}:{quote(account)}"
            f"?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30")


# ---------------- Rate Limiter ----------------

class RateLimiter:
    """محدودیت تلاش بر اساس کلید (مثلاً IP) در پنجره زمانی."""

    def __init__(self, max_tries: int, window: int):
        self.max = max_tries
        self.window = window
        self._hits: dict = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """True اگر مجاز باشد. تلاش ناموفق را خودتان با fail() ثبت کنید."""
        now = time.time()
        with self._lock:
            self._gc(now)
            cnt, ts0 = self._hits.get(key, (0, now))
            if now - ts0 > self.window:
                cnt, ts0 = 0, now
            return cnt < self.max

    def fail(self, key: str) -> None:
        now = time.time()
        with self._lock:
            cnt, ts0 = self._hits.get(key, (0, now))
            if now - ts0 > self.window:
                cnt, ts0 = 0, now
            self._hits[key] = (cnt + 1, ts0)

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def _gc(self, now: float) -> None:
        if len(self._hits) > 4096:
            self._hits = {k: v for k, v in self._hits.items()
                          if now - v[1] <= self.window}


login_limiter = RateLimiter(cfg.LOGIN_MAX_TRIES, cfg.LOGIN_WINDOW)


# ---------------- متفرقه ----------------

def random_token(nbytes: int = 9) -> str:
    return secrets.token_urlsafe(nbytes)


def random_password(length: int = 16) -> str:
    import string
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))