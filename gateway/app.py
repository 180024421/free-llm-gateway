from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __product__, __product_en__, __version__

DEFAULT_DISCLAIMER = (
    "本软件提供个人授权使用（非开源）。个人授权仅限本人；商用授权须另行取得书面许可。"
    "禁止反编译、破解、篡改、二次分发源码或改包再分发。使用即表示同意上述条款。"
)
from .config import (
    load_config,
    load_providers,
    load_routers,
    mask_secret,
    overview_payload,
    reload_all,
    save_config,
    save_providers,
    save_routers,
)
from .poller import check_all, get_poll_status, latest_health, load_latest_history
from .route_builder import rebuild_and_save
from .proxy import (
    aclose_http_client,
    call_log,
    forward_chat,
    is_coding_route,
    is_complex_route,
    is_daily_route,
    is_fast_route,
    is_novel_route,
    is_snappy_route,
    prepare_body_for_upstream,
    probe_provider,
    remount_route_for_tools,
    usage_csv,
    usage_for_ui,
    usage_summary,
)
from .router import list_upstream_models, resolve_candidates
from .channel_store import apply_to_state
from .chat_dispatch import race_first_success
from .concurrency import provider_limit_from_config, provider_slot
from .state import STATE
from .ops import (
    autostart_status,
    archive_usage_now,
    backup_config_zip,
    bootstrap_for_ui,
    classify_error,
    clear_usage_now,
    enrich_error_entry,
    is_loopback_host,
    list_backups,
    list_usage_archives,
    recent_failures,
    remediation_hint,
    restore_config_zip,
    set_autostart,
)
from .workbuddy import diagnose_workbuddy, sync_workbuddy, workbuddy_status
from .license import (
    cache_entitlement,
    clear_session,
    entitlement_snapshot,
    flush_pending_usage,
    jane_request,
    license_required,
    load_session,
    refresh_status,
    release_quota,
    require_entitlement,
    reserve_quota,
    save_session,
)


def _ascii_header(value: Any) -> str:
    """Starlette encodes response headers as latin-1; quote Chinese names (e.g. 魔搭)."""
    s = str(value or "")
    try:
        s.encode("latin-1")
        return s
    except UnicodeEncodeError:
        from urllib.parse import quote

        return quote(s, safe="._-/:+=@")


def _assistant_text(raw: Any) -> str:
    if not isinstance(raw, dict):
        return ""
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    msg = first.get("message") if isinstance(first.get("message"), dict) else {}
    for key in ("content", "reasoning_content", "reasoning"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    delta = first.get("delta") if isinstance(first.get("delta"), dict) else {}
    for key in ("content", "reasoning_content", "reasoning"):
        val = delta.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _usable_chat_payload(raw: Any) -> bool:
    return bool(_assistant_text(raw))


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        from .commercial import enforce_commercial_config, unify_local_api_key

        enforce_commercial_config()
        unify_local_api_key()
    except Exception:
        pass
    try:
        apply_to_state(STATE)
    except Exception:
        pass
    # Push current routes into WorkBuddy on every gateway start.
    try:
        sync_workbuddy(auto=True)
    except Exception:
        pass

    async def _license_warmup() -> None:
        try:
            await flush_pending_usage()
            if license_required():
                await refresh_status(force=True)
        except Exception:
            pass

    async def _license_refresh_loop() -> None:
        import asyncio

        while True:
            await asyncio.sleep(180)
            try:
                if license_required():
                    await flush_pending_usage()
                    await refresh_status(force=True)
            except Exception:
                pass

    async def _health_probe_loop() -> None:
        import asyncio

        while True:
            cfg = load_config()
            interval = int(cfg.get("health_probe_interval_sec") or 0)
            if interval <= 0:
                await asyncio.sleep(120)
                continue
            await asyncio.sleep(max(30, interval))
            try:
                await check_all(quiet=True)
            except Exception:
                pass
            try:
                rebuild_and_save()
            except Exception:
                pass

    # Do not block server ready / desktop window on remote license calls
    try:
        import asyncio

        from .usage_queue import start_usage_writer

        start_usage_writer()
        asyncio.create_task(_license_warmup())
        asyncio.create_task(_license_refresh_loop())
        asyncio.create_task(_health_probe_loop())
    except Exception:
        pass
    yield
    try:
        from .usage_queue import stop_usage_writer

        stop_usage_writer(flush=True)
    except Exception:
        pass
    await aclose_http_client()


app = FastAPI(title=__product__, version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8010",
        "http://localhost:8010",
        "http://127.0.0.1:8011",
        "http://localhost:8011",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def require_localhost_for_ops(request: Request, call_next):
    """Sensitive stats/ops endpoints are loopback-only."""
    p = request.url.path or ""
    guarded = (
        p.startswith("/api/usage")
        or p.startswith("/api/call-log")
        or p.startswith("/api/bootstrap")
        or p.startswith("/api/health-board")
        or p.startswith("/api/ops/")
        or p.startswith("/api/integrations/workbuddy/diagnose")
    )
    if guarded:
        host = request.client.host if request.client else ""
        # Starlette TestClient reports host as "testclient"
        if host not in ("testclient", "testserver") and not is_loopback_host(host):
            return JSONResponse({"detail": "localhost only"}, status_code=403)
    return await call_next(request)


_MAINT_CACHE: dict[str, Any] = {"ts": 0.0, "enabled": False, "message": ""}


async def ensure_not_maintenance() -> None:
    cfg = load_config()
    if not license_required(cfg):
        return
    now = time.time()
    if now - float(_MAINT_CACHE.get("ts") or 0) < 300:
        if _MAINT_CACHE.get("enabled"):
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "MAINTENANCE",
                    "message": str(_MAINT_CACHE.get("message") or "系统维护中，请稍后再试"),
                },
            )
        return
    enabled = False
    message = ""
    if (cfg.get("license_api_base") or "").strip():
        try:
            data = await jane_request("GET", "/gateway/meta/bootstrap", timeout=6.0)
            if isinstance(data, dict):
                enabled = bool(data.get("maintenanceEnabled") or data.get("maintenance_enabled"))
                message = str(data.get("maintenanceMessage") or data.get("maintenance_message") or "")
        except Exception:
            pass
    _MAINT_CACHE.update(ts=now, enabled=enabled, message=message)
    if enabled:
        raise HTTPException(
            status_code=503,
            detail={"code": "MAINTENANCE", "message": message or "系统维护中，请稍后再试"},
        )


