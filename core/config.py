# -*- coding: utf-8 -*-
"""تنظیمات مرکزی — مسیرها، پورت‌ها، حالت دیپلوی."""
import os

APP_NAME = "SF-Panel"
APP_VERSION = "2.0.0"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _path(env_key: str, default_name: str) -> str:
    v = os.environ.get(env_key)
    if v:
        return os.path.abspath(os.path.expanduser(v))
    return os.path.join(BASE_DIR, default_name)


DATA_DIR = _path("SF_DATA_DIR", "data")
DB_PATH  = os.path.join(DATA_DIR, "panel.db")
XRAY_DIR = os.path.join(DATA_DIR, "xray")
XRAY_BIN = os.path.join(XRAY_DIR, "xray.exe" if os.name == "nt" else "xray")
XRAY_CFG = os.path.join(XRAY_DIR, "config.json")
XRAY_LOG = os.path.join(XRAY_DIR, "error.log")
CERT_DIR = os.path.join(DATA_DIR, "certs")

# ---------- حالت دیپلوی ----------
# PaaS  : یک پورت عمومی → روتر L4 → پنل + اینباند‌های داخلی (Railway/Render/Koyeb)
# VPS   : پنل روی پورت خودش، Xray مستقیم روی پورت‌های واقعی (Reality/TLS/gRPC کامل)
_mode = (os.environ.get("DEPLOY_MODE") or "auto").strip().lower()
if _mode in ("paas", "cloud", "railway", "render", "koyeb", "heroku"):
    PAAS = True
elif _mode in ("vps", "server", "dedicated", "local"):
    PAAS = False
else:
    PAAS = bool(os.environ.get("PORT"))  # پلتفرم‌های ابری PORT را ست می‌کنند

# ---------- پورت‌ها ----------
PUBLIC_PORT         = int(os.environ.get("PORT") or os.environ.get("PANEL_PORT") or 2087)
PANEL_INTERNAL_PORT = int(os.environ.get("PANEL_INTERNAL_PORT") or 21080)
XRAY_API_PORT       = int(os.environ.get("XRAY_API_PORT") or 15490)

# ---------- رفتار ----------
STATS_INTERVAL      = int(os.environ.get("STATS_INTERVAL") or 8)   # ثانیه
SESSION_TTL         = 7 * 86400
LOGIN_MAX_TRIES     = 5
LOGIN_WINDOW        = 300
MAX_EVENT_ROWS      = 3000
XRAY_START_TIMEOUT  = 6.0      # حداکثر انتظار برای بالا آمدن هسته
XRAY_DL_TIMEOUT     = 240      # ثانیه دانلود هسته

# استخر پورت داخلی اینباند‌ها (فقط PaaS)
INTERNAL_PORT_START = 20001
INTERNAL_PORT_END   = 25000


def ensure_dirs() -> None:
    for d in (DATA_DIR, XRAY_DIR, CERT_DIR):
        os.makedirs(d, exist_ok=True)