"""HTTP server: REST API + MCP streamable HTTP at /mcp."""

from __future__ import annotations

import inspect
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
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


def _tool_to_schema(tool: Tool) -> Dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.params_model.model_json_schema(),
    }


def _validate_params(tool: Tool, raw: Any) -> BaseModel:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object"
        )
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

    @app.get("/healthz")
    async def healthz() -> Dict[str, Any]:
        return {"status": "ok", "authorized": holder._client is not None}

    @app.get("/api/tools")
    async def list_tools_route() -> Dict[str, Any]:
        return {"tools": [_tool_to_schema(t) for t in REGISTRY.values()]}

    @app.post("/api/tools/{name}")
    async def call_tool(name: str, request: Request) -> JSONResponse:
        tool = REGISTRY.get(name)
        if tool is None:
            raise HTTPException(status_code=404, detail=f"unknown tool: {name}")

        body = await request.body()
        if body:
            try:
                raw = json.loads(body)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=400, detail=f"invalid JSON: {exc}"
                ) from exc
        else:
            raw = {}

        params = _validate_params(tool, raw)
        result = await _invoke(holder, tool, params)
        return JSONResponse(content={"result": result})

    app.mount("/mcp", mcp.streamable_http_app())

    return app