def _auth(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    api_key: Optional[str] = Header(default=None, alias="api-key"),
) -> None:
    cfg = load_config()
    expected = (cfg.get("local_api_key") or "").strip()
    if not expected:
        return

    candidates: list[str] = []
    if authorization:
        auth = authorization.strip()
        low = auth.lower()
        if low.startswith("bearer "):
            candidates.append(auth[7:].strip())
        else:
            # Some clients send raw key in Authorization
            candidates.append(auth)
    if x_api_key:
        candidates.append(x_api_key.strip())
    if api_key:
        candidates.append(api_key.strip())

    for token in candidates:
        # tolerate accidental quotes / Bearer prefix in the key field itself
        t = token.strip().strip('"').strip("'")
        if t.lower().startswith("bearer "):
            t = t[7:].strip()
        if t == expected:
            return

    raise HTTPException(
        status_code=401,
        detail={
            "code": "LOCAL_KEY_MISMATCH",
            "message": "本地 API Key 不正确",
            "hint": "客户端的 apiKey 必须与网关一致。请在面板点「同步到本机客户端」（会自动写入 WorkBuddy / Cursor，一般不用改设置）。",
        },
    )


def _public_base(request: Request) -> str:
    cfg = load_config()
    host = cfg.get("host") or "127.0.0.1"
    if host in ("0.0.0.0", "::"):
        host = request.url.hostname or "127.0.0.1"
    port = int(cfg.get("port") or 8010)
    scheme = request.url.scheme or "http"
    return f"{scheme}://{host}:{port}"


@app.get("/")
def root(request: Request):
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept:
        return RedirectResponse(url="/ui/", status_code=307)
    base = _public_base(request)
    return {
        "name": "dashuai-gateway",
        "product": __product__,
        "product_en": __product_en__,
        "version": __version__,
        "openai_base": f"{base}/v1",
        "ui": f"{base}/ui/",
        "health": f"{base}/health",
        "license": entitlement_snapshot() if license_required() else "none - require_license off",
    }


@app.get("/health")
def health(request: Request) -> dict[str, Any]:
    data = overview_payload(_public_base(request))
    data["version"] = __version__
    data["channels"] = STATE.snapshot()
    data["usage"] = usage_summary(200)
    data["health"] = latest_health() or load_latest_history()
    data["poll_status"] = get_poll_status()
    return data


@app.get("/api/overview")
def api_overview(request: Request) -> dict[str, Any]:
    data = overview_payload(_public_base(request))
    data["version"] = __version__
    data["channels"] = STATE.snapshot()
    data["usage"] = usage_summary(300)
    data["health"] = latest_health() or load_latest_history()
    data["poll_status"] = get_poll_status()
    data["license"] = entitlement_snapshot()
    data["recent_failures"] = recent_failures(5)
    return data


@app.get("/api/usage")
def api_usage(days: int = 1) -> dict[str, Any]:
    """Local usage aggregate (no auth — read-only stats for UI). ?days=1|7|30"""
    d = max(1, min(90, int(days or 1)))
    return usage_for_ui(d)


@app.get("/api/call-log")
def api_call_log(limit: int = 100, route: str | None = None) -> list[dict[str, Any]]:
    """Recent calls (localhost-only). Optional ?route= filter."""
    return call_log(max(1, min(500, int(limit or 100))), route=route)


@app.get("/api/usage.csv")
def api_usage_csv(days: int = 7):
    from fastapi.responses import PlainTextResponse

    d = max(1, min(90, int(days or 7)))
    return PlainTextResponse(
        usage_csv(d),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="usage-{d}d.csv"'},
    )


