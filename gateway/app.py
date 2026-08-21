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
from .config import (
    load_config,
    load_providers,
    load_routers,
    overview_payload,
    reload_all,
    save_config,
    save_providers,
    save_routers,
)
from .proxy import aclose_http_client, forward_chat, probe_provider, usage_summary
from .router import list_upstream_models, resolve_candidates
from .state import STATE
from .workbuddy import sync_workbuddy, workbuddy_status


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
    yield
    await aclose_http_client()


app = FastAPI(title=__product__, version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _auth(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
) -> None:
    cfg = load_config()
    expected = (cfg.get("local_api_key") or "").strip()
    if not expected:
        return
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_api_key:
        token = x_api_key.strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


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
        "license": "none - no expiry, no activation",
    }


@app.get("/health")
def health(request: Request) -> dict[str, Any]:
    data = overview_payload(_public_base(request))
    data["version"] = __version__
    data["channels"] = STATE.snapshot()
    data["usage"] = usage_summary(200)
    return data


@app.get("/api/overview")
def api_overview(request: Request) -> dict[str, Any]:
    data = overview_payload(_public_base(request))
    data["version"] = __version__
    data["channels"] = STATE.snapshot()
    data["usage"] = usage_summary(300)
    return data


@app.get("/api/usage")
def api_usage(_: None = Depends(_auth)) -> dict[str, Any]:
    return usage_summary(1000)


@app.post("/api/probe")
async def api_probe(request: Request, _: None = Depends(_auth)) -> dict[str, Any]:
    body = await request.json()
    name = (body or {}).get("name") if isinstance(body, dict) else None
    providers = load_providers()
    target = None
    if name:
        for p in providers:
            if p.get("name") == name:
                target = p
                break
    elif providers:
        target = next((p for p in providers if (p.get("api_key") or "").strip() and not str(p.get("api_key")).startswith("REPLACE_")), None)
    if not target:
        raise HTTPException(status_code=404, detail="provider not found or not configured")
    cfg = load_config()
    timeout = float(cfg.get("request_timeout_sec") or 120)
    return await probe_provider(target, timeout_sec=min(60.0, timeout))


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
    ):
        if key in body:
            cfg[key] = body[key]
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
                "free_only": bool(item.get("free_only", False)),
                "weight": item.get("weight", 1),
                "enabled": bool(item.get("enabled", True)),
            }
        )
    save_providers(cleaned)
    return {"status": "saved", "count": len(cleaned)}


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


@app.get("/api/integrations/workbuddy")
def get_workbuddy_integration(_: None = Depends(_auth)) -> dict[str, Any]:
    return workbuddy_status()


@app.post("/api/integrations/workbuddy")
def post_workbuddy_integration(_: None = Depends(_auth)) -> dict[str, Any]:
    return sync_workbuddy()


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
    cfg, providers, routers = reload_all()
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body required")

    client_model = str(body.get("model") or "daily")
    stream = bool(body.get("stream"))
    timeout = float(cfg.get("request_timeout_sec") or 120)
    max_retries = int(cfg.get("max_retries_per_request") or 4)

    candidates = resolve_candidates(client_model, providers, routers)
    if not candidates:
        raise HTTPException(
            status_code=503,
            detail="No upstream candidate. Fill providers API keys in the UI or data/providers.json.",
        )

    errors: list[dict[str, Any]] = []
    for provider, upstream_model in candidates[: max(1, max_retries)]:
        resp, stream_iter, meta = await forward_chat(
            provider=provider,
            upstream_model=upstream_model,
            client_model=client_model,
            body=body,
            timeout_sec=timeout,
            stream=stream,
        )
        gateway_headers = {
            "X-Gateway-Provider": str(meta.get("provider")),
            "X-Gateway-Model": str(meta.get("upstream_model")),
            "X-Request-Id": str(meta.get("request_id") or ""),
        }
        if stream:
            if stream_iter is not None:
                return StreamingResponse(
                    stream_iter,
                    media_type="text/event-stream",
                    headers={
                        **gateway_headers,
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
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
            continue

        if resp is not None and (meta.get("status_code") or resp.status_code) < 400:
            raw = meta.get("_raw")
            if isinstance(raw, dict) and not stream:
                # Empty/null choices or blank content → try next candidate (common for Qwen3 thinking).
                if not _usable_chat_payload(raw):
                    errors.append(
                        {
                            "provider": meta.get("provider"),
                            "model": meta.get("upstream_model"),
                            "error": "empty assistant content",
                            "status_code": meta.get("status_code"),
                        }
                    )
                    continue
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

    raise HTTPException(
        status_code=502,
        detail={"message": "All upstream candidates failed", "errors": errors},
    )


_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if _WEB_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(_WEB_DIR), html=True), name="ui")
