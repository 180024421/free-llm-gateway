from __future__ import annotations

import argparse

import uvicorn

from .config import load_config


def main() -> None:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Free LLM Gateway")
    parser.add_argument("--host", default=cfg.get("host") or "127.0.0.1")
    parser.add_argument("--port", type=int, default=int(cfg.get("port") or 8010))
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run(
        "gateway.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