@app.get("/api/bootstrap")
def api_bootstrap() -> dict[str, Any]:
    return bootstrap_for_ui()


@app.get("/api/health-board")
def api_health_board() -> dict[str, Any]:
    channels = STATE.snapshot()
    cooling = [c for c in channels if c.get("circuit_open")]
    fails = recent_failures(20)
    return {
        "channels": channels,
        "cooling": cooling,
        "cooling_count": len(cooling),
        "recent_failures": fails,
        # aliases used by UI enhance layer
        "cooling_models": cooling,
        "recent_fails": fails,
    }


@app.get("/api/ops/autostart")
def api_autostart_get() -> dict[str, Any]:
    return autostart_status()


@app.post("/api/ops/autostart")
async def api_autostart_set(request: Request) -> dict[str, Any]:
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    return set_autostart(bool((body or {}).get("enabled")))


@app.get("/api/ops/backups")
def api_backups_list() -> dict[str, Any]:
    return {"items": list_backups()}


@app.get("/api/ops/usage/archives")
def api_usage_archives_list() -> dict[str, Any]:
    return {"items": list_usage_archives()}


@app.post("/api/ops/usage/archive")
def api_usage_archive(_: None = Depends(_auth)) -> dict[str, Any]:
    return archive_usage_now()


@app.post("/api/ops/usage/clear")
def api_usage_clear(_: None = Depends(_auth)) -> dict[str, Any]:
    return clear_usage_now()


@app.post("/api/license/flush-usage")
async def api_license_flush_usage(_: None = Depends(_auth)) -> dict[str, Any]:
    await flush_pending_usage()
    snap = entitlement_snapshot()
    return {
        "ok": True,
        "pending_usage_count": snap.get("pending_usage_count") or 0,
        "message": snap.get("pending_usage_last_error") or "已尝试上报待同步用量",
    }


@app.get("/api/update/check")
async def api_update_check() -> dict[str, Any]:
    from .versioning import is_newer

    local = __version__
    latest = local
    download_url = ""
    download_sha256 = ""
    changelog = ""
    force_update = False
    maintenance = False
    # Prefer dedicated app-update catalog; fall back to bootstrap meta.
    try:
        data = await jane_request("GET", "/app-update/dashuai-gateway", timeout=8.0)
        if isinstance(data, dict):
            latest = str(data.get("versionName") or data.get("version_name") or latest)
            download_url = str(data.get("desktopUrl") or data.get("desktop_url") or "")
            download_sha256 = str(data.get("downloadSha256") or data.get("download_sha256") or "")
            changelog = str(data.get("changelog") or "")
            force_update = bool(data.get("forceUpdate") or data.get("force_update"))
    except Exception:
        meta = await api_remote_bootstrap()
        latest = str(meta.get("latestVersion") or local)
        download_url = str(meta.get("downloadUrl") or "")
        download_sha256 = str(meta.get("downloadSha256") or "")
        changelog = str(meta.get("changelog") or "")
        force_update = bool(meta.get("forceUpdate") or meta.get("force_update"))
        maintenance = bool(meta.get("maintenanceEnabled"))
    else:
        try:
            meta = await api_remote_bootstrap()
            maintenance = bool(meta.get("maintenanceEnabled"))
            if not download_url:
                download_url = str(meta.get("downloadUrl") or "")
            if not download_sha256:
                download_sha256 = str(meta.get("downloadSha256") or "")
            if not changelog:
                changelog = str(meta.get("changelog") or "")
            if not force_update:
                force_update = bool(meta.get("forceUpdate") or meta.get("force_update"))
        except Exception:
            pass
    return {
        "local_version": local,
        "latest_version": latest,
        "update_available": is_newer(latest, local),
        "download_url": download_url,
        "download_sha256": download_sha256,
        "changelog": changelog,
        "force_update": force_update,
        "maintenance": maintenance,
    }


@app.post("/api/ops/backup")
def api_backup_create(_: None = Depends(_auth)) -> dict[str, Any]:
    p = backup_config_zip()
    return {"ok": True, "path": str(p), "name": p.name}


@app.post("/api/ops/restore")
async def api_backup_restore(request: Request, _: None = Depends(_auth)) -> dict[str, Any]:
    body = await request.json()
    name = str((body or {}).get("name") or "").strip()
    if not name or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="invalid backup name")
    from .config import DATA_DIR

    return restore_config_zip(DATA_DIR / "backups" / name)


@app.get("/api/integrations/workbuddy/diagnose")
def api_workbuddy_diagnose() -> dict[str, Any]:
    return diagnose_workbuddy()




@app.get("/api/poll-status")
def api_poll_status(_: None = Depends(_auth)) -> dict[str, Any]:
    return get_poll_status()


@app.post("/api/check/all")
async def api_check_all(_: None = Depends(_auth)) -> dict[str, Any]:
    """One-click probe all enabled models (commercial「立即检测」)."""
    return await check_all(concurrency=4)


