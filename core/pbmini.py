# -*- coding: utf-8 -*-
"""Encoder/Decoder مینیمال protobuf — فقط چیزی که API آمار Xray لازم دارد."""


def varint(value: int) -> bytes:
    if value < 0:
        value += 1 << 64
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _tag(field: int, wire: int) -> bytes:
    return varint((field << 3) | wire)


def f_str(field: int, value: str) -> bytes:
    data = value.encode("utf-8")
    return _tag(field, 2) + varint(len(data)) + data


def f_uint(field: int, value: int) -> bytes:
    return _tag(field, 0) + varint(int(value))


def f_bool(field: int, value: bool) -> bytes:
    return _tag(field, 0) + varint(1 if value else 0)


def read_varint(buf: bytes, pos: int):
    result, shift = 0, 0
    while True:
        if pos >= len(buf):
            raise ValueError("truncated varint")
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


def parse(buf: bytes):
    """→ لیستی از (field_number, wire_type, value) — value: int یا bytes."""
    out, pos, n = [], 0, len(buf)
    while pos < n:
        t, pos = read_varint(buf, pos)
        field, wire = t >> 3, t & 7
        if wire == 0:
            v, pos = read_varint(buf, pos)
        elif wire == 1:
            v, pos = buf[pos:pos + 8], pos + 8
        elif wire == 2:
            ln, pos = read_varint(buf, pos)
            v, pos = buf[pos:pos + ln], pos + ln
        elif wire == 5:
            v, pos = buf[pos:pos + 4], pos + 4
        else:
            break
        out.append((field, wire, v))
    return out