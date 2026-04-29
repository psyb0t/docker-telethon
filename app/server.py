"""HTTP server: REST API + MCP streamable HTTP at /mcp."""

from __future__ import annotations

import inspect
import json
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ValidationError
from telethon.errors import RPCError

from app.client import TelethonHolder
from app.config import Config
from app.tools import REGISTRY, ParamsModel, Tool

log = logging.getLogger(__name__)


def _model_to_signature(model: ParamsModel) -> inspect.Signature:
    _MISSING = object()
    params = []
    for name, field in model.model_fields.items():
        if field.is_required():
            default = inspect.Parameter.empty
        else:
            default = field.default if field.default is not _MISSING else inspect.Parameter.empty
        params.append(
            inspect.Parameter(
                name,
                inspect.Parameter.KEYWORD_ONLY,
                default=default,
                annotation=field.annotation,
            )
        )
    return inspect.Signature(params)


def _validate_params(tool: Tool, raw: Any) -> BaseModel:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="request body must be a JSON object")
    try:
        return tool.params_model.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors()) from exc


async def _invoke(holder: TelethonHolder, tool: Tool, params: BaseModel) -> Any:
    try:
        return await tool.handler(holder, params)
    except RPCError as exc:
        log.warning("telegram RPC error in %s: %s", tool.name, exc)
        raise HTTPException(
            status_code=502,
            detail={"telegram_error": exc.__class__.__name__, "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _parse_body(request: Request) -> dict:
    body = await request.body()
    if not body:
        return {}
    try:
        raw = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="request body must be a JSON object")
    return raw


def build_mcp(holder: TelethonHolder, host: str, port: int) -> FastMCP:
    mcp = FastMCP(
        name="docker-telethon",
        instructions=(
            "Telegram client tools backed by Telethon. "
            "All chat references accept usernames, phone numbers, t.me links, "
            "or numeric IDs as strings."
        ),
        host=host,
        port=port,
        streamable_http_path="/",
        stateless_http=True,
    )

    for tool in REGISTRY.values():
        _mount_mcp_tool(mcp, holder, tool)

    return mcp


def _mount_mcp_tool(mcp: FastMCP, holder: TelethonHolder, tool: Tool) -> None:
    params_model = tool.params_model

    async def _call(**kwargs: Any) -> Any:
        try:
            params = params_model.model_validate(kwargs)
            return await tool.handler(holder, params)
        except RPCError as exc:
            return {
                "error": "telegram_rpc",
                "type": exc.__class__.__name__,
                "message": str(exc),
            }
        except ValueError as exc:
            return {"error": "invalid_argument", "message": str(exc)}

    _call.__name__ = tool.name
    _call.__doc__ = tool.description
    _call.__signature__ = _model_to_signature(params_model)
    _call.__annotations__ = {
        **{n: f.annotation for n, f in params_model.model_fields.items()},
        "return": Any,
    }
    mcp.tool(name=tool.name, description=tool.description)(_call)


def build_app(cfg: Config) -> FastAPI:
    holder = TelethonHolder(cfg)
    mcp = build_mcp(holder, cfg.listen_host, cfg.listen_port)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await holder.start()
        async with mcp.session_manager.run():
            try:
                yield
            finally:
                await holder.stop()

    app = FastAPI(
        title="docker-telethon",
        description="HTTP + MCP front-end for the Telethon Telegram client.",
        version="1.0.0",
        lifespan=lifespan,
    )

    if cfg.auth_key:
        @app.middleware("http")
        async def _auth(request: Request, call_next: Any) -> Response:
            if request.url.path == "/healthz":
                return await call_next(request)
            header = request.headers.get("Authorization", "")
            token = header.removeprefix("Bearer ").strip()
            if not secrets.compare_digest(token, cfg.auth_key):
                return Response(
                    content='{"detail":"unauthorized"}',
                    status_code=401,
                    media_type="application/json",
                )
            return await call_next(request)

    @app.get("/healthz")
    async def healthz() -> Dict[str, Any]:
        return {"status": "ok", "authorized": holder._client is not None}

    @app.get("/api/me")
    async def get_me() -> JSONResponse:
        params = _validate_params(REGISTRY["get_me"], {})
        result = await _invoke(holder, REGISTRY["get_me"], params)
        return JSONResponse(content={"result": result})

    @app.get("/api/entities")
    async def get_entity(request: Request) -> JSONResponse:
        raw = dict(request.query_params)
        params = _validate_params(REGISTRY["get_entity"], raw)
        result = await _invoke(holder, REGISTRY["get_entity"], params)
        return JSONResponse(content={"result": result})

    @app.get("/api/dialogs")
    async def get_dialogs(request: Request) -> JSONResponse:
        raw = dict(request.query_params)
        params = _validate_params(REGISTRY["get_dialogs"], raw)
        result = await _invoke(holder, REGISTRY["get_dialogs"], params)
        return JSONResponse(content={"result": result})

    @app.get("/api/messages")
    async def get_messages(request: Request) -> JSONResponse:
        raw = dict(request.query_params)
        params = _validate_params(REGISTRY["get_messages"], raw)
        result = await _invoke(holder, REGISTRY["get_messages"], params)
        return JSONResponse(content={"result": result})

    @app.post("/api/messages")
    async def send_message(request: Request) -> JSONResponse:
        raw = await _parse_body(request)
        params = _validate_params(REGISTRY["send_message"], raw)
        result = await _invoke(holder, REGISTRY["send_message"], params)
        return JSONResponse(content={"result": result})

    @app.post("/api/messages/forward")
    async def forward_messages(request: Request) -> JSONResponse:
        raw = await _parse_body(request)
        params = _validate_params(REGISTRY["forward_messages"], raw)
        result = await _invoke(holder, REGISTRY["forward_messages"], params)
        return JSONResponse(content={"result": result})

    @app.post("/api/messages/read")
    async def mark_read(request: Request) -> JSONResponse:
        raw = await _parse_body(request)
        params = _validate_params(REGISTRY["mark_read"], raw)
        result = await _invoke(holder, REGISTRY["mark_read"], params)
        return JSONResponse(content={"result": result})

    @app.patch("/api/messages/{message_id}")
    async def edit_message(message_id: int, request: Request) -> JSONResponse:
        raw = await _parse_body(request)
        raw["message_id"] = message_id
        params = _validate_params(REGISTRY["edit_message"], raw)
        result = await _invoke(holder, REGISTRY["edit_message"], params)
        return JSONResponse(content={"result": result})

    @app.delete("/api/messages")
    async def delete_messages(request: Request) -> JSONResponse:
        raw = await _parse_body(request)
        params = _validate_params(REGISTRY["delete_messages"], raw)
        result = await _invoke(holder, REGISTRY["delete_messages"], params)
        return JSONResponse(content={"result": result})

    @app.post("/api/files")
    async def send_file(request: Request) -> JSONResponse:
        raw = await _parse_body(request)
        params = _validate_params(REGISTRY["send_file"], raw)
        result = await _invoke(holder, REGISTRY["send_file"], params)
        return JSONResponse(content={"result": result})

    @app.get("/api/participants")
    async def get_participants(request: Request) -> JSONResponse:
        raw = dict(request.query_params)
        params = _validate_params(REGISTRY["get_participants"], raw)
        result = await _invoke(holder, REGISTRY["get_participants"], params)
        return JSONResponse(content={"result": result})

    @app.post("/api/chats")
    async def create_group(request: Request) -> JSONResponse:
        raw = await _parse_body(request)
        params = _validate_params(REGISTRY["create_group"], raw)
        result = await _invoke(holder, REGISTRY["create_group"], params)
        return JSONResponse(content={"result": result})

    @app.post("/api/chats/join")
    async def join_chat(request: Request) -> JSONResponse:
        raw = await _parse_body(request)
        params = _validate_params(REGISTRY["join_chat"], raw)
        result = await _invoke(holder, REGISTRY["join_chat"], params)
        return JSONResponse(content={"result": result})

    @app.post("/api/chats/leave")
    async def leave_chat(request: Request) -> JSONResponse:
        raw = await _parse_body(request)
        params = _validate_params(REGISTRY["leave_chat"], raw)
        result = await _invoke(holder, REGISTRY["leave_chat"], params)
        return JSONResponse(content={"result": result})

    @app.delete("/api/chats")
    async def delete_chat(request: Request) -> JSONResponse:
        raw = await _parse_body(request)
        params = _validate_params(REGISTRY["delete_chat"], raw)
        result = await _invoke(holder, REGISTRY["delete_chat"], params)
        return JSONResponse(content={"result": result})

    app.mount("/mcp", mcp.streamable_http_app())

    return app
