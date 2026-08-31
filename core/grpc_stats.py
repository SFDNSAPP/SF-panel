# -*- coding: utf-8 -*-
"""کلاینت gRPC آمار Xray — با protobuf دست‌ساز (pbmini) و کانال کش‌شده."""
import threading

import grpc

from . import pbmini as pb

_SVC = "/xray.app.stats.command.StatsService"


class XrayStatsClient:
    def __init__(self, port: int):
        self._target = f"127.0.0.1:{port}"
        self._lock = threading.Lock()
        self._channel = None

    def _get_channel(self):
        with self._lock:
            if self._channel is None:
                self._channel = grpc.insecure_channel(
                    self._target,
                    options=[("grpc.enable_retries", 0),
                             ("grpc.keepalive_time_ms", 30000),
                             ("grpc.max_receive_message_length", 8 * 1024 * 1024)])
            return self._channel

    def _reset(self) -> None:
        with self._lock:
            if self._channel is not None:
                try:
                    self._channel.close()
                except Exception:
                    pass
                self._channel = None

    def _call(self, method: str, payload: bytes, timeout: float = 6.0) -> bytes:
        ch = self._get_channel()
        try:
            call = ch.unary_unary(method,
                                  request_serializer=lambda x: x,
                                  response_deserializer=lambda x: x)
            return call(payload, timeout=timeout)
        except Exception:
            self._reset()
            raise

    # ---------- QueryStats ----------
    def query(self, pattern: str = "user>>>", reset: bool = True) -> dict:
        """→ {counter_name: value} — مثل user>>>email>>>traffic>>>uplink"""
        req = pb.f_str(1, pattern) + pb.f_bool(2, reset)
        resp = self._call(f"{_SVC}/QueryStats", req)
        out = {}
        for f, w, v in pb.parse(resp):
            if f == 1 and w == 2:          # repeated Stat stat
                name, value = None, 0
                for f2, w2, v2 in pb.parse(v):
                    if f2 == 1 and w2 == 2:
                        name = v2.decode("utf-8", "replace")
                    elif f2 == 2 and w2 == 0:
                        value = v2
                if name:
                    out[name] = value
        return out

    # ---------- SysStats ----------
    def sys_stats(self) -> dict:
        """→ {uptime, goroutines, alloc, total_alloc, sys, live_objects}"""
        try:
            resp = self._call(f"{_SVC}/SysStats", b"")
        except Exception:
            return {}
        names = {1: "uptime", 2: "goroutines", 3: "alloc",
                 4: "total_alloc", 5: "sys", 8: "live_objects"}
        out = {}
        for f, w, v in pb.parse(resp):
            if w == 0 and f in names:
                out[names[f]] = v
        return out