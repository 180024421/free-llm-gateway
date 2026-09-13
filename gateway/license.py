"""License gate: session cache + remote entitlement against run-jane."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import platform
import secrets as pysecrets
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import HTTPException

from .crypto_transport import create_envelope, decrypt_response
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
_MACHINE_ID_FILE = "machine-id"
_refresh_ts = 0.0
_REFRESH_INTERVAL = 300.0

# Keep protocol scopes in one place so backend naming can be adjusted centrally.
SENSITIVE_SCOPES = {
    "user.login": "user.login",
    "user.register": "user.register",
    "user.refreshToken": "user.refreshToken",
    "gateway-license.redeem": "gateway-license.redeem",
    "gateway-license.status": "gateway-license.status",
    "gateway-license.usage": "gateway-license.usage",
    "gateway-license.usage-history": "gateway-license.usage-history",
}

_reserve_lock = asyncio.Lock()
_reserved_tokens = 0
_usage_batch_lock = threading.RLock()


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
    return license_api_configured(cfg)


def _legacy_device_fingerprint() -> str:
    """Pre-stable algorithm (hostname|OS|username); used once to migrate signed cache."""
    raw = f"{platform.node()}|{platform.system()}|{os.environ.get('USERNAME') or os.environ.get('USER') or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _machine_id_path() -> Path:
    from . import config as cfg_mod

    return Path(cfg_mod.DATA_DIR) / _MACHINE_ID_FILE


def _read_or_create_machine_id() -> str:
    path = _machine_id_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        mid = path.read_text(encoding="utf-8").strip()
        if mid:
            return mid
    mid = str(uuid.uuid4())
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, (mid + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    except FileExistsError:
        mid = path.read_text(encoding="utf-8").strip() or mid
    except Exception:
        try:
            path.write_text(mid + "\n", encoding="utf-8")
        except Exception:
            pass
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    return mid


def device_fingerprint() -> str:
    mid = _read_or_create_machine_id()
    return hashlib.sha256(f"dashuai-gateway:{mid}".encode("utf-8")).hexdigest()[:32]


def _sign_payload_for(payload: dict[str, Any], fingerprint: str) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    key = _hmac_secret() + fingerprint.encode("utf-8")
    return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()


def _verify_entitlement_sig(ent: dict[str, Any], fingerprint: str) -> bool:
    check = {k: v for k, v in ent.items() if k != "_sig"}
    expected = _sign_payload_for(check, fingerprint)
    return hmac.compare_digest(expected, str(ent.get("_sig")))


def _sign_payload(payload: dict[str, Any]) -> str:
    return _sign_payload_for(payload, device_fingerprint())


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
        fp = device_fingerprint()
        if not _verify_entitlement_sig(ent, fp):
            # Migration: older builds signed with hostname|OS|username fingerprint.
            if _verify_entitlement_sig(ent, _legacy_device_fingerprint()):
                clean = {k: v for k, v in ent.items() if k != "_sig"}
                clean["device"] = fp
                clean["_sig"] = _sign_payload(clean)
                data["entitlement"] = clean
                save_session(data)
            else:
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


def license_api_configured(cfg: dict[str, Any] | None = None) -> bool:
    return bool(jane_bases(cfg))


def _normalize_license_base(raw: str, cfg: dict[str, Any]) -> str:
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    is_local = host in {"127.0.0.1", "localhost", "::1"}
    is_ip = bool(host) and host.replace(".", "").isdigit()
    allow_insecure = bool(cfg.get("license_allow_insecure_http"))
    if parsed.scheme.lower() == "https" and allow_insecure and (is_local or is_ip):
        raw = urlunparse(("http", parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
        return raw.rstrip("/")
    if is_local or (allow_insecure and is_ip):
        return raw.rstrip("/")
    return force_https_url(raw).rstrip("/")


def _collect_base_urls(raw: Any, cfg: dict[str, Any]) -> list[str]:
    out: list[str] = []
    items: list[Any]
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str) and raw.strip():
        items = [raw]
    else:
        items = []
    for item in items:
        migrated = migrate_public_license_base(str(item or "").strip())
        if migrated:
            out.append(_normalize_license_base(migrated, cfg))
    return out


def jane_bases(cfg: dict[str, Any] | None = None) -> list[str]:
    cfg = cfg or load_config()
    bases = _collect_base_urls(cfg.get("license_api_base"), cfg)
    fallback_raw = cfg.get("license_api_base_fallback")
    if fallback_raw is not None:
        bases.extend(_collect_base_urls(fallback_raw, cfg))
    seen: set[str] = set()
    ordered: list[str] = []
    for base in bases:
        b = base.rstrip("/")
        if b and b not in seen:
            seen.add(b)
            ordered.append(b)
    return ordered


def jane_base(cfg: dict[str, Any] | None = None) -> str:
    bases = jane_bases(cfg)
    return bases[0] if bases else ""


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


def _is_auth_failure(status_code: int) -> bool:
    return status_code in (401, 403)


def _is_retryable_http(status_code: int) -> bool:
    return status_code >= 500


def _assert_commercial_https(base: str) -> None:
    if not base.lower().startswith("http://") or not is_commercial_build():
        return
    host = ""
    try:
        from urllib.parse import urlparse

        host = (urlparse(base).hostname or "").lower()
    except Exception:
        host = ""
    allow_insecure = bool(load_config().get("license_allow_insecure_http"))
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_insecure and not host.replace(".", "").isdigit():
        raise HTTPException(status_code=503, detail="正式版要求 license_api_base 使用 HTTPS（或设置 license_allow_insecure_http）")


def invalidate_auth_session(message: str = "请重新登录") -> None:
    sess = load_session()
    ent = sess.get("entitlement") if isinstance(sess.get("entitlement"), dict) else {}
    sess.pop("token", None)
    sess.pop("refresh_token", None)
    if ent:
        ent["valid"] = False
        ent["message"] = message
        sess["entitlement"] = ent
    else:
        sess["entitlement"] = {"valid": False, "message": message, "cached_at": time.time()}
    save_session(sess)


async def _jane_http_once(
    base: str,
    method: str,
    path: str,
    *,
    json_body: Any = None,
    params: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: float = 30.0,
    scope: str | None = None,
) -> Any:
    _assert_commercial_https(base)
    url = f"{base.rstrip('/')}{path if path.startswith('/') else '/' + path}"
    headers = {"Accept": "application/json", **_auth_header(token)}
    try:
        headers["X-Device-Fingerprint"] = device_fingerprint()
    except Exception:
        pass
    request_body = json_body
    response_key: bytes | None = None
    request_envelope: dict[str, Any] | None = None
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        if scope:
            key_response = await client.get(
                f"{base.rstrip('/')}/crypto/public-key",
                headers={"Accept": "application/json"},
            )
            key_response.raise_for_status()
            request_envelope, response_key = create_envelope(key_response.json(), scope, json_body or {})
            request_body = request_envelope
        resp = await client.request(method.upper(), url, json=request_body, params=params, headers=headers)
    try:
        body = resp.json()
    except Exception:
        body = {"message": resp.text[:500]}
    if scope:
        try:
            body = decrypt_response(body, request_envelope or {}, response_key or b"")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"授权服务加密响应校验失败: {exc}") from exc
    if resp.status_code >= 400:
        msg = body.get("message") if isinstance(body, dict) else str(body)
        raise HTTPException(status_code=resp.status_code, detail=msg or f"HTTP {resp.status_code}")
    if isinstance(body, dict) and body.get("code") not in (None, 200, "200"):
        raise HTTPException(status_code=400, detail=str(body.get("message") or "业务错误"))
    return _unwrap(body)


async def try_refresh_session_token() -> bool:
    """POST /user/refreshToken once; updates session token on success."""
    sess = load_session()
    refresh = (sess.get("refresh_token") or "").strip()
    access = (sess.get("token") or "").strip()
    if not refresh:
        return False
    body = {"token": access, "refreshToken": refresh}
    for base in jane_bases():
        try:
            data = await _jane_http_once(
                base,
                "POST",
                "/user/refreshToken",
                json_body=body,
                token=None,
                timeout=15.0,
                scope=SENSITIVE_SCOPES["user.refreshToken"],
            )
            if isinstance(data, dict) and data.get("token"):
                sess = load_session()
                sess["token"] = data.get("token")
                new_rt = data.get("refreshToken") or data.get("refresh_token")
                if new_rt:
                    sess["refresh_token"] = new_rt
                if data.get("userId") or data.get("user_id"):
                    sess["user_id"] = data.get("userId") or data.get("user_id")
                if data.get("username"):
                    sess["username"] = data.get("username")
                save_session(sess)
                return True
        except HTTPException as e:
            if _is_retryable_http(e.status_code):
                continue
            return False
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError, httpx.ReadError):
            continue
        except Exception:
            return False
    return False


async def jane_request(
    method: str,
    path: str,
    *,
    json_body: Any = None,
    params: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: float = 30.0,
    allow_refresh: bool = True,
    scope: str | None = None,
) -> Any:
    bases = jane_bases()
    if not bases:
        raise HTTPException(status_code=503, detail="未配置 license_api_base，无法连接授权服务")

    last_exc: HTTPException | None = None
    auth_retried = False

    for base in bases:
        try:
            return await _jane_http_once(
                base,
                method,
                path,
                json_body=json_body,
                params=params,
                token=token,
                timeout=timeout,
                scope=scope,
            )
        except HTTPException as e:
            if _is_auth_failure(e.status_code):
                if (
                    allow_refresh
                    and not auth_retried
                    and path not in ("/user/refreshToken", "/user/login", "/user/register")
                ):
                    auth_retried = True
                    if await try_refresh_session_token():
                        return await jane_request(
                            method,
                            path,
                            json_body=json_body,
                            params=params,
                            token=token,
                            timeout=timeout,
                            allow_refresh=False,
                            scope=scope,
                        )
                invalidate_auth_session("登录已过期，请重新登录")
                raise HTTPException(status_code=e.status_code, detail="登录已过期，请重新登录")
            if 400 <= e.status_code < 500:
                raise
            last_exc = e
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError, httpx.ReadError, httpx.RemoteProtocolError) as e:
            last_exc = HTTPException(status_code=503, detail=str(e) or "网络错误")
        except Exception as e:
            # httpx 其它传输层错误也换线路重试，避免只显示 “Server disconnected…”
            name = type(e).__name__
            if "Protocol" in name or "Timeout" in name or "Connect" in name or "Network" in name or "Read" in name:
                last_exc = HTTPException(status_code=503, detail=str(e) or "网络错误")
            else:
                last_exc = HTTPException(status_code=503, detail=str(e) or "授权服务不可用")

    if last_exc:
        raise last_exc
    raise HTTPException(status_code=503, detail="授权服务不可用")


def _pending_usage_tokens(sess: dict[str, Any]) -> int:
    items: list[Any] = []
    for key in ("pending_usage", "pending_usage_batches"):
        value = sess.get(key)
        if isinstance(value, list):
            items.extend(value)
    current = sess.get("pending_usage_current")
    if isinstance(current, dict):
        items.extend(current.values())
    return sum(
        max(0, int(item.get("tokens") or 0))
        for item in items
        if isinstance(item, dict)
    )


def cache_entitlement(status: dict[str, Any]) -> None:
    # Serialize this read-modify-write with the usage writer. Otherwise a
    # remote status refresh can overwrite a batch queued by the writer thread.
    should_kick = False
    with _usage_batch_lock:
        sess = load_session()
        remote_used = status.get("tokenUsed") if status.get("tokenUsed") is not None else status.get("token_used")
        token_used = int(remote_used or 0) + _pending_usage_tokens(sess)
        token_quota = status.get("tokenQuota") if status.get("tokenQuota") is not None else status.get("token_quota")
        remote_remaining = (
            status.get("tokenRemaining")
            if status.get("tokenRemaining") is not None
            else status.get("token_remaining")
        )
        token_remaining = remote_remaining
        if int(token_quota or 0) > 0:
            local_remaining = max(0, int(token_quota) - token_used)
            token_remaining = min(int(remote_remaining), local_remaining) if remote_remaining is not None else local_remaining
        frozen = bool(status.get("frozen"))
        message = status.get("message")
        if frozen and not message:
            message = (
                status.get("frozenReason")
                or status.get("frozen_reason")
                or "账号权益已冻结，请重新登录"
            )
        # 未兑卡也是 valid=false，不能清登录；仅冻结/禁用才踢会话
        msg_l = str(message or "").lower()
        revoked = frozen or ("冻结" in str(message or "")) or ("禁用" in str(message or "")) or (
            "revok" in msg_l
        )
        valid = (
            bool(status.get("valid"))
            and not revoked
            and not (int(token_quota or 0) > 0 and token_used >= int(token_quota))
        )
        sess["entitlement"] = {
            "valid": valid,
            "expire_at": status.get("expireAt") or status.get("expire_at"),
            "token_quota": token_quota,
            "token_used": token_used,
            "token_remaining": token_remaining,
            "token_unlimited": bool(status.get("tokenUnlimited") if status.get("tokenUnlimited") is not None else status.get("token_unlimited")),
            "time_unlimited": bool(status.get("timeUnlimited") if status.get("timeUnlimited") is not None else status.get("time_unlimited")),
            "plan_label": status.get("planLabel") or status.get("plan_label"),
            "message": message,
            "user_id": status.get("userId") or status.get("user_id"),
            "username": status.get("username"),
            "project_id": status.get("projectId") or status.get("project_id"),
            "frozen": frozen,
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
        should_kick = revoked
    if should_kick:
        invalidate_auth_session(
            str(
                status.get("message")
                or status.get("frozenReason")
                or status.get("frozen_reason")
                or "权益已冻结，请重新登录"
            )
        )


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
        "pending_usage_count": (
            (len(sess.get("pending_usage") or []) if isinstance(sess.get("pending_usage"), list) else 0)
            + (len(sess.get("pending_usage_batches") or []) if isinstance(sess.get("pending_usage_batches"), list) else 0)
            + (len(sess.get("pending_usage_current") or {}) if isinstance(sess.get("pending_usage_current"), dict) else 0)
        ),
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
        data = await jane_request(
            "POST",
            "/gateway/license/status",
            timeout=8.0,
            scope=SENSITIVE_SCOPES["gateway-license.status"],
        )
        if isinstance(data, dict):
            cache_entitlement(data)
            _refresh_ts = time.time()
    except HTTPException as e:
        if _is_auth_failure(e.status_code):
            # invalidate_auth_session already ran inside jane_request
            pass
        elif _is_retryable_http(e.status_code) or e.status_code == 503:
            # Network / 5xx: keep cached entitlement for offline grace
            pass
    except Exception:
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


def _queue_usage_batch(tokens: int, *, estimated: bool = False) -> None:
    """Persist at most one current batch per usage kind.

    Detailed request logs remain local; the license service receives one
    idempotent delta per flush interval instead of one write per request.
    """
    if tokens <= 0:
        return
    with _usage_batch_lock:
        sess = load_session()
        current = sess.get("pending_usage_current")
        if not isinstance(current, dict):
            current = {}
        key = "estimated" if estimated else "exact"
        batch = current.get(key)
        if not isinstance(batch, dict):
            batch = {
                "requestId": f"batch-{uuid.uuid4()}",
                "tokens": 0,
                "count": 0,
                "ts": time.time(),
                "estimated": bool(estimated),
            }
        batch["tokens"] = int(batch.get("tokens") or 0) + int(tokens)
        batch["count"] = int(batch.get("count") or 0) + 1
        batch["lastTs"] = time.time()
        current[key] = batch
        sess["pending_usage_current"] = current
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
        sess["pending_usage_last_error"] = "用量已在本地聚合，将定时批量上报"
        save_session(sess)


async def report_usage(tokens: int, request_id: str | None = None, *, estimated: bool = False) -> None:
    if tokens <= 0 or not license_required():
        return
    cfg = load_config()
    if estimated and not bill_estimated_usage(cfg):
        return
    if not load_session().get("token"):
        return
    _queue_usage_batch(int(tokens), estimated=estimated)


async def flush_pending_usage() -> None:
    with _usage_batch_lock:
        sess = load_session()
        if not sess.get("token"):
            return
        pending = list(sess.get("pending_usage") or []) if isinstance(sess.get("pending_usage"), list) else []
        pending.extend(sess.get("pending_usage_batches") or [] if isinstance(sess.get("pending_usage_batches"), list) else [])
        current = sess.get("pending_usage_current") if isinstance(sess.get("pending_usage_current"), dict) else {}
        pending.extend(item for item in current.values() if isinstance(item, dict))
        if not pending:
            return
        # Detach before network I/O so new requests form a fresh batch.
        sess["pending_usage"] = []
        sess["pending_usage_batches"] = []
        sess["pending_usage_current"] = {}
        save_session(sess)
    if not pending:
        return
    left = []
    latest_status: dict[str, Any] | None = None
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
                scope=SENSITIVE_SCOPES["gateway-license.usage"],
            )
            if isinstance(data, dict):
                latest_status = data
        except Exception:
            left.append(item)
    with _usage_batch_lock:
        sess = load_session()
        queued = sess.get("pending_usage_batches") if isinstance(sess.get("pending_usage_batches"), list) else []
        # Never discard unacknowledged usage. requestId makes retries idempotent.
        sess["pending_usage_batches"] = queued + left
        if left:
            sess["pending_usage_last_error"] = f"仍有 {len(left)} 个用量批次未上报，将在下次联网重试"
        elif not sess.get("pending_usage_current"):
            sess.pop("pending_usage_last_error", None)
        save_session(sess)
    if latest_status is not None:
        # Requeued failures and newly queued requests must remain reflected in
        # the local balance after applying the server's acknowledged total.
        cache_entitlement(latest_status)


def schedule_usage_from_row(row: dict[str, Any]) -> None:
    if (
        not row.get("ok")
        or str(row.get("client_model") or "").strip().lower() == "probe"
        or not license_required()
    ):
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
        _queue_usage_batch(tt, estimated=estimated)
