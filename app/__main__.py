"""Entry point.

Usage:
    python -m app          # start HTTP server
    python -m app login    # interactive login to generate TELETHON_SESSION
"""

from __future__ import annotations

import logging
import sys

import uvicorn

from app.config import Config
from app.login import run as run_login
from app.server import build_app


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "serve"

    if command == "login":
        try:
            cfg = Config.for_login()
        except RuntimeError as exc:
            print(f"config error: {exc}", file=sys.stderr)
            sys.exit(2)
        run_login(cfg)
        return

    if command != "serve":
        print(f"unknown command {command!r} — valid: serve, login", file=sys.stderr)
        sys.exit(2)

    try:
        cfg = Config.from_env()
    except RuntimeError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        sys.exit(2)

    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    logging.getLogger("telethon").setLevel(max(cfg.log_level, logging.WARNING))

    app = build_app(cfg)

    uvicorn.run(
        app,
        host=cfg.listen_host,
        port=cfg.listen_port,
        log_level=logging.getLevelName(cfg.log_level).lower(),
        access_log=cfg.log_level <= logging.INFO,
    )


if __name__ == "__main__":
    main()
