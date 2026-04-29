"""Tool definitions exposed via REST and MCP.

Each tool is a coroutine `(holder, params) -> dict | list`. Pydantic models
describe the input schema. The same registry drives the REST routes under
`/api/` and the MCP tools at `/mcp`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field, ConfigDict
from telethon.tl.custom.message import Message
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    DeleteChannelRequest,
    JoinChannelRequest,
    LeaveChannelRequest,
)
from telethon.tl.types import User

from app.client import TelethonHolder

ParamsModel = type[BaseModel]
Handler = Callable[[TelethonHolder, BaseModel], Awaitable[Any]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params_model: ParamsModel
    handler: Handler


REGISTRY: Dict[str, Tool] = {}


def _register(tool: Tool) -> Tool:
    if tool.name in REGISTRY:
        raise RuntimeError(f"duplicate tool: {tool.name}")
    REGISTRY[tool.name] = tool
    return tool


def list_tools() -> List[Tool]:
    return list(REGISTRY.values())


def _entity_to_dict(entity: Any) -> Dict[str, Any]:
    if entity is None:
        return {}
    out: Dict[str, Any] = {
        "id": getattr(entity, "id", None),
        "type": type(entity).__name__,
    }
    for attr in ("username", "first_name", "last_name", "title", "phone", "bot"):
        value = getattr(entity, attr, None)
        if value is not None:
            out[attr] = value
    return out


def _message_to_dict(msg: Message) -> Dict[str, Any]:
    return {
        "id": msg.id,
        "date": msg.date.isoformat() if msg.date else None,
        "chat_id": getattr(msg.peer_id, "user_id", None)
        or getattr(msg.peer_id, "channel_id", None)
        or getattr(msg.peer_id, "chat_id", None),
        "sender_id": msg.sender_id,
        "text": msg.message or "",
        "out": msg.out,
        "reply_to_msg_id": msg.reply_to.reply_to_msg_id if msg.reply_to else None,
        "media": msg.media is not None,
        "media_type": type(msg.media).__name__ if msg.media else None,
    }


# ---------------------------------------------------------------------------
# get_me
# ---------------------------------------------------------------------------


class GetMeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


async def _get_me(holder: TelethonHolder, _: GetMeParams) -> Dict[str, Any]:
    async with holder.lock:
        me: User = await holder.client.get_me()
    return _entity_to_dict(me)


_register(
    Tool(
        name="get_me",
        description="Return the authorized account profile.",
        params_model=GetMeParams,
        handler=_get_me,
    )
)


# ---------------------------------------------------------------------------
# get_entity
# ---------------------------------------------------------------------------


class GetEntityParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat: str = Field(
        ..., description="Username, phone, t.me link, or numeric ID as string."
    )


def _coerce_chat(chat: str) -> Any:
    stripped = chat.strip()
    if stripped.lstrip("-").isdigit():
        return int(stripped)
    return stripped


async def _get_entity(
    holder: TelethonHolder, params: GetEntityParams
) -> Dict[str, Any]:
    async with holder.lock:
        entity = await holder.client.get_entity(_coerce_chat(params.chat))
    return _entity_to_dict(entity)


_register(
    Tool(
        name="get_entity",
        description="Resolve a chat reference (username, phone, link, or ID) to a profile.",
        params_model=GetEntityParams,
        handler=_get_entity,
    )
)


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------


class SendMessageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat: str = Field(..., description="Target chat (username/ID/phone).")
    text: str = Field(..., min_length=1, max_length=4096)
    parse_mode: Optional[str] = Field(
        None, description="One of: md, markdown, html, or null for plain text."
    )
    reply_to: Optional[int] = Field(
        None, description="Message ID to reply to."
    )
    silent: bool = Field(False, description="Send without notification.")
    link_preview: bool = Field(True, description="Allow link previews.")


async def _send_message(
    holder: TelethonHolder, params: SendMessageParams
) -> Dict[str, Any]:
    async with holder.lock:
        msg = await holder.client.send_message(
            entity=_coerce_chat(params.chat),
            message=params.text,
            parse_mode=params.parse_mode,
            reply_to=params.reply_to,
            silent=params.silent,
            link_preview=params.link_preview,
        )
    return _message_to_dict(msg)


_register(
    Tool(
        name="send_message",
        description="Send a text message to a chat.",
        params_model=SendMessageParams,
        handler=_send_message,
    )
)


# ---------------------------------------------------------------------------
# get_messages
# ---------------------------------------------------------------------------


class GetMessagesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat: str
    limit: int = Field(20, ge=1, le=200)
    offset_id: int = Field(0, ge=0)
    search: Optional[str] = None


async def _get_messages(
    holder: TelethonHolder, params: GetMessagesParams
) -> List[Dict[str, Any]]:
    async with holder.lock:
        result: List[Dict[str, Any]] = []
        async for msg in holder.client.iter_messages(
            entity=_coerce_chat(params.chat),
            limit=params.limit,
            offset_id=params.offset_id,
            search=params.search,
        ):
            result.append(_message_to_dict(msg))
    return result


_register(
    Tool(
        name="get_messages",
        description="Read recent messages from a chat (newest first).",
        params_model=GetMessagesParams,
        handler=_get_messages,
    )
)


# ---------------------------------------------------------------------------
# get_dialogs
# ---------------------------------------------------------------------------


class GetDialogsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(20, ge=1, le=200)
    archived: bool = False


async def _get_dialogs(
    holder: TelethonHolder, params: GetDialogsParams
) -> List[Dict[str, Any]]:
    async with holder.lock:
        dialogs = await holder.client.get_dialogs(
            limit=params.limit, archived=params.archived
        )
    out: List[Dict[str, Any]] = []
    for dialog in dialogs:
        item = _entity_to_dict(dialog.entity)
        item["unread_count"] = dialog.unread_count
        item["pinned"] = dialog.pinned
        if dialog.message is not None:
            item["last_message"] = _message_to_dict(dialog.message)
        out.append(item)
    return out


_register(
    Tool(
        name="get_dialogs",
        description="List your dialogs (chats, groups, channels).",
        params_model=GetDialogsParams,
        handler=_get_dialogs,
    )
)


# ---------------------------------------------------------------------------
# forward_messages
# ---------------------------------------------------------------------------


class ForwardMessagesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_chat: str
    to_chat: str
    message_ids: List[int] = Field(..., min_length=1, max_length=100)
    silent: bool = False


async def _forward_messages(
    holder: TelethonHolder, params: ForwardMessagesParams
) -> List[Dict[str, Any]]:
    async with holder.lock:
        result = await holder.client.forward_messages(
            entity=_coerce_chat(params.to_chat),
            messages=params.message_ids,
            from_peer=_coerce_chat(params.from_chat),
            silent=params.silent,
        )
    if not isinstance(result, list):
        result = [result]
    return [_message_to_dict(m) for m in result if m is not None]


_register(
    Tool(
        name="forward_messages",
        description="Forward one or more messages between chats.",
        params_model=ForwardMessagesParams,
        handler=_forward_messages,
    )
)


# ---------------------------------------------------------------------------
# delete_messages
# ---------------------------------------------------------------------------


class DeleteMessagesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat: str
    message_ids: List[int] = Field(..., min_length=1, max_length=100)
    revoke: bool = Field(True, description="Delete for everyone, not just you.")


async def _delete_messages(
    holder: TelethonHolder, params: DeleteMessagesParams
) -> Dict[str, Any]:
    async with holder.lock:
        affected = await holder.client.delete_messages(
            entity=_coerce_chat(params.chat),
            message_ids=params.message_ids,
            revoke=params.revoke,
        )
    deleted = sum(getattr(a, "pts_count", 0) for a in affected)
    return {"deleted": deleted, "requested": len(params.message_ids)}


_register(
    Tool(
        name="delete_messages",
        description="Delete messages by ID.",
        params_model=DeleteMessagesParams,
        handler=_delete_messages,
    )
)


# ---------------------------------------------------------------------------
# edit_message
# ---------------------------------------------------------------------------


class EditMessageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat: str
    message_id: int
    text: str = Field(..., min_length=1, max_length=4096)
    parse_mode: Optional[str] = None
    link_preview: bool = True


async def _edit_message(
    holder: TelethonHolder, params: EditMessageParams
) -> Dict[str, Any]:
    async with holder.lock:
        msg = await holder.client.edit_message(
            entity=_coerce_chat(params.chat),
            message=params.message_id,
            text=params.text,
            parse_mode=params.parse_mode,
            link_preview=params.link_preview,
        )
    return _message_to_dict(msg)


_register(
    Tool(
        name="edit_message",
        description="Edit a message you sent.",
        params_model=EditMessageParams,
        handler=_edit_message,
    )
)


# ---------------------------------------------------------------------------
# mark_read
# ---------------------------------------------------------------------------


class MarkReadParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat: str
    max_id: int = Field(0, ge=0, description="Mark up to this message ID. 0 = all.")


async def _mark_read(
    holder: TelethonHolder, params: MarkReadParams
) -> Dict[str, Any]:
    async with holder.lock:
        ok = await holder.client.send_read_acknowledge(
            entity=_coerce_chat(params.chat),
            max_id=params.max_id,
        )
    return {"ok": bool(ok)}


_register(
    Tool(
        name="mark_read",
        description="Mark messages in a chat as read.",
        params_model=MarkReadParams,
        handler=_mark_read,
    )
)


# ---------------------------------------------------------------------------
# send_file
# ---------------------------------------------------------------------------


class SendFileParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat: str
    file_url: str = Field(
        ...,
        description="HTTPS URL of the file to download and forward to Telegram.",
    )
    caption: Optional[str] = None
    parse_mode: Optional[str] = None
    silent: bool = False
    force_document: bool = False
    max_bytes: int = Field(50 * 1024 * 1024, ge=1, le=2 * 1024 * 1024 * 1024)


async def _send_file(
    holder: TelethonHolder, params: SendFileParams
) -> Dict[str, Any]:
    if not params.file_url.startswith(("http://", "https://")):
        raise ValueError("file_url must be http(s)")

    os.makedirs("/tmp/telethon-plus", exist_ok=True)
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        async with http.stream("GET", params.file_url) as resp:
            resp.raise_for_status()
            length = int(resp.headers.get("content-length") or 0)
            if length and length > params.max_bytes:
                raise ValueError(
                    f"file too large: {length} > {params.max_bytes}"
                )

            tmp_path = f"/tmp/telethon-plus/upload-{os.getpid()}-{id(resp)}"
            written = 0
            with open(tmp_path, "wb") as fh:
                async for chunk in resp.aiter_bytes(1 << 16):
                    written += len(chunk)
                    if written > params.max_bytes:
                        os.unlink(tmp_path)
                        raise ValueError(
                            f"file too large: exceeded {params.max_bytes}"
                        )
                    fh.write(chunk)

    try:
        async with holder.lock:
            msg = await holder.client.send_file(
                entity=_coerce_chat(params.chat),
                file=tmp_path,
                caption=params.caption,
                parse_mode=params.parse_mode,
                silent=params.silent,
                force_document=params.force_document,
            )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return _message_to_dict(msg)


_register(
    Tool(
        name="send_file",
        description=(
            "Download a file from an HTTP(S) URL and send it to a chat. "
            "Use force_document=true to send as a generic file instead of "
            "letting Telegram pick a media type."
        ),
        params_model=SendFileParams,
        handler=_send_file,
    )
)


# ---------------------------------------------------------------------------
# get_participants
# ---------------------------------------------------------------------------


class GetParticipantsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat: str
    limit: int = Field(100, ge=1, le=1000)
    search: Optional[str] = None


async def _get_participants(
    holder: TelethonHolder, params: GetParticipantsParams
) -> List[Dict[str, Any]]:
    async with holder.lock:
        participants = await holder.client.get_participants(
            _coerce_chat(params.chat),
            limit=params.limit,
            search=params.search or "",
        )
    return [_entity_to_dict(p) for p in participants]


_register(
    Tool(
        name="get_participants",
        description="List members of a group or channel.",
        params_model=GetParticipantsParams,
        handler=_get_participants,
    )
)


# ---------------------------------------------------------------------------
# create_group
# ---------------------------------------------------------------------------


class CreateGroupParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(..., min_length=1, max_length=255)
    megagroup: bool = Field(True, description="True = supergroup, False = broadcast channel.")


async def _create_group(
    holder: TelethonHolder, params: CreateGroupParams
) -> Dict[str, Any]:
    async with holder.lock:
        result = await holder.client(
            CreateChannelRequest(
                title=params.title,
                about="",
                megagroup=params.megagroup,
            )
        )
    return _entity_to_dict(result.chats[0])


_register(
    Tool(
        name="create_group",
        description="Create a new supergroup or broadcast channel.",
        params_model=CreateGroupParams,
        handler=_create_group,
    )
)


# ---------------------------------------------------------------------------
# delete_chat
# ---------------------------------------------------------------------------


class DeleteChatParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat: str


async def _delete_chat(
    holder: TelethonHolder, params: DeleteChatParams
) -> Dict[str, Any]:
    async with holder.lock:
        entity = await holder.client.get_entity(_coerce_chat(params.chat))
        await holder.client(DeleteChannelRequest(channel=entity))
    return {"ok": True}


_register(
    Tool(
        name="delete_chat",
        description="Delete a supergroup or channel you own.",
        params_model=DeleteChatParams,
        handler=_delete_chat,
    )
)


# ---------------------------------------------------------------------------
# join_chat
# ---------------------------------------------------------------------------


class JoinChatParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat: str


async def _join_chat(
    holder: TelethonHolder, params: JoinChatParams
) -> Dict[str, Any]:
    async with holder.lock:
        entity = await holder.client.get_entity(_coerce_chat(params.chat))
        await holder.client(JoinChannelRequest(channel=entity))
    return {"ok": True}


_register(
    Tool(
        name="join_chat",
        description="Join a public channel or supergroup.",
        params_model=JoinChatParams,
        handler=_join_chat,
    )
)


# ---------------------------------------------------------------------------
# leave_chat
# ---------------------------------------------------------------------------


class LeaveChatParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat: str


async def _leave_chat(
    holder: TelethonHolder, params: LeaveChatParams
) -> Dict[str, Any]:
    async with holder.lock:
        entity = await holder.client.get_entity(_coerce_chat(params.chat))
        await holder.client(LeaveChannelRequest(channel=entity))
    return {"ok": True}


_register(
    Tool(
        name="leave_chat",
        description="Leave a channel or supergroup.",
        params_model=LeaveChatParams,
        handler=_leave_chat,
    )
)
