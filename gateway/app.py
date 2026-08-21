from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from . import __version__
from .config import reload_all
from .proxy import forward_chat
from .router import list_upstream_models, resolve_candidates
from .state import STATE

app = FastAPI(title="Free LLM Gateway", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if WEB_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(WEB_DIR), html=True), name="ui")


def _auth(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
) -> None:
    cfg, _, _ = reload_all()
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


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "name": "free-llm-gateway",
        "version": __version__,
        "openai_base": "/v1",
        "ui": "/ui/",
        "health": "/health",
        "license": "none - no expiry, no activation",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    cfg, providers, routers = reload_all()
    enabled = [
        p.get("name")
        for p in providers
        if p.get("enabled", True)
        and (p.get("api_key") or "").strip()
        and not str(p.get("api_key")).startswith("REPLACE_")
    ]
    return {
        "ok": True,
        "version": __version__,
        "port": cfg.get("port"),
        "providers_ready": enabled,
        "routes": list(routers.keys()),
        "channels": STATE.snapshot(),
    }


@app.post("/admin/reload")
def admin_reload(_: None = Depends(_auth)) -> dict[str, str]:
    reload_all()
    return {"status": "reloaded"}


@app.get("/v1/models")
def models(_: None = Depends(_auth)) -> dict[str, Any]:
    _, providers, routers = reload_all()
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


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, _: None = Depends(_auth)):
    cfg, providers, routers = reload_all()
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body required")

    model = body.get("model") or "daily"
    stream = bool(body.get("stream"))
    timeout = float(cfg.get("request_timeout_sec") or 120)
    max_retries = int(cfg.get("max_retries_per_request") or 4)

    candidates = resolve_candidates(str(model), providers, routers)
    if not candidates:
        raise HTTPException(
            status_code=503,
            detail="No upstream candidate. Fill data/providers.json API keys and models.",
        )

    errors: list[dict[str, Any]] = []
    for provider, upstream_model in candidates[: max(1, max_retries)]:
        resp, stream_iter, meta = await forward_chat(
            provider=provider,
            upstream_model=upstream_model,
            body=body,
            timeout_sec=timeout,
            stream=stream,
        )
        if stream:
            if stream_iter is not None:
                return StreamingResponse(
                    stream_iter,
                    media_type="text/event-stream",
                    headers={
                        "X-Gateway-Provider": str(meta.get("provider")),
                        "X-Gateway-Model": str(meta.get("upstream_model")),
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    },
                )
            errors.append(meta)
            continue

        if resp is not None and resp.status_code < 400:
            raw = meta.get("_raw")
            client = meta.get("_client")
            try:
                if isinstance(raw, dict):
                    # expose which upstream served this call
                    raw = dict(raw)
                    raw.setdefault("gateway", {})
                    if isinstance(raw["gateway"], dict):
                        raw["gateway"].update(
                            {
                                "provider": meta.get("provider"),
                                "upstream_model": meta.get("upstream_model"),
                                "latency_ms": meta.get("latency_ms"),
                            }
                        )
                    return JSONResponse(content=raw)
                return JSONResponse(content={"raw": raw})
            finally:
                if client is not None:
                    await client.aclose()
                await resp.aclose()

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
