"""Env-driven configuration."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} environment variable is required")
    return value


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from exc


def _split_host_port(addr: str) -> tuple[str, int]:
    if ":" not in addr:
        raise RuntimeError(
            f"TELETHON_HTTP_LISTEN_ADDRESS must be host:port, got {addr!r}"
        )
    host, _, port = addr.rpartition(":")
    try:
        return host or "0.0.0.0", int(port)
    except ValueError as exc:
        raise RuntimeError(f"invalid port in {addr!r}") from exc


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    session: str
    listen_host: str
    listen_port: int
    log_level: int
    request_timeout: float
    flood_sleep_threshold: int
    device_model: str
    system_version: str
    app_version: str
    proxy: str
    download_dir: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls._build(require_session=True)

    @classmethod
    def for_login(cls) -> "Config":
        """Minimal config for the interactive login flow — no session required."""
        return cls._build(require_session=False)

    @classmethod
    def _build(cls, *, require_session: bool) -> "Config":
        api_id = _int("TELETHON_API_ID", 0)
        if api_id == 0:
            raise RuntimeError("TELETHON_API_ID environment variable is required")

        host, port = _split_host_port(
            os.environ.get("TELETHON_HTTP_LISTEN_ADDRESS", "0.0.0.0:8080")
        )

        level_name = os.environ.get("TELETHON_LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, level_name, logging.INFO)

        session = (
            _required("TELETHON_SESSION") if require_session
            else os.environ.get("TELETHON_SESSION", "")
        )

        return cls(
            api_id=api_id,
            api_hash=_required("TELETHON_API_HASH"),
            session=session,
            listen_host=host,
            listen_port=port,
            log_level=log_level,
            request_timeout=float(
                os.environ.get("TELETHON_REQUEST_TIMEOUT", "60")
            ),
            flood_sleep_threshold=_int("TELETHON_FLOOD_SLEEP_THRESHOLD", 60),
            device_model=os.environ.get("TELETHON_DEVICE_MODEL", "docker-telethon"),
            system_version=os.environ.get("TELETHON_SYSTEM_VERSION", "1.0"),
            app_version=os.environ.get("TELETHON_APP_VERSION", "1.0"),
            proxy=os.environ.get("TELETHON_PROXY", ""),
            download_dir=os.environ.get("TELETHON_DOWNLOAD_DIR", "/tmp/telethon"),
        )
