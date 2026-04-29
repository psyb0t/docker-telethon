#!/usr/bin/env python3
"""Thin shim — kept for backwards compat. Prefer: docker run psyb0t/telethon login"""

import sys

from app.config import Config
from app.login import run

if __name__ == "__main__":
    try:
        cfg = Config.for_login()
    except RuntimeError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        sys.exit(2)
    run(cfg)