@app.post("/api/probe")
async def api_probe(request: Request, _: None = Depends(_auth)) -> dict[str, Any]:
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    if not isinstance(body, dict):
        body = {}
    if body.get("all"):
        return await check_all(concurrency=4)
    name = body.get("name")
    model = body.get("model")
    providers = load_providers()
    target = None
    if name:
        for p in providers:
            if p.get("name") == name:
                target = p
                break
    elif providers:
        target = next(
            (
                p
                for p in providers
                if (p.get("api_key") or "").strip() and not str(p.get("api_key")).startswith("REPLACE_")
            ),
            None,
        )
    if not target:
        raise HTTPException(status_code=404, detail="provider not found or not configured")
    cfg = load_config()
    timeout = float(cfg.get("request_timeout_sec") or 120)
    return await probe_provider(target, timeout_sec=min(60.0, timeout), model=model)


@app.post("/admin/reload")
def admin_reload(_: None = Depends(_auth)) -> dict[str, str]:
    reload_all()
    return {"status": "reloaded"}


@app.get("/api/config")
def get_config(_: None = Depends(_auth)) -> dict[str, Any]:
    return load_config()


@app.put("/api/config")
async def put_config(request: Request, _: None = Depends(_auth)) -> dict[str, Any]:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    cfg = load_config()
    for key in (
        "host",
        "port",
        "local_api_key",
        "request_timeout_sec",
        "max_retries_per_request",
        "health_probe_interval_sec",
        "stream_stall_sec",
        "tool_request_timeout_sec",
        "tool_stream_stall_sec",
        "fast_stream_stall_sec",
        "fast_tool_stream_stall_sec",
        "fast_tool_request_timeout_sec",
        "fast_request_timeout_sec",
        "fast_max_retries",
        "daily_stream_stall_sec",
        "daily_request_timeout_sec",
        "complex_stream_stall_sec",
        "complex_tool_stream_stall_sec",
        "complex_request_timeout_sec",
        "complex_tool_request_timeout_sec",
        "complex_max_retries",
        "novel_stream_stall_sec",
        "novel_request_timeout_sec",
        "code_stream_stall_sec",
        "code_tool_stream_stall_sec",
        "code_request_timeout_sec",
        "code_tool_request_timeout_sec",
        "code_max_retries",
        "novel_max_retries",
        "novel_fallback_daily",
        "novel_preferred_provider",
        "novel_stream_mode",
        "encrypt_provider_keys",
        "encrypt_session",
        "workbuddy_enable_agent_teams",
        "fast_hedged_requests",
        "fast_hedge_candidates",
        "fast_hedge_with_tools",
        "provider_max_concurrent",
        "provider_concurrency_limit",
        "usage_async_write",
        "license_online_cache_sec",
        "license_offline_grace_sec",
        "license_reserve_tokens",
        "bill_estimated_usage",
        "license_allow_insecure_http",
    ):
        if key in body:
            cfg[key] = body[key]
    # Commercial builds refuse to turn off license via API.
    try:
        from .commercial import is_commercial_build

        if is_commercial_build(cfg):
            cfg["require_license"] = True
            cfg["commercial_mode"] = True
    except Exception:
        pass
    save_config(cfg)
    return {"status": "saved", "config": cfg}


@app.get("/api/providers")
def get_providers(_: None = Depends(_auth)) -> list[dict[str, Any]]:
    return load_providers()


@app.put("/api/providers")
async def put_providers(request: Request, _: None = Depends(_auth)) -> dict[str, Any]:
    body = await request.json()
    if not isinstance(body, list):
        raise HTTPException(status_code=400, detail="JSON array required")
    cleaned: list[dict[str, Any]] = []
    for item in body:
        if not isinstance(item, dict):
            continue
        cleaned.append(
            {
                "name": item.get("name") or "unnamed",
                "base_url": item.get("base_url") or "",
                "api_key": item.get("api_key") or "",
                "models": item.get("models") or [],
                "disabled_models": item.get("disabled_models") or [],
                "free_only": bool(item.get("free_only", False)),
                "weight": item.get("weight", 1),
                "enabled": bool(item.get("enabled", True)),
            }
        )
    save_providers(cleaned)
    try:
        rebuild_and_save()
    except Exception:
        pass
    return {"status": "saved", "count": len(cleaned), "routes_rebuilt": True}


@app.get("/api/routers")
def get_routers(_: None = Depends(_auth)) -> dict[str, Any]:
    return load_routers()


@app.put("/api/routers")
async def put_routers(request: Request, _: None = Depends(_auth)) -> dict[str, Any]:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    save_routers(body)
    return {"status": "saved", "routes": list(body.keys())}


@app.post("/api/routers/rebuild-smart")
def post_rebuild_smart_routers(_: None = Depends(_auth)) -> dict[str, Any]:
    """Rebuild all use-case routes from usage.jsonl success rates (top 10 each)."""
    return rebuild_and_save()


