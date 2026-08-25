"""License gate: session cache + remote entitlement against run-jane."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import platform
import secrets as pysecrets
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import HTTPException

from .commercial import (
    bill_estimated_usage,
    force_https_url,
    is_commercial_build,
    migrate_public_license_base,
    offline_grace_sec,
    online_cache_sec,
    reserve_tokens_default,
)
from .config import DATA_DIR, load_config, save_json, load_json

SESSION_PATH = DATA_DIR / "session.json"
_SECRET_PATH_NAME = ".license_hmac"
_refresh_ts = 0.0
_REFRESH_INTERVAL = 300.0

_reserve_lock = asyncio.Lock()
_reserved_tokens = 0


def session_path() -> Path:
    """Always resolve against current DATA_DIR (EXE may set it after import)."""
    from . import config as cfg_mod

    return Path(cfg_mod.DATA_DIR) / "session.json"


def _hmac_secret() -> bytes:
    """Per-install HMAC secret (DPAPI-sealed on Windows when possible)."""
    from . import config as cfg_mod

    path = Path(cfg_mod.DATA_DIR) / _SECRET_PATH_NAME
    Path(cfg_mod.DATA_DIR).mkdir(parents=True, exist_ok=True)
    raw = b""
    if path.exists():
        try:
            blob = path.read_text(encoding="utf-8").strip()
            from .secrets import decrypt_secret

            plain = decrypt_secret(blob) if blob.startswith("enc:v1:") else blob
            raw = bytes.fromhex(plain) if all(c in "0123456789abcdef" for c in plain.lower()) and len(plain) >= 32 else plain.encode("utf-8")
        except Exception:
            raw = b""
    if len(raw) < 16:
        raw = pysecrets.token_bytes(32)
        try:
            from .secrets import encrypt_secret

            sealed = encrypt_secret(raw.hex())
            path.write_text(sealed if sealed.startswith("enc:v1:") else raw.hex(), encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except Exception:
                pass
        except Exception:
            path.write_text(raw.hex(), encoding="utf-8")
    return raw


def license_required(cfg: dict[str, Any] | None = None) -> bool:
    cfg = cfg or load_config()
    if is_commercial_build(cfg):
        return True
    flag = cfg.get("require_license")
    if flag is False:
        return False
    if flag is True:
        return True
    return bool((cfg.get("license_api_base") or "").strip())


def device_fingerprint() -> str:
    raw = f"{platform.node()}|{platform.system()}|{os.environ.get('USERNAME') or os.environ.get('USER') or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _sign_payload(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    key = _hmac_secret() + device_fingerprint().encode("utf-8")
    return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()


def load_session() -> dict[str, Any]:
    data = load_json(session_path(), {})
    if not isinstance(data, dict):
        return {}
    try:
        from .secrets import open_session_secrets

        data = open_session_secrets(data)
    except Exception:
        pass
    ent = data.get("entitlement")
    if isinstance(ent, dict) and ent.get("_sig"):
        check = {k: v for k, v in ent.items() if k != "_sig"}
        if not hmac.compare_digest(_sign_payload(check), str(ent.get("_sig"))):
            data["entitlement"] = None
            data["entitlement_corrupt"] = True
    return data


def save_session(data: dict[str, Any]) -> None:
    from . import config as cfg_mod

    Path(cfg_mod.DATA_DIR).mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    ent = payload.get("entitlement")
    if isinstance(ent, dict):
        clean = {k: v for k, v in ent.items() if k != "_sig"}
        clean["device"] = device_fingerprint()
        clean["_sig"] = _sign_payload(clean)
        payload["entitlement"] = clean
    try:
        from .secrets import seal_session_secrets

        payload = seal_session_secrets(payload)
    except Exception:
        pass
    save_json(session_path(), payload)


def clear_session() -> None:
    path = session_path()
    if path.exists():
        path.unlink()


def jane_base(cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load_config()
    raw = migrate_public_license_base((cfg.get("license_api_base") or "").strip())
    if not raw:
        return ""
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    is_local = host in {"127.0.0.1", "localhost", "::1"}
    is_ip = bool(host) and host.replace(".", "").isdigit()
    allow_insecure = bool(cfg.get("license_allow_insecure_http"))
    # 仅本机 / 裸 IP 在显式允许时可用 HTTP；花生壳等域名一律保持 HTTPS
    if parsed.scheme.lower() == "https" and allow_insecure and (is_local or is_ip):
        raw = urlunparse(("http", parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
        return raw.rstrip("/")
    if is_local or (allow_insecure and is_ip):
        return raw.rstrip("/")
    return force_https_url(raw).rstrip("/")


def _auth_header(token: str | None = None) -> dict[str, str]:
    tok = token
    if not tok:
        tok = (load_session().get("token") or "").strip()
    if not tok:
        return {}
    return {"Authorization": f"LiDaShuai {tok}"}


def _unwrap(body: Any) -> Any:
    if isinstance(body, dict) and "data" in body and "code" in body:
        code = body.get("code")
        if code not in (200, "200", None):
            msg = body.get("message") or "remote error"
            raise HTTPException(status_code=400, detail=str(msg))
        return body.get("data")
    return body


async def jane_request(
    method: str,
    path: str,
    *,
    json_body: Any = None,
    params: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: float = 30.0,
) -> Any:
    base = jane_base()
    if not base:
        raise HTTPException(status_code=503, detail="未配置 license_api_base，无法连接授权服务")
    if base.lower().startswith("http://") and is_commercial_build():
        host = ""
        try:
            from urllib.parse import urlparse

            host = (urlparse(base).hostname or "").lower()
        except Exception:
            host = ""
        allow_insecure = bool(load_config().get("license_allow_insecure_http"))
        if host not in {"127.0.0.1", "localhost", "::1"} and not allow_insecure and not host.replace(".", "").isdigit():
            raise HTTPException(status_code=503, detail="正式版要求 license_api_base 使用 HTTPS（或设置 license_allow_insecure_http）")
    url = f"{base}{path if path.startswith('/') else '/' + path}"
    headers = {"Accept": "application/json", **_auth_header(token)}
    try:
        headers["X-Device-Fingerprint"] = device_fingerprint()
    except Exception:
        pass
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.request(method.upper(), url, json=json_body, params=params, headers=headers)
    try:
        body = resp.json()
    except Exception:
        body = {"message": resp.text[:500]}
    if resp.status_code >= 400:
        msg = body.get("message") if isinstance(body, dict) else str(body)
        raise HTTPException(status_code=resp.status_code, detail=msg or f"HTTP {resp.status_code}")
    if isinstance(body, dict) and body.get("code") not in (None, 200, "200"):
        raise HTTPException(status_code=400, detail=str(body.get("message") or "业务错误"))
    return _unwrap(body)


def cache_entitlement(status: dict[str, Any]) -> None:
    sess = load_session()
    sess["entitlement"] = {
        "valid": bool(status.get("valid")),
        "expire_at": status.get("expireAt") or status.get("expire_at"),
        "token_quota": status.get("tokenQuota") if status.get("tokenQuota") is not None else status.get("token_quota"),
        "token_used": status.get("tokenUsed") if status.get("tokenUsed") is not None else status.get("token_used"),
        "token_remaining": status.get("tokenRemaining") if status.get("tokenRemaining") is not None else status.get("token_remaining"),
        "token_unlimited": bool(status.get("tokenUnlimited") if status.get("tokenUnlimited") is not None else status.get("token_unlimited")),
        "time_unlimited": bool(status.get("timeUnlimited") if status.get("timeUnlimited") is not None else status.get("time_unlimited")),
        "plan_label": status.get("planLabel") or status.get("plan_label"),
        "message": status.get("message"),
        "user_id": status.get("userId") or status.get("user_id"),
        "username": status.get("username"),
        "project_id": status.get("projectId") or status.get("project_id"),
        "frozen": bool(status.get("frozen")),
        "frozen_reason": status.get("frozenReason") or status.get("frozen_reason") or "",
        "low_balance": bool(status.get("lowBalance") if status.get("lowBalance") is not None else status.get("low_balance")),
        "device_bound": bool(status.get("deviceBound") if status.get("deviceBound") is not None else status.get("device_bound")),
        "cached_at": time.time(),
        "online_verified_at": time.time(),
    }
    if status.get("username"):
        sess["username"] = status.get("username")
    if status.get("userId") or status.get("user_id"):
        sess["user_id"] = status.get("userId") or status.get("user_id")
    save_session(sess)


def entitlement_snapshot() -> dict[str, Any]:
    sess = load_session()
    ent = sess.get("entitlement") if isinstance(sess.get("entitlement"), dict) else {}
    remaining = ent.get("token_remaining")
    try:
        if remaining is not None and not ent.get("token_unlimited"):
            remaining = max(0, int(remaining) - int(_reserved_tokens))
    except Exception:
        pass
    return {
        "logged_in": bool(sess.get("token")),
        "username": sess.get("username"),
        "user_id": sess.get("user_id"),
        "valid": bool(ent.get("valid")),
        "expire_at": ent.get("expire_at"),
        "token_quota": ent.get("token_quota"),
        "token_used": ent.get("token_used"),
        "token_remaining": remaining,
        "token_unlimited": bool(ent.get("token_unlimited")),
        "time_unlimited": bool(ent.get("time_unlimited")),
        "plan_label": ent.get("plan_label"),
        "message": ent.get("message") or ("未登录" if not sess.get("token") else "未激活"),
        "project_id": ent.get("project_id") or load_config().get("license_project_id"),
        "require_license": license_required(),
        "cached_at": ent.get("cached_at"),
        "online_verified_at": ent.get("online_verified_at"),
        "pending_usage_count": len(sess.get("pending_usage") or []) if isinstance(sess.get("pending_usage"), list) else 0,
        "pending_usage_last_error": sess.get("pending_usage_last_error"),
        "reserved_tokens": int(_reserved_tokens),
        "commercial_mode": is_commercial_build(),
        "offline_grace_sec": offline_grace_sec(load_config()),
        "frozen": bool(ent.get("frozen")),
        "frozen_reason": ent.get("frozen_reason") or "",
        "low_balance": bool(ent.get("low_balance")),
        "device_bound": bool(ent.get("device_bound")),
    }


def _local_still_valid(ent: dict[str, Any], max_age: float) -> bool:
    if not ent.get("valid"):
        return False
    cached_at = float(ent.get("cached_at") or 0)
    if time.time() - cached_at > max_age:
        return False
    expire_at = ent.get("expire_at")
    if expire_at:
        try:
            from datetime import datetime

            s = str(expire_at).replace("T", " ")[:19]
            if datetime.strptime(s, "%Y-%m-%d %H:%M:%S").timestamp() < time.time():
                return False
        except Exception:
            pass
    if ent.get("token_unlimited"):
        return True
    quota = int(ent.get("token_quota") or 0)
    used = int(ent.get("token_used") or 0)
    remaining = ent.get("token_remaining")
    if remaining is not None:
        try:
            if int(remaining) - int(_reserved_tokens) <= 0 and quota > 0:
                return False
        except Exception:
            pass
    if quota > 0 and used >= quota:
        return False
    return True


async def refresh_status(force: bool = False) -> dict[str, Any]:
    global _refresh_ts
    sess = load_session()
    if not sess.get("token"):
        return entitlement_snapshot()
    if not force and time.time() - _refresh_ts < 30:
        return entitlement_snapshot()
    try:
        data = await jane_request("GET", "/gateway/license/status", timeout=8.0)
        if isinstance(data, dict):
            cache_entitlement(data)
            _refresh_ts = time.time()
    except HTTPException:
        pass
    return entitlement_snapshot()


async def require_entitlement() -> dict[str, Any]:
    cfg = load_config()
    if not license_required(cfg):
        return {"valid": True, "bypassed": True}
    sess = load_session()
    if not sess.get("token"):
        raise HTTPException(
            status_code=403,
            detail={"message": "请先登录并激活卡密", "code": "LICENSE_REQUIRED"},
        )
    ent = sess.get("entitlement") if isinstance(sess.get("entitlement"), dict) else {}
    cache_age = online_cache_sec(cfg)
    grace = offline_grace_sec(cfg)

    # Fresh enough local cache: allow without remote round-trip.
    if _local_still_valid(ent, max_age=cache_age):
        return ent

    # Cache stale → force online verification when possible.
    snap = await refresh_status(force=True)
    if snap.get("valid"):
        return snap

    # Remote down: short offline grace only (commercial much shorter than old 72h).
    if ent.get("valid") and _local_still_valid(ent, max_age=grace):
        return ent

    raise HTTPException(
        status_code=402,
        detail={
            "message": snap.get("message") or "权益无效或需联网校验，请购买/续费后重试",
            "code": "LICENSE_INVALID",
            "license": snap,
        },
    )


async def reserve_quota(tokens: int | None = None) -> int:
    """Pre-reserve tokens before upstream call to reduce concurrent oversell."""
    global _reserved_tokens
    cfg = load_config()
    if not license_required(cfg):
        return 0
    n = int(tokens if tokens is not None else reserve_tokens_default(cfg))
    if n <= 0:
        return 0
    async with _reserve_lock:
        sess = load_session()
        ent = sess.get("entitlement") if isinstance(sess.get("entitlement"), dict) else {}
        if ent.get("token_unlimited"):
            return 0
        quota = int(ent.get("token_quota") or 0)
        if quota <= 0:
            return 0
        remaining = ent.get("token_remaining")
        try:
            rem = int(remaining) if remaining is not None else max(0, quota - int(ent.get("token_used") or 0))
        except Exception:
            rem = 0
        avail = rem - int(_reserved_tokens)
        if avail < n:
            raise HTTPException(
                status_code=402,
                detail={
                    "message": f"Token 余量不足（可用约 {max(0, avail)}，本次预留 {n}）",
                    "code": "TOKEN_INSUFFICIENT",
                    "license": entitlement_snapshot(),
                },
            )
        _reserved_tokens += n
        return n


async def release_quota(reserved: int, actual: int = 0) -> None:
    global _reserved_tokens
    if reserved <= 0 and actual <= 0:
        return
    async with _reserve_lock:
        _reserved_tokens = max(0, int(_reserved_tokens) - max(0, int(reserved)))
        # Local used bump is handled by report_usage / cache from server.


async def report_usage(tokens: int, request_id: str | None = None, *, estimated: bool = False) -> None:
    if tokens <= 0 or not license_required():
        return
    cfg = load_config()
    if estimated and not bill_estimated_usage(cfg):
        return
    sess = load_session()
    if not sess.get("token"):
        return
    rid = (request_id or str(uuid.uuid4())).strip()
    body = {"requestId": rid, "tokens": int(tokens)}
    if estimated:
        body["estimated"] = True
    try:
        data = await jane_request(
            "POST",
            "/gateway/license/usage",
            json_body=body,
            timeout=12.0,
        )
        if isinstance(data, dict):
            cache_entitlement(data)
    except Exception:
        pending = sess.get("pending_usage") if isinstance(sess.get("pending_usage"), list) else []
        pending.append({"requestId": rid, "tokens": int(tokens), "ts": time.time(), "estimated": bool(estimated)})
        sess["pending_usage"] = pending[-80:]
        ent = sess.get("entitlement") if isinstance(sess.get("entitlement"), dict) else {}
        if ent:
            used = int(ent.get("token_used") or 0) + int(tokens)
            ent["token_used"] = used
            quota = int(ent.get("token_quota") or 0)
            if quota > 0:
                ent["token_remaining"] = max(0, quota - used)
                if used >= quota:
                    ent["valid"] = False
                    ent["message"] = "Token 已用尽"
            sess["entitlement"] = ent
        sess["pending_usage_last_error"] = "用量暂存本地，联网后自动上报"
        save_session(sess)


async def flush_pending_usage() -> None:
    sess = load_session()
    pending = sess.get("pending_usage") if isinstance(sess.get("pending_usage"), list) else []
    if not pending or not sess.get("token"):
        return
    left = []
    for item in pending:
        try:
            body = {"requestId": item.get("requestId"), "tokens": item.get("tokens") or 0}
            if item.get("estimated"):
                body["estimated"] = True
            data = await jane_request(
                "POST",
                "/gateway/license/usage",
                json_body=body,
                timeout=12.0,
            )
            if isinstance(data, dict):
                cache_entitlement(data)
        except Exception:
            left.append(item)
    sess = load_session()
    sess["pending_usage"] = left
    if left:
        sess["pending_usage_last_error"] = f"仍有 {len(left)} 条用量未上报，将在下次联网重试"
    else:
        sess.pop("pending_usage_last_error", None)
    save_session(sess)


def schedule_usage_from_row(row: dict[str, Any]) -> None:
    if not row.get("ok") or not license_required():
        return
    usage = row.get("usage") if isinstance(row.get("usage"), dict) else {}
    estimated = bool(row.get("usage_estimated") or usage.get("estimated"))
    cfg = load_config()
    if estimated and not bill_estimated_usage(cfg):
        return
    pt = int(usage.get("prompt_tokens") or row.get("pt") or 0)
    ct = int(usage.get("completion_tokens") or row.get("ct") or 0)
    tt = int(usage.get("total_tokens") or row.get("tt") or (pt + ct))
    if tt <= 0:
        return
    rid = str(row.get("request_id") or uuid.uuid4())
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(report_usage(tt, rid, estimated=estimated))
    except RuntimeError:
        sess = load_session()
        pending = sess.get("pending_usage") if isinstance(sess.get("pending_usage"), list) else []
        pending.append({"requestId": rid, "tokens": tt, "ts": time.time(), "estimated": estimated})
        sess["pending_usage"] = pending[-80:]
        save_session(sess)
