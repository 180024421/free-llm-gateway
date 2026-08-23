# -*- coding: utf-8 -*-
"""Optional DPAPI encryption for upstream API keys (Windows)."""
from __future__ import annotations

import base64
import sys
from typing import Any

_ENC_PREFIX = "enc:v1:"


def encryption_enabled(cfg: dict[str, Any] | None = None) -> bool:
    if cfg is None:
        from .config import load_config

        cfg = load_config()
    if cfg.get("encrypt_provider_keys") is False:
        return False
    if cfg.get("encrypt_provider_keys") is True:
        return True
    return sys.platform.startswith("win")


def _protect_windows(plain: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    in_blob = DATA_BLOB(len(plain), ctypes.cast(ctypes.create_string_buffer(plain), ctypes.POINTER(ctypes.c_char)))
    out_blob = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "DashuaiGateway",
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _unprotect_windows(blob: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    in_blob = DATA_BLOB(len(blob), ctypes.cast(ctypes.create_string_buffer(blob), ctypes.POINTER(ctypes.c_char)))
    out_blob = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def encrypt_secret(value: str, *, cfg: dict[str, Any] | None = None) -> str:
    s = (value or "").strip()
    if not s or s.startswith(_ENC_PREFIX):
        return value or ""
    if not encryption_enabled(cfg):
        return s
    if not sys.platform.startswith("win"):
        return s
    try:
        blob = _protect_windows(s.encode("utf-8"))
        return _ENC_PREFIX + base64.b64encode(blob).decode("ascii")
    except Exception:
        return s


def decrypt_secret(value: str, *, cfg: dict[str, Any] | None = None) -> str:
    s = value or ""
    if not s.startswith(_ENC_PREFIX):
        return s
    if not sys.platform.startswith("win"):
        return ""
    try:
        blob = base64.b64decode(s[len(_ENC_PREFIX) :])
        return _unprotect_windows(blob).decode("utf-8")
    except Exception:
        return ""


def scrub_providers_for_save(providers: list[dict[str, Any]], cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in providers:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        key = str(row.get("api_key") or "")
        if key and not key.startswith(_ENC_PREFIX):
            row["api_key"] = encrypt_secret(key, cfg=cfg)
        out.append(row)
    return out


def reveal_providers(providers: list[dict[str, Any]], cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in providers:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["api_key"] = decrypt_secret(str(row.get("api_key") or ""), cfg=cfg)
        out.append(row)
    return out
