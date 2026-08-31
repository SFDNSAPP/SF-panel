# -*- coding: utf-8 -*-
"""مدیریت هسته Xray — دانلود، اجرا، rollback خودکار، واچ‌داگ، ابزارها."""

import os
import platform
import re
import shutil
import subprocess
import threading
import time
import zipfile

import requests

from . import config as cfg
from . import database as db
from . import inbound_builder as ibld
from .grpc_stats import XrayStatsClient


class XrayManager:
    def __init__(self):
        self._lock = threading.RLock()
        self.proc = None
        self.version = ""
        self.started_at = 0.0
        self.should_run = False
        self.last_error = ""
        self.last_good = None
        self.restarts = 0
        self._logf = None
        self._last_attempt = 0.0
        self.stats = XrayStatsClient(cfg.XRAY_API_PORT)

    # ---------------- وضعیت ----------------

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def state(self) -> dict:
        return {
            "running": self.alive(),
            "starting": self.should_run and not self.alive(),
            "version": self.version,
            "uptime": int(time.time() - self.started_at)
                      if (self.alive() and self.started_at) else 0,
            "restarts": self.restarts,
            "error": self.last_error,
        }

    @staticmethod
    def _pflags():
        return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}

    # ---------------- نصب هسته ----------------

    @staticmethod
    def asset_name() -> str:
        s = platform.system().lower()
        m = platform.machine().lower()
        if s == "linux":
            if m in ("aarch64", "arm64"):
                return "Xray-linux-arm64-v8a.zip"
            if m in ("armv7l", "armv6l", "arm"):
                return "Xray-linux-arm32-v7a.zip"
            return "Xray-linux-64.zip"
        if s == "darwin":
            return ("Xray-macOS-arm64-v8a.zip" if m in ("aarch64", "arm64")
                    else "Xray-macOS-64.zip")
        return ("Xray-windows-arm64-v8a.zip" if m in ("aarch64", "arm64")
                else "Xray-windows-64.zip")

    def ensure_binary(self, force=False):
        if os.path.isfile(cfg.XRAY_BIN) and not force:
            if not self.version:
                self.read_version()
            return
        cfg.ensure_dirs()
        pin = (os.environ.get("XRAY_VERSION")
               or db.get_setting("xray_version") or "").strip()
        if pin and not pin.startswith("v"):
            pin = "v" + pin
        base = os.environ.get("XRAY_DL_URL") or \
            "https://github.com/XTLS/Xray-core/releases/"
        if not base.endswith("/"):
            base += "/"
        url = base + (f"download/{pin}/" if pin else "latest/download/") \
            + self.asset_name()

        db.log_event("دانلود هسته Xray-core ... "
                     + (f"({pin})" if pin else "(latest)"))
        tmp = os.path.join(cfg.XRAY_DIR, "core.zip")
        try:
            with requests.get(url, stream=True, timeout=cfg.XRAY_DL_TIMEOUT) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        if chunk:
                            f.write(chunk)
            self._extract(tmp)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        self.read_version()
        db.log_event(f"هسته Xray نصب شد: {self.version or '?'}", "ok")

    def _extract(self, zip_path):
        exe = "xray.exe" if os.name == "nt" else "xray"
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()

            def pick(target):
                for n in names:
                    if n.split("/")[-1] == target:
                        return n
                return None

            binm = pick(exe)
            if binm is None:
                raise RuntimeError("باینری xray در آرشیو یافت نشد")
            mapping = {binm: cfg.XRAY_BIN}
            for dat in ("geoip.dat", "geosite.dat"):
                m = pick(dat)
                if m:
                    mapping[m] = os.path.join(cfg.XRAY_DIR, dat)
            for member, dest in mapping.items():
                with z.open(member) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
        if os.name != "nt":
            os.chmod(cfg.XRAY_BIN, 0o755)

    def read_version(self):
        try:
            out = subprocess.run([cfg.XRAY_BIN, "version"], capture_output=True,
                                 text=True, timeout=25, **self._pflags()).stdout
            self.version = out.splitlines()[0].strip() if out else ""
        except Exception:
            self.version = ""

    # ---------------- چرخه حیات ----------------

    def build_config(self) -> str:
        return ibld.build_full_config(cfg.PAAS)

    def _spawn(self) -> bool:
        try:
            self._logf = open(cfg.XRAY_LOG, "ab")
            self.proc = subprocess.Popen(
                [cfg.XRAY_BIN, "run", "-c", cfg.XRAY_CFG],
                stdout=self._logf, stderr=subprocess.STDOUT,
                cwd=cfg.XRAY_DIR, **self._pflags())
            return True
        except Exception as e:
            self.last_error = f"اجرای xray ناموفق: {e}"
            return False

    def stop(self):
        with self._lock:
            if self.proc is not None:
                if self.proc.poll() is None:
                    try:
                        self.proc.terminate()
                    except Exception:
                        pass
                    try:
                        self.proc.wait(4)
                    except Exception:
                        try:
                            self.proc.kill()
                        except Exception:
                            pass
                self.proc = None
            if self._logf:
                try:
                    self._logf.close()
                except Exception:
                    pass
                self._logf = None

    def _api_ready(self) -> bool:
        try:
            self.stats.query("user>>>", reset=False)
            return True
        except Exception:
            return False

    def apply(self, text: str):
        """نوشتن کانفیگ و اجرا؛ در صورت خطا بازگشت خودکار به کانفیگ سالم."""
        with self._lock:
            prev = self.last_good
            self.stop()
            with open(cfg.XRAY_CFG, "w", encoding="utf-8") as f:
                f.write(text)
            if not self._spawn():
                return False, self.last_error

            deadline = time.time() + cfg.XRAY_START_TIMEOUT
            while time.time() < deadline:
                if self.proc is None or self.proc.poll() is not None:
                    break  # پروسه مرد
                if self._api_ready():
                    self.last_good = text
                    self.last_error = ""
                    self.started_at = time.time()
                    return True, ""
                time.sleep(0.25)

            err = self.tail_log(8) or "Xray بالا نیامد (بدون پیام خطا)"
            self.last_error = err
            if prev and prev != text:
                db.log_event("کانفیگ جدید رد شد؛ بازگشت به پیکربندی سالم قبلی",
                             "warn")
                try:
                    with open(cfg.XRAY_CFG, "w", encoding="utf-8") as f:
                        f.write(prev)
                    if self._spawn():
                        time.sleep(1.0)
                        if self.proc is not None and self.proc.poll() is None:
                            self.started_at = time.time()
                except Exception:
                    pass
            return False, err

    def start(self):
        with self._lock:
            self.should_run = True
            self._last_attempt = time.time()
            try:
                self.ensure_binary()
            except Exception as e:
                self.last_error = f"نصب هسته ناموفق: {e}"
                db.log_event(self.last_error, "err")
                return False, self.last_error
            ok, err = self.apply(self.build_config())
            if ok:
                db.log_event("هسته Xray اجرا شد ✅", "ok")
            else:
                db.log_event(f"اجرای Xray ناموفق: {err}", "err")
            return ok, err

    def restart(self, reason=""):
        with self._lock:
            self.restarts += 1
            self._last_attempt = time.time()
            if not os.path.isfile(cfg.XRAY_BIN):
                return self.start()
            ok, err = self.apply(self.build_config())
            if ok and reason:
                db.log_event(f"راه‌اندازی مجدد Xray ({reason})", "info")
            return ok, err

    def update_core(self):
        with self._lock:
            db.log_event("به‌روزرسانی هسته Xray ...", "info")
            try:
                self.ensure_binary(force=True)
            except Exception as e:
                return False, f"دانلود ناموفق: {e}"
            ok, err = self.restart("به‌روزرسانی هسته")
            return ok, (self.version if ok else err)

    # ---------------- ابزارها ----------------

    def tail_log(self, n=30) -> str:
        try:
            with open(cfg.XRAY_LOG, "rb") as f:
                data = f.read()[-65536:]
            lines = data.decode("utf-8", "replace").strip().splitlines()
            return "\n".join(lines[-n:])
        except Exception:
            return ""

    def x25519(self) -> dict:
        out = subprocess.run([cfg.XRAY_BIN, "x25519"], capture_output=True,
                             text=True, timeout=25, **self._pflags()).stdout
        priv = re.search(r"Private key:\s*(\S+)", out)
        pub = re.search(r"Public key:\s*(\S+)", out)
        if priv and pub:
            return {"privateKey": priv.group(1), "publicKey": pub.group(1)}
        raise RuntimeError("خواندن خروجی x25519 ناموفق بود")

    def gen_selfsigned_cert(self, domain: str) -> dict:
        """گواهی خودامضای ۱۰ ساله با openssl → مسیر فایل‌ها."""
        if not re.match(r"^[A-Za-z0-9.\-]+$", domain or ""):
            raise ValueError("دامنه نامعتبر است")
        key = os.path.join(cfg.CERT_DIR, domain + ".key")
        crt = os.path.join(cfg.CERT_DIR, domain + ".crt")
        base_cmd = ["openssl", "req", "-x509", "-newkey", "rsa:2048",
                    "-sha256", "-days", "3650", "-nodes",
                    "-subj", f"/CN={domain}", "-keyout", key, "-out", crt]
        r = subprocess.run(base_cmd + ["-addext", f"subjectAltName=DNS:{domain}"],
                           capture_output=True, text=True, timeout=60,
                           **self._pflags())
        if r.returncode != 0:
            r = subprocess.run(base_cmd, capture_output=True, text=True,
                               timeout=60, **self._pflags())
        if r.returncode != 0 or not (os.path.isfile(key) and os.path.isfile(crt)):
            raise RuntimeError((r.stderr or "openssl اجرا نشد")[:300])
        return {"certFile": crt, "keyFile": key, "domain": domain}


xray = XrayManager()


def watchdog_loop(mgr: "XrayManager" = None):
    """نخ پس‌زمینه: اگر هسته سقوط کند، خودش دوباره بالا می‌آورد."""
    mgr = mgr or xray
    time.sleep(20)
    while True:
        time.sleep(10)
        try:
            if not mgr.should_run or mgr.alive():
                continue
            if time.time() - mgr._last_attempt < 30:
                continue  # تازه تلاش شده؛ صبر کن
            db.log_event("واچ‌داگ: هسته Xray پایین است؛ راه‌اندازی مجدد", "warn")
            mgr.start()
        except Exception as e:
            db.log_event(f"واچ‌داگ: {e}", "err")