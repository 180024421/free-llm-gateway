"""License gate: session cache + remote entitlement against run-jane."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import HTTPException

from .config import DATA_DIR, load_config, save_json, load_json

SESSION_PATH = DATA_DIR / "session.json"
_HMAC_SALT = b"dashuai-gateway-license-v1"
_refresh_ts = 0.0
_REFRESH_INTERVAL = 300.0


def session_path() -> Path:
    """Always resolve against current DATA_DIR (EXE may set it after import)."""
    from . import config as cfg_mod

    return Path(cfg_mod.DATA_DIR) / "session.json"


def license_required(cfg: dict[str, Any] | None = None) -> bool:
    cfg = cfg or load_config()
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
    key = _HMAC_SALT + device_fingerprint().encode("utf-8")
    return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()


def load_session() -> dict[str, Any]:
    data = load_json(session_path(), {})
    if not isinstance(data, dict):
        return {}
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
    ent = data.get("entitlement")
    if isinstance(ent, dict):
        clean = {k: v for k, v in ent.items() if k != "_sig"}
        clean["device"] = device_fingerprint()
        clean["_sig"] = _sign_payload(clean)
        data["entitlement"] = clean
    save_json(session_path(), data)


def clear_session() -> None:
    path = session_path()
    if path.exists():
        path.unlink()


def jane_base(cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load_config()
    return (cfg.get("license_api_base") or "").strip().rstrip("/")


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
    url = f"{base}{path if path.startswith('/') else '/' + path}"
    headers = {"Accept": "application/json", **_auth_header(token)}
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
        "cached_at": time.time(),
    }
    if status.get("username"):
        sess["username"] = status.get("username")
    if status.get("userId") or status.get("user_id"):
        sess["user_id"] = status.get("userId") or status.get("user_id")
    save_session(sess)


def entitlement_snapshot() -> dict[str, Any]:
    sess = load_session()
    ent = sess.get("entitlement") if isinstance(sess.get("entitlement"), dict) else {}
    return {
        "logged_in": bool(sess.get("token")),
        "username": sess.get("username"),
        "user_id": sess.get("user_id"),
        "valid": bool(ent.get("valid")),
        "expire_at": ent.get("expire_at"),
        "token_quota": ent.get("token_quota"),
        "token_used": ent.get("token_used"),
        "token_remaining": ent.get("token_remaining"),
        "token_unlimited": bool(ent.get("token_unlimited")),
        "time_unlimited": bool(ent.get("time_unlimited")),
        "plan_label": ent.get("plan_label"),
        "message": ent.get("message") or ("未登录" if not sess.get("token") else "未激活"),
        "project_id": ent.get("project_id") or load_config().get("license_project_id"),
        "require_license": license_required(),
        "cached_at": ent.get("cached_at"),
        "pending_usage_count": len(sess.get("pending_usage") or []) if isinstance(sess.get("pending_usage"), list) else 0,
        "pending_usage_last_error": sess.get("pending_usage_last_error"),
    }


def _local_still_valid(ent: dict[str, Any], max_age: float = _REFRESH_INTERVAL) -> bool:
    if not ent.get("valid"):
        return False
    cached_at = float(ent.get("cached_at") or 0)
    if time.time() - cached_at > max_age:
        return False
    expire_at = ent.get("expire_at")
    if expire_at:
        # accept ISO-like or "yyyy-MM-dd HH:mm:ss"
        try:
            from datetime import datetime

            s = str(expire_at).replace("T", " ")[:19]
            if datetime.strptime(s, "%Y-%m-%d %H:%M:%S").timestamp() < time.time():
                return False
        except Exception:
            pass
    quota = int(ent.get("token_quota") or 0)
    used = int(ent.get("token_used") or 0)
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
        data = await jane_request("GET", "/gateway/license/status")
        if isinstance(data, dict):
            cache_entitlement(data)
            _refresh_ts = time.time()
    except HTTPException:
        # keep cache for short offline grace
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
    # UI / 离线宽限：本地仍有效则直接放行；过期后再强制刷新
    if _local_still_valid(ent, max_age=86400.0):
        return ent
    snap = await refresh_status(force=True)
    if snap.get("valid"):
        return snap
    # 远端失败时，若本地缓存曾有效且未明显过期，再给短宽限
    if ent.get("valid") and _local_still_valid(ent, max_age=86400.0 * 3):
        return ent
    raise HTTPException(
        status_code=402,
        detail={
            "message": snap.get("message") or "权益无效，请购买或续费",
            "code": "LICENSE_INVALID",
            "license": snap,
        },
    )


async def report_usage(tokens: int, request_id: str | None = None) -> None:
    if tokens <= 0 or not license_required():
        return
    sess = load_session()
    if not sess.get("token"):
        return
    rid = (request_id or str(uuid.uuid4())).strip()
    try:
        data = await jane_request(
            "POST",
            "/gateway/license/usage",
            json_body={"requestId": rid, "tokens": int(tokens)},
        )
        if isinstance(data, dict):
            cache_entitlement(data)
            # bump local used optimistically already in cache
    except Exception:
        # queue locally for retry
        pending = sess.get("pending_usage") if isinstance(sess.get("pending_usage"), list) else []
        pending.append({"requestId": rid, "tokens": int(tokens), "ts": time.time()})
        sess["pending_usage"] = pending[-50:]
        # also bump local used so gate trips sooner offline
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
        save_session(sess)


async def flush_pending_usage() -> None:
    sess = load_session()
    pending = sess.get("pending_usage") if isinstance(sess.get("pending_usage"), list) else []
    if not pending or not sess.get("token"):
        return
    left = []
    for item in pending:
        try:
            data = await jane_request(
                "POST",
                "/gateway/license/usage",
                json_body={"requestId": item.get("requestId"), "tokens": item.get("tokens") or 0},
            )
            if isinstance(data, dict):
                cache_entitlement(data)
        except Exception:
            left.append(item)
    sess = load_session()
    sess["pending_usage"] = left
    if left:
        sess["pending_usage_last_error"] = "部分用量尚未上报到服务器，将在下次联网时重试"
    else:
        sess.pop("pending_usage_last_error", None)
    save_session(sess)


def schedule_usage_from_row(row: dict[str, Any]) -> None:
    if not row.get("ok") or not license_required():
        return
    usage = row.get("usage") if isinstance(row.get("usage"), dict) else {}
    pt = int(usage.get("prompt_tokens") or row.get("pt") or 0)
    ct = int(usage.get("completion_tokens") or row.get("ct") or 0)
    tt = int(usage.get("total_tokens") or row.get("tt") or (pt + ct))
    if tt <= 0:
        return
    rid = str(row.get("request_id") or uuid.uuid4())
    try:
        import asyncio

        loop = asyncio.get_running_loop()
        loop.create_task(report_usage(tt, rid))
    except RuntimeError:
        sess = load_session()
        pending = sess.get("pending_usage") if isinstance(sess.get("pending_usage"), list) else []
        pending.append({"requestId": rid, "tokens": tt, "ts": time.time()})
        sess["pending_usage"] = pending[-50:]
        save_session(sess)