@app.get("/api/integrations/workbuddy")
def get_workbuddy_integration(_: None = Depends(_auth)) -> dict[str, Any]:
    return workbuddy_status()


@app.post("/api/integrations/workbuddy")
async def post_workbuddy_integration(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    api_key: Optional[str] = Header(default=None, alias="api-key"),
) -> dict[str, Any]:
    host = request.client.host if request.client else ""
    # Desktop UI runs on loopback — allow sync even when browser cached an old local key.
    if host not in ("testclient", "testserver") and not is_loopback_host(host):
        _auth(
            authorization=authorization,
            x_api_key=x_api_key,
            api_key=api_key,
        )
    api_key_updated = False
    try:
        body = await request.json()
    except Exception:
        body = {}
    if isinstance(body, dict):
        incoming_key = str(body.get("local_api_key") or "").strip()
        if incoming_key:
            cfg = load_config()
            if cfg.get("local_api_key") != incoming_key:
                cfg["local_api_key"] = incoming_key
                save_config(cfg)
                api_key_updated = True
    try:
        rebuild_and_save()
    except Exception:
        pass
    out = sync_workbuddy()
    synced_key = str(load_config().get("local_api_key") or "").strip()
    out["api_key_updated"] = api_key_updated
    out["api_key_masked"] = mask_secret(synced_key)
    out["diagnose"] = diagnose_workbuddy()
    return out


def _models_payload() -> dict[str, Any]:
    providers = load_providers()
    routers = load_routers()
    data = []
    now = int(time.time())
    for rid, meta in routers.items():
        data.append(
            {
                "id": rid,
                "object": "model",
                "created": now,
                "owned_by": "router",
                "description": (meta or {}).get("description") if isinstance(meta, dict) else "",
            }
        )
    for m in list_upstream_models(providers):
        data.append(
            {
                "id": m["id"],
                "object": "model",
                "created": now,
                "owned_by": m["owned_by"],
            }
        )
    return {"object": "list", "data": data}


@app.get("/v1/models")
def models(_: None = Depends(_auth)) -> dict[str, Any]:
    return _models_payload()


@app.get("/models")
def models_alias(_: None = Depends(_auth)) -> dict[str, Any]:
    return _models_payload()


@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def chat_completions(request: Request, _: None = Depends(_auth)):
    await ensure_not_maintenance()
    await require_entitlement()
    reserved = 0
    try:
        reserved = await reserve_quota()
        return await _chat_completions_inner(request)
    finally:
        if reserved:
            try:
                await release_quota(reserved)
            except Exception:
                pass


