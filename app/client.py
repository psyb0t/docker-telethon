"""Telethon client lifecycle and lock."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telethon import TelegramClient
from telethon.sessions import StringSession

from app.config import Config

log = logging.getLogger(__name__)


class TelethonHolder:
    """Single shared TelegramClient with a serialization lock.

    Telethon's TelegramClient is async-safe for most operations, but
    serializing API calls behind a lock makes flood/error semantics
    predictable across the REST + MCP surfaces sharing one client.
    """

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._client: Optional[TelegramClient] = None
        self._lock = asyncio.Lock()

    @property
    def client(self) -> TelegramClient:
        if self._client is None:
            raise RuntimeError("Telethon client not started")
        return self._client

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock

    async def start(self) -> None:
        if self._client is not None:
            return

        client = TelegramClient(
            StringSession(self._cfg.session),
            self._cfg.api_id,
            self._cfg.api_hash,
            device_model=self._cfg.device_model,
            system_version=self._cfg.system_version,
            app_version=self._cfg.app_version,
            request_retries=5,
            connection_retries=5,
            flood_sleep_threshold=self._cfg.flood_sleep_threshold,
            timeout=self._cfg.request_timeout,
        )

        log.info("connecting to Telegram")
        await client.connect()

        if not await client.is_user_authorized():
            await client.disconnect()
            raise RuntimeError(
                "TELETHON_SESSION is not authorized — generate a fresh one with "
                "the login helper (see README)."
            )

        self._client = client
        me = await client.get_me()
        log.info("authorized as id=%s username=%s", me.id, me.username)

    async def stop(self) -> None:
        if self._client is None:
            return
        log.info("disconnecting Telethon client")
        await self._client.disconnect()
        self._client = None
