# docker-telethon-plus

[![Docker Hub](https://img.shields.io/docker/pulls/psyb0t/telethon-plus?style=flat-square)](https://hub.docker.com/r/psyb0t/telethon-plus)
[![License: WTFPL](https://img.shields.io/badge/License-WTFPL-brightgreen.svg?style=flat-square)](http://www.wtfpl.net/)

Your Telegram account, but it takes HTTP requests. Wraps [Telethon](https://codeberg.org/Lonami/Telethon) — the real MTProto userbot client, not that neutered Bot API garbage — behind a JSON HTTP API and a Model Context Protocol endpoint.

Same tools, two doors. POST some JSON, or point your AI agent at `/mcp` and let it go nuts. Either way it's talking to Telegram as *you*, with full account access.

One login. One session string. Never type a code again.

## Table of Contents

- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [First-time login](#first-time-login)
- [Configuration](#configuration)
- [Tools](#tools)
- [HTTP API](#http-api)
- [MCP](#mcp)
- [Development](#development)
- [Tests](#tests)
- [License](#license)

## How it works

```
+-------------------+        +-----------------------+
|  Any HTTP client  | -----> |  REST  /api/...       | --+
+-------------------+        +-----------------------+   |
                                                         |   +-----------+        Telegram
+-------------------+        +-----------------------+   +-> |  Telethon | <----> Servers
|  MCP-aware agent  | -----> |  /mcp  (Streamable    | --+   +-----------+       (MTProto)
|  (Claude, etc.)   |        |   HTTP transport)     |
+-------------------+        +-----------------------+
```

One Telethon client. One async lock. Both surfaces share the same tool registry — no duplication, no weird state, no bullshit.

## Quick start

```yaml
services:
  telethon-plus:
    image: psyb0t/telethon-plus
    ports:
      - "8080:8080"
    environment:
      TELETHON_API_ID: "123456"
      TELETHON_API_HASH: "your-api-hash"
      TELETHON_SESSION: "1Aa...long-string-from-login-helper..."
    restart: unless-stopped
```

Get `API_ID` / `API_HASH` from <https://my.telegram.org/apps>. Get the session string from the [login helper](#first-time-login) below.

## First-time login

Telegram makes you prove you're a human once — phone number, SMS code, optionally 2FA. Do it once, never again.

```bash
cp .env.example .env
$EDITOR .env  # put in TELETHON_API_ID and TELETHON_API_HASH

make login
```

`make login` builds the image, runs the interactive flow, and shoves `TELETHON_SESSION` straight into your `.env`. That's it. Run `make run` and you're live.

No repo? No problem:

```bash
docker run --rm -it \
  -e TELETHON_API_ID=123456 \
  -e TELETHON_API_HASH=your-api-hash \
  psyb0t/telethon-plus login
```

Copy the session string it spits out, set it as `TELETHON_SESSION`, done.

> **The session string is full account access.** Whoever has it is you. Don't commit it, don't paste it in Slack, don't tattoo it anywhere.

## Configuration

All config via environment variables. Copy `.env.example` to get the full list with comments.

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELETHON_API_ID` | yes | — | API ID from my.telegram.org |
| `TELETHON_API_HASH` | yes | — | API hash from my.telegram.org |
| `TELETHON_SESSION` | yes | — | StringSession from the login helper |
| `TELETHON_HTTP_LISTEN_ADDRESS` | no | `0.0.0.0:8080` | `host:port` to bind |
| `TELETHON_LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `TELETHON_REQUEST_TIMEOUT` | no | `60` | Per-request timeout in seconds |
| `TELETHON_FLOOD_SLEEP_THRESHOLD` | no | `60` | Auto-sleep through `FLOOD_WAIT` errors below this many seconds. Telegram will rate-limit you — this is the safety valve. |
| `TELETHON_DEVICE_MODEL` | no | `docker-telethon-plus` | What Telegram thinks your device is |
| `TELETHON_SYSTEM_VERSION` | no | `1.0` | Ditto for OS |
| `TELETHON_APP_VERSION` | no | `1.0` | Ditto for app |
| `TELETHON_DOWNLOAD_DIR` | no | `/tmp/telethon-plus` | Scratch space for `send_file` uploads |
| `TELETHON_AUTH_KEY` | no | `""` | When set, all endpoints require `Authorization: Bearer <key>`. `/healthz` stays public. Empty = no auth. |

## Tools

JSON in, JSON out. All inputs are pydantic-validated — send garbage, get a `400` back with exactly what's wrong.

Chat references (`chat`, `from_chat`, `to_chat`) accept whatever Telethon accepts:

| Format | Example |
|---|---|
| Username | `@psyb0t` |
| Phone number | `+1234567890` |
| t.me link | `https://t.me/psyb0t` |
| Numeric ID | `123456789` |
| Supergroup/channel ID | `-1001234567890` |
| Your own Saved Messages | `me` |

> **Numeric IDs only resolve for entities Telethon has already seen** — i.e. cached in your session via a prior `@username` / `t.me` lookup, dialog list, or incoming message. MTProto needs an `access_hash`, not just an ID, and bare numbers don't carry one. Especially relevant for bots: pass `@botusername` first (or call `GET /api/dialogs` / `GET /api/entities?chat=@bot` once) before referring to it by numeric ID. If you only have the bot's token and no username, hit Telegram's Bot API `getMe` to fetch the username, then use that.

### Quick reference

| Endpoint | Required params | What it does |
|---|---|---|
| `GET /api/me` | — | Who the fuck am I — returns your account profile. |
| `GET /api/entities` | `chat` | Resolve a username/ID/link to a full profile. |
| `POST /api/messages` | `chat`, `text` | Send a text message. Supports `parse_mode` (`md`/`html`), `reply_to`, `silent`, `link_preview`. |
| `GET /api/messages` | `chat` | Read recent messages. Optional: `limit` (default 20, max 200), `offset_id`, `search`. |
| `GET /api/dialogs` | — | List your chats, groups, and channels. Optional: `limit`, `archived`. |
| `POST /api/messages/forward` | `from_chat`, `to_chat`, `message_ids` | Forward one or more messages between chats. |
| `DELETE /api/messages` | `chat`, `message_ids` | Nuke messages by ID. `revoke: true` (default) deletes for everyone. |
| `PATCH /api/messages/{id}` | `chat`, `text` | Fix your typos after the fact. |
| `POST /api/messages/read` | `chat` | Mark messages as read. Optional: `max_id` (default 0 = all). |
| `POST /api/files` | `chat`, `file_url` | Download a file from an HTTPS URL and send it. Optional: `caption`, `parse_mode`, `silent`, `force_document`, `max_bytes`. |
| `GET /api/participants` | `chat` | List members of a group or channel. Optional: `limit` (default 100, max 1000), `search`. |
| `POST /api/chats` | `title` | Create a supergroup or broadcast channel. Optional: `megagroup` (default true). |
| `DELETE /api/chats` | `chat` | Delete a supergroup or channel you own. |
| `POST /api/chats/join` | `chat` | Join a public channel or supergroup. |
| `POST /api/chats/leave` | `chat` | Leave a channel or supergroup. |

## HTTP API

Standard REST API. JSON in, JSON out. Every response is `{"result": ...}` on success.

If `TELETHON_AUTH_KEY` is set, every request (except `/healthz`) needs:

```http
Authorization: Bearer your-secret-key
```

### GET /api/me

Who am I right now.

```http
GET /api/me
```

```json
{
  "result": {
    "id": 123456789,
    "type": "User",
    "username": "psyb0t",
    "first_name": "Ciprian",
    "phone": "+40..."
  }
}
```

### GET /api/entities

Resolve any chat reference to a full profile.

```http
GET /api/entities?chat=@telegram
```

```json
{
  "result": {
    "id": 1234567,
    "type": "Channel",
    "username": "telegram",
    "title": "Telegram"
  }
}
```

### GET /api/dialogs

```http
GET /api/dialogs?limit=10&archived=false
```

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 20 | How many dialogs (1–200) |
| `archived` | bool | false | Include archived chats |

```json
{
  "result": [
    {
      "id": 123456789,
      "type": "User",
      "username": "someone",
      "first_name": "Some",
      "last_name": "One",
      "unread_count": 3,
      "pinned": true,
      "last_message": {
        "id": 999,
        "date": "2026-04-29T11:00:00+00:00",
        "chat_id": 123456789,
        "sender_id": 123456789,
        "text": "hey",
        "out": false,
        "reply_to_msg_id": null,
        "media": false,
        "media_type": null
      }
    }
  ]
}
```

### GET /api/messages

```http
GET /api/messages?chat=me&limit=5&search=hello
```

| Param | Type | Default | Description |
|---|---|---|---|
| `chat` | string | required | Chat to read from |
| `limit` | int | 20 | How many messages (1–200) |
| `offset_id` | int | 0 | Start from this message ID (pagination) |
| `search` | string | — | Full-text search filter |

```json
{
  "result": [
    {
      "id": 4242,
      "date": "2026-04-29T12:00:00+00:00",
      "chat_id": 12345,
      "sender_id": 67890,
      "text": "hello",
      "out": false,
      "reply_to_msg_id": null,
      "media": false,
      "media_type": null
    }
  ]
}
```

Newest first. Returns `[]` if nothing matches.

### POST /api/messages

Send a message.

```http
POST /api/messages
Content-Type: application/json

{
  "chat": "@psyb0t",
  "text": "**hello** from a container",
  "parse_mode": "md",
  "silent": true,
  "reply_to": 4241
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `chat` | string | required | Target chat |
| `text` | string | required | Message text (1–4096 chars) |
| `parse_mode` | string | null | `md` / `markdown` / `html` / null |
| `reply_to` | int | null | Message ID to reply to |
| `silent` | bool | false | Send without notification |
| `link_preview` | bool | true | Show link previews |

```json
{
  "result": {
    "id": 4242,
    "date": "2026-04-29T12:00:00+00:00",
    "chat_id": 12345,
    "sender_id": 67890,
    "text": "hello from a container",
    "out": true,
    "reply_to_msg_id": 4241,
    "media": false,
    "media_type": null
  }
}
```

### PATCH /api/messages/{id}

Edit a message. Message ID goes in the URL, everything else in the body.

```http
PATCH /api/messages/4242
Content-Type: application/json

{
  "chat": "me",
  "text": "fixed version",
  "parse_mode": "md"
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `chat` | string | required | Chat containing the message |
| `text` | string | required | New text (1–4096 chars) |
| `parse_mode` | string | null | `md` / `html` / null |
| `link_preview` | bool | true | Show link previews |

```json
{
  "result": {
    "id": 4242,
    "date": "2026-04-29T12:00:00+00:00",
    "chat_id": 99999,
    "sender_id": 123456789,
    "text": "fixed version",
    "out": true,
    "reply_to_msg_id": null,
    "media": false,
    "media_type": null
  }
}
```

### DELETE /api/messages

Delete messages by ID.

```http
DELETE /api/messages
Content-Type: application/json

{
  "chat": "@psyb0t",
  "message_ids": [4242, 4243],
  "revoke": true
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `chat` | string | required | Chat containing the messages |
| `message_ids` | list[int] | required | IDs to delete (max 100) |
| `revoke` | bool | true | Delete for everyone, not just yourself |

```json
{ "result": { "deleted": 2, "requested": 2 } }
```

### POST /api/messages/forward

```http
POST /api/messages/forward
Content-Type: application/json

{
  "from_chat": "@sourcechannel",
  "to_chat": "me",
  "message_ids": [101, 102, 103],
  "silent": true
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `from_chat` | string | required | Source chat |
| `to_chat` | string | required | Destination chat |
| `message_ids` | list[int] | required | IDs to forward (max 100) |
| `silent` | bool | false | Forward without notification |

```json
{
  "result": [
    {
      "id": 5001,
      "date": "2026-04-29T12:01:00+00:00",
      "chat_id": 99999,
      "sender_id": 123456789,
      "text": "forwarded content here",
      "out": true,
      "reply_to_msg_id": null,
      "media": false,
      "media_type": null
    }
  ]
}
```

### POST /api/messages/read

Mark messages as read.

```http
POST /api/messages/read
Content-Type: application/json

{ "chat": "@psyb0t", "max_id": 0 }
```

| Field | Type | Default | Description |
|---|---|---|---|
| `chat` | string | required | Chat to mark as read |
| `max_id` | int | 0 | Mark up to this message ID. `0` = mark all. |

```json
{ "result": { "ok": true } }
```

### POST /api/files

Download a file from an HTTPS URL and send it to a chat. Never touches your disk — goes through the container's scratch dir (`TELETHON_DOWNLOAD_DIR`) and gets cleaned up immediately.

```http
POST /api/files
Content-Type: application/json

{
  "chat": "@psyb0t",
  "file_url": "https://example.com/photo.jpg",
  "caption": "look at this shit",
  "silent": true
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `chat` | string | required | Target chat |
| `file_url` | string | required | HTTPS URL of the file to fetch and send |
| `caption` | string | null | Caption text |
| `parse_mode` | string | null | `md` / `html` / null |
| `silent` | bool | false | Send without notification |
| `force_document` | bool | false | Send as a generic file instead of letting Telegram pick media type |
| `max_bytes` | int | 52428800 | Reject files larger than this (default 50 MB, max 2 GB) |

Telegram auto-detects media type from the file extension and MIME type. A `.jpg` becomes a photo, `.mp4` becomes a video, `.mp3` becomes audio. Use `force_document: true` to override.

```json
{
  "result": {
    "id": 4243,
    "date": "2026-04-29T12:02:00+00:00",
    "chat_id": 12345,
    "sender_id": 67890,
    "text": "look at this shit",
    "out": true,
    "reply_to_msg_id": null,
    "media": true,
    "media_type": "MessageMediaPhoto"
  }
}
```

### GET /api/participants

List members of a group or channel.

```http
GET /api/participants?chat=-1001234567890&limit=50&search=john
```

| Param | Type | Default | Description |
|---|---|---|---|
| `chat` | string | required | Group or channel |
| `limit` | int | 100 | Max members to return (1–1000) |
| `search` | string | — | Filter by name |

```json
{
  "result": [
    { "id": 123456789, "type": "User", "username": "johndoe", "first_name": "John" }
  ]
}
```

Large public channels may return a limited set or require admin rights.

### POST /api/chats

Create a supergroup or broadcast channel.

```http
POST /api/chats
Content-Type: application/json

{ "title": "my-group", "megagroup": true }
```

| Field | Type | Default | Description |
|---|---|---|---|
| `title` | string | required | Group name (1–255 chars) |
| `megagroup` | bool | true | `true` = supergroup, `false` = broadcast channel |

```json
{
  "result": { "id": 1234567890, "type": "Channel", "title": "my-group" }
}
```

### DELETE /api/chats

Delete a supergroup or channel you own. **Irreversible.**

```http
DELETE /api/chats
Content-Type: application/json

{ "chat": "-1001234567890" }
```

```json
{ "result": { "ok": true } }
```

### POST /api/chats/join

Join a public channel or supergroup.

```http
POST /api/chats/join
Content-Type: application/json

{ "chat": "@somegroup" }
```

```json
{ "result": { "ok": true } }
```

### POST /api/chats/leave

Leave a channel or supergroup.

```http
POST /api/chats/leave
Content-Type: application/json

{ "chat": "@somegroup" }
```

```json
{ "result": { "ok": true } }
```

### Errors

| Status | When |
|---|---|
| `400` | Bad JSON, validation failure, or Telethon said the input is nonsense. Body has details. |
| `401` | Missing or wrong Bearer token (only when `TELETHON_AUTH_KEY` is set). |
| `404` | Unknown endpoint. |
| `502` | Telegram threw an RPC error (`FloodWaitError`, `ChatWriteForbiddenError`, etc.). Body has the error class and message. |

### Health

```http
GET /healthz
```

```json
{ "status": "ok", "authorized": true }
```

`authorized: false` means the container started but the session is fucked — bad string, revoked, or Telegram unreachable. Always public, no auth required.

## MCP

Mounted at `/mcp/` using the [streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports#streamable-http). Every tool from the table above shows up automatically as an MCP tool with the same name and schema.

Point your agent at:

```
http://your-host:8080/mcp/
```

Stateless — every request is independent, no session juggling. Drop it into Claude Desktop, a custom agent, anything that speaks MCP over HTTP. Works out of the box.

## Development

```bash
make build        # build psyb0t/telethon-plus:latest
make build-test   # build psyb0t/telethon-plus:latest-test
make run          # run locally on :8080 (reads .env)
make login        # interactive login — writes TELETHON_SESSION to .env automatically
make lint         # flake8 + pyright
make format       # isort + black
make test         # run integration tests in Docker
make clean        # remove built images
```

## Tests

Real tests. Real Telegram. No mocking bullshit.

`tests/` spins up the container and hammers both REST and MCP with your actual account. Messages get sent and deleted. If anything breaks, you'll know.

Setup:

```bash
cp .env.example .env
$EDITOR .env  # needs TELETHON_API_ID, TELETHON_API_HASH, TELETHON_SESSION, TEST_CHAT

make test
```

`TEST_CHAT` is where test messages land. Use `me` for Saved Messages — private, yours, no one else sees it. All chat reference formats from the [Tools](#tools) section work here.

`make test` builds both images and runs pytest inside Docker with the socket mounted. No setup beyond `.env`. If credentials are missing, the suite skips cleanly.

| Test file | What it beats on |
|---|---|
| `test_health.py` | Container boots, auth succeeds, OpenAPI spec has all the routes. |
| `test_rest.py` | Validation errors, extra fields rejected, send → edit → fetch → delete roundtrip, dialogs, entity resolution, public channel read, group create/delete, participants. |
| `test_mcp.py` | MCP streamable HTTP: tool discovery, `get_me`, send + delete roundtrip, validation errors come back as `isError`. |
| `test_auth.py` | Auth middleware: 401 on missing/wrong token, 200 on correct token, `/healthz` always public, MCP endpoint protected too. |

## License

[WTFPL](LICENSE) — do whatever the fuck you want.