async def _chat_completions_inner(request: Request):
    cfg, providers, routers = reload_all()
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body required")

    client_model = str(body.get("model") or "daily")
    stream = bool(body.get("stream"))
    timeout = float(cfg.get("request_timeout_sec") or 120)
    max_retries = int(cfg.get("max_retries_per_request") or 3)
    has_tools = bool(body.get("tools"))
    # WorkBuddy 画布/Ardot：即使用户选了「识图」，也强制改走 Agent，避免 VL 死磕 batch_edit。
    remounted = remount_route_for_tools(client_model, body)
    if remounted != client_model:
        client_model = remounted
        body = dict(body)
        body["model"] = client_model
    fast = is_fast_route(client_model)
    daily = is_daily_route(client_model)
    snappy = is_snappy_route(client_model)
    complex_route = is_complex_route(client_model)
    novel_route = is_novel_route(client_model)
    coding_route = is_coding_route(client_model)

    # Snappy routes: low reasoning + short stall so WorkBuddy Agent feels snappy.
    body = prepare_body_for_upstream(body, client_model)
    if snappy:
        stall_sec = float(
            cfg.get("fast_stream_stall_sec")
            if fast
            else cfg.get("daily_stream_stall_sec")
            or cfg.get("stream_stall_sec")
            or 5
        )
        timeout = min(
            timeout,
            float(
                cfg.get("fast_request_timeout_sec")
                if fast
                else cfg.get("daily_request_timeout_sec")
                or cfg.get("fast_request_timeout_sec")
                or 25
            ),
        )
        if has_tools:
            stall_sec = float(cfg.get("fast_tool_stream_stall_sec") or 8)
            timeout = min(
                max(timeout, float(cfg.get("fast_tool_request_timeout_sec") or 60)),
                float(cfg.get("fast_tool_request_timeout_sec") or 60),
            )
        max_retries = min(max_retries, int(cfg.get("fast_max_retries") or 3))
    elif complex_route or novel_route:
        # Smart / long-form: allow slow thinking; stall-fail over if hung.
        stall_sec = float(cfg.get("complex_stream_stall_sec") or 30)
        timeout = float(cfg.get("complex_request_timeout_sec") or 180)
        if novel_route:
            stall_sec = float(cfg.get("novel_stream_stall_sec") or stall_sec)
            timeout = float(cfg.get("novel_request_timeout_sec") or timeout)
        if has_tools:
            stall_sec = max(stall_sec, float(cfg.get("complex_tool_stream_stall_sec") or 45))
            timeout = max(timeout, float(cfg.get("complex_tool_request_timeout_sec") or 240))
        max_retries = min(max(max_retries, int(cfg.get("complex_max_retries") or 6)), 8)
    elif coding_route:
        # Coding: prefer Coder models; tools need longer wait but still fail over.
        stall_sec = float(cfg.get("code_stream_stall_sec") or 20)
        timeout = float(cfg.get("code_request_timeout_sec") or 120)
        if has_tools:
            stall_sec = max(stall_sec, float(cfg.get("code_tool_stream_stall_sec") or 35))
            timeout = max(timeout, float(cfg.get("code_tool_request_timeout_sec") or 180))
        max_retries = min(max(max_retries, int(cfg.get("code_max_retries") or 4)), 5)
    else:
        stall_sec = float(cfg.get("stream_stall_sec") or 8)
        # Cap per-attempt wait so a hung NVIDIA candidate fails over quickly.
        timeout = min(timeout, float(cfg.get("request_timeout_sec") or 60), 60.0)
        if has_tools:
            stall_sec = max(stall_sec, float(cfg.get("tool_stream_stall_sec") or 20))
            timeout = max(timeout, min(float(cfg.get("tool_request_timeout_sec") or 120), 120.0))

    candidates = resolve_candidates(client_model, providers, routers)
    if not candidates:
        raise HTTPException(
            status_code=503,
            detail="No upstream candidate. Fill providers API keys in the UI or data/providers.json.",
        )

    errors: list[dict[str, Any]] = []
    tried: set[tuple[str, str]] = set()
    import uuid as _uuid

    client_request_id = (
        (request.headers.get("x-request-id") or request.headers.get("x-client-request-id") or "")
        .strip()[:48]
        or _uuid.uuid4().hex[:16]
    )

    async def _attempt(provider: dict[str, Any], upstream_model: str) -> Any | None:
        key = (str(provider.get("name") or ""), upstream_model)
        if key in tried:
            return None
        tried.add(key)
        plimit = provider_limit_from_config(cfg)

        async def _do_attempt() -> Any | None:
            resp, stream_iter, meta = await forward_chat(
                provider=provider,
                upstream_model=upstream_model,
                client_model=client_model,
                body=body,
                timeout_sec=timeout,
                stream=stream,
                stall_sec=stall_sec,
                client_request_id=client_request_id,
            )
            gateway_headers = {
                "X-Gateway-Provider": _ascii_header(meta.get("provider")),
                "X-Gateway-Model": _ascii_header(meta.get("upstream_model")),
                "X-Request-Id": _ascii_header(meta.get("request_id") or ""),
            }
            if stream:
                if stream_iter is not None:
                    try:
                        return StreamingResponse(
                            stream_iter,
                            media_type="text/event-stream",
                            headers={
                                **gateway_headers,
                                "Cache-Control": "no-cache",
                                "Connection": "keep-alive",
                                "X-Accel-Buffering": "no",
                            },
                        )
                    except UnicodeEncodeError:
                        return StreamingResponse(
                            stream_iter,
                            media_type="text/event-stream",
                            headers={
                                "Cache-Control": "no-cache",
                                "Connection": "keep-alive",
                                "X-Accel-Buffering": "no",
                                "X-Request-Id": _ascii_header(meta.get("request_id") or ""),
                            },
                        )
                errors.append(
                    {
                        "provider": meta.get("provider"),
                        "model": meta.get("upstream_model"),
                        "error": meta.get("error"),
                        "status_code": meta.get("status_code"),
                    }
                )
                return None

            if resp is not None and (meta.get("status_code") or resp.status_code) < 400:
                raw = meta.get("_raw")
                if isinstance(raw, dict) and not stream:
                    if not _usable_chat_payload(raw):
                        errors.append(
                            {
                                "provider": meta.get("provider"),
                                "model": meta.get("upstream_model"),
                                "error": "empty assistant content",
                                "status_code": meta.get("status_code"),
                            }
                        )
                        return None
                    return JSONResponse(content=raw, headers=gateway_headers)
                if isinstance(raw, dict):
                    return JSONResponse(content=raw, headers=gateway_headers)
                return JSONResponse(content={"raw": raw}, headers=gateway_headers)

            errors.append(
                {
                    "provider": meta.get("provider"),
                    "model": meta.get("upstream_model"),
                    "error": meta.get("error"),
                    "status_code": meta.get("status_code"),
                }
            )
            return None

        pname = str(provider.get("name") or "unknown")
        if plimit > 0:
            async with provider_slot(pname, plimit):
                return await _do_attempt()
        return await _do_attempt()

    try_n = max(1, min(len(candidates), max_retries))
    if novel_route:
        try_n = min(len(candidates), max(max_retries, int(cfg.get("novel_max_retries") or 6)))

    use_hedge = (
        snappy
        and bool(cfg.get("fast_hedged_requests", True))
        and (not has_tools or bool(cfg.get("fast_hedge_with_tools", False)))
        and len(candidates) >= 2
    )
    hedge_n = 0
    if use_hedge:
        hedge_n = min(int(cfg.get("fast_hedge_candidates") or 2), try_n, len(candidates))
        hit = await race_first_success(candidates[:hedge_n], _attempt)
        if hit is not None:
            return hit

    for provider, upstream_model in candidates[hedge_n:try_n]:
        hit = await _attempt(provider, upstream_model)
        if hit is not None:
            return hit

    # Novel last resort: borrow stable models from 日常 before 502.
    if novel_route and bool(cfg.get("novel_fallback_daily", True)):
        fallback = resolve_candidates("日常", providers, routers)
        for provider, upstream_model in fallback[:4]:
            hit = await _attempt(provider, upstream_model)
            if hit is not None:
                return hit

    raise HTTPException(
        status_code=502,
        detail={
            "message": "所有上游候选均失败",
            "code": "UPSTREAM_EXHAUSTED",
            "errors": [enrich_error_entry(e) for e in errors],
            "hint": remediation_hint(
                classify_error(str((errors[-1] or {}).get("error") or "")) if errors else "unknown"
            ),
        },
    )


# ----- account / shop / license proxy (run-jane) -----


@app.get("/api/license/status")
async def api_license_status(refresh: bool = False) -> dict[str, Any]:
    if refresh and license_required():
        await refresh_status(force=True)
    return entitlement_snapshot()


@app.get("/api/license/usage-history")
async def api_license_usage_history(limit: int = 50) -> dict[str, Any]:
    if not license_required():
        return {"items": []}
    sess = load_session()
    if not sess.get("token"):
        raise HTTPException(status_code=401, detail="未登录")
    data = await jane_request(
        "GET",
        f"/gateway/license/usage-history?limit={max(1, min(200, int(limit or 50)))}",
        timeout=12.0,
    )
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        raw = data.get("items") or data.get("list") or data.get("records") or []
        items = raw if isinstance(raw, list) else []
    else:
        items = []
    return {"items": items}


@app.get("/api/remote/bootstrap")
async def api_remote_bootstrap() -> dict[str, Any]:
    cfg = load_config()
    local = {
        "version": __version__,
        "require_license": license_required(cfg),
        "license_api_base": bool((cfg.get("license_api_base") or "").strip()),
        "project_id": cfg.get("license_project_id"),
    }
    if not (cfg.get("license_api_base") or "").strip():
        return {
            **local,
            "announcement": "未配置授权服务地址（license_api_base）。开发模式可关闭 require_license。",
            "disclaimer": DEFAULT_DISCLAIMER,
            "guideSteps": "1. 配置上游 Key\n2. 点「同步到本机客户端」（自动写入 WorkBuddy / Cursor 等）\n3. 模型列表选「日常 · 大帅网关」",
            "apiKeyGuide": "到上游平台注册并复制 API Key，粘贴到「上游渠道」。",
            "latestVersion": __version__,
            "downloadUrl": "",
        }
    try:
        data = await jane_request("GET", "/gateway/meta/bootstrap", timeout=8.0)
    except Exception:
        # Don't block UI / desktop shell if remote is slow or down
        return {
            **local,
            "announcement": "授权服务暂时不可达，可稍后点「检查更新」重试。",
            "disclaimer": DEFAULT_DISCLAIMER,
            "guideSteps": "",
            "apiKeyGuide": "",
            "latestVersion": __version__,
            "downloadUrl": "",
            "offline": True,
        }
    if not isinstance(data, dict):
        data = {}
    # normalize camelCase for UI
    out = {
        **local,
        "announcement": data.get("announcement") or "",
        "disclaimer": data.get("disclaimer") or DEFAULT_DISCLAIMER,
        "guideSteps": data.get("guideSteps") or data.get("guide_steps") or "",
        "apiKeyGuide": data.get("apiKeyGuide") or data.get("api_key_guide") or "",
        "latestVersion": data.get("latestVersion") or data.get("latest_version") or __version__,
        "downloadUrl": data.get("downloadUrl") or data.get("download_url") or "",
        "downloadSha256": data.get("downloadSha256") or data.get("download_sha256") or "",
        "changelog": data.get("changelog") or "",
        "forceUpdate": bool(data.get("forceUpdate") or data.get("force_update")),
        "projectId": data.get("projectId") or data.get("project_id") or cfg.get("license_project_id"),
        "projectName": data.get("projectName") or data.get("project_name") or "大帅网关",
        "maintenanceEnabled": bool(data.get("maintenanceEnabled") or data.get("maintenance_enabled")),
        "maintenanceMessage": data.get("maintenanceMessage") or data.get("maintenance_message") or "",
    }
    if out.get("projectId") and not cfg.get("license_project_id"):
        cfg2 = load_config()
        cfg2["license_project_id"] = out["projectId"]
        save_config(cfg2)
    return out


@app.post("/api/account/register")
async def api_account_register(request: Request) -> dict[str, Any]:
    body = await request.json()
    payload = {
        "username": (body or {}).get("username"),
        "password": (body or {}).get("password"),
        "confirmPassword": (body or {}).get("confirmPassword") or (body or {}).get("password"),
        "typed": 0,
    }
    await jane_request("POST", "/user/register", json_body=payload)
    return {"ok": True}


@app.post("/api/account/login")
async def api_account_login(request: Request) -> dict[str, Any]:
    body = await request.json()
    data = await jane_request(
        "POST",
        "/user/login",
        json_body={
            "username": (body or {}).get("username"),
            "password": (body or {}).get("password"),
            "typed": 0,
        },
    )
    if not isinstance(data, dict) or not data.get("token"):
        raise HTTPException(status_code=401, detail="登录失败")
    sess = load_session()
    sess["token"] = data.get("token")
    sess["refresh_token"] = data.get("refreshToken") or data.get("refresh_token")
    sess["user_id"] = data.get("userId") or data.get("user_id")
    sess["username"] = data.get("username")
    save_session(sess)
    try:
        status = await jane_request("GET", "/gateway/license/status", token=str(data.get("token")))
        if isinstance(status, dict):
            cache_entitlement(status)
    except Exception:
        pass
    return {"ok": True, "license": entitlement_snapshot()}


@app.post("/api/account/logout")
async def api_account_logout() -> dict[str, Any]:
    clear_session()
    return {"ok": True}


@app.get("/api/account/me")
async def api_account_me() -> dict[str, Any]:
    return entitlement_snapshot()


@app.post("/api/license/redeem")
async def api_license_redeem(request: Request) -> dict[str, Any]:
    body = await request.json()
    code = str((body or {}).get("cardCode") or (body or {}).get("card_code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="请输入卡密")
    data = await jane_request("POST", "/gateway/license/redeem", json_body={"cardCode": code})
    if isinstance(data, dict):
        cache_entitlement(data)
    return {"ok": True, "license": entitlement_snapshot()}


@app.get("/api/shop/catalog")
async def api_shop_catalog() -> dict[str, Any]:
    cfg = load_config()
    project_id = cfg.get("license_project_id")
    if not project_id:
        boot = await api_remote_bootstrap()
        project_id = boot.get("projectId")
    params: dict[str, Any] = {}
    if project_id:
        params["projectId"] = project_id
    features = await jane_request("GET", "/cardSale/feature/list", params=params or None)
    prices = await jane_request("GET", "/cardSale/price/list", params=params or None)
    types = await jane_request("GET", "/cardSale/type/list")
    return {
        "projectId": project_id,
        "features": features if isinstance(features, list) else [],
        "prices": prices if isinstance(prices, list) else [],
        "types": types if isinstance(types, list) else [],
    }


@app.post("/api/shop/order")
async def api_shop_order(request: Request) -> dict[str, Any]:
    body = await request.json()
    sess = load_session()
    if not sess.get("token"):
        raise HTTPException(status_code=401, detail="请先登录")
    email = str((body or {}).get("buyerEmail") or (body or {}).get("buyer_email") or "").strip()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="请填写有效收货邮箱（用于接收卡密）")
    payload = {
        "priceId": (body or {}).get("priceId") or (body or {}).get("price_id"),
        "channel": (body or {}).get("channel") or "WECHAT",
        "buyerEmail": email,
        "wechatScene": (body or {}).get("wechatScene") or "NATIVE",
        "referrerSource": (body or {}).get("referrerSource") or "dashuai-gateway",
    }
    data = await jane_request("POST", "/cardSale/order/create", json_body=payload)
    return data if isinstance(data, dict) else {"raw": data}


@app.get("/api/shop/order/{order_no}")
async def api_shop_order_get(order_no: str, verifyAmount: float | None = None) -> dict[str, Any]:
    params = {}
    if verifyAmount is not None:
        params["verifyAmount"] = verifyAmount
    data = await jane_request("GET", f"/cardSale/order/{order_no}", params=params or None)
    return data if isinstance(data, dict) else {"raw": data}


@app.post("/api/shop/order/{order_no}/redeem")
async def api_shop_order_redeem(order_no: str) -> dict[str, Any]:
    """After paid: redeem cardCode from order onto current user."""
    data = await jane_request("GET", f"/cardSale/order/{order_no}")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="查单失败")
    status = str(data.get("status") or "").upper()
    card = data.get("cardCode") or data.get("card_code")
    if status != "PAID" or not card:
        return {"ok": False, "paid": status == "PAID", "order": data, "message": "订单未支付或尚未发卡"}
    redeemed = await jane_request("POST", "/gateway/license/redeem", json_body={"cardCode": card})
    if isinstance(redeemed, dict):
        cache_entitlement(redeemed)
    return {"ok": True, "cardCode": card, "license": entitlement_snapshot()}


_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if _WEB_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(_WEB_DIR), html=True), name="ui")
