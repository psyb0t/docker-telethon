# telethon

[![Docker Hub](https://img.shields.io/docker/pulls/psyb0t/telethon?style=flat-square)](https://hub.docker.com/r/psyb0t/telethon)
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
|  Any HTTP client  | -----> |  POST /api/tools/...  | --+
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
  telethon:
    image: psyb0t/telethon
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
  psyb0t/telethon login
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
| `TELETHON_DEVICE_MODEL` | no | `docker-telethon` | What Telegram thinks your device is |
| `TELETHON_SYSTEM_VERSION` | no | `1.0` | Ditto for OS |
| `TELETHON_APP_VERSION` | no | `1.0` | Ditto for app |
| `TELETHON_DOWNLOAD_DIR` | no | `/tmp/telethon` | Scratch space for `send_file` uploads |

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

### Tool reference

| Tool | Required params | What it does |
|---|---|---|
| `get_me` | — | Who the fuck am I — returns your account profile. |
| `get_entity` | `chat` | Resolve a username/ID/link to a full profile. |
| `send_message` | `chat`, `text` | Send a text message. Supports `parse_mode` (`md`/`html`), `reply_to`, `silent`, `link_preview`. |
| `get_messages` | `chat` | Read recent messages. Optional: `limit` (default 20, max 200), `offset_id`, `search`. |
| `get_dialogs` | — | List your chats, groups, and channels. Optional: `limit`, `archived`. |
| `forward_messages` | `from_chat`, `to_chat`, `message_ids` | Forward one or more messages between chats. |
| `delete_messages` | `chat`, `message_ids` | Nuke messages by ID. `revoke: true` (default) deletes for everyone. |
| `edit_message` | `chat`, `message_id`, `text` | Fix your typos after the fact. |
| `mark_read` | `chat` | Mark messages as read. Optional: `max_id` (default 0 = all). |
| `send_file` | `chat`, `file_url` | Download a file from an HTTPS URL and send it. Optional: `caption`, `parse_mode`, `silent`, `force_document`, `max_bytes`. |

Hit `GET /api/tools` for the full JSON Schema of every tool — every field, type, default, and constraint, live from the running server.

## HTTP API

### List tools

```http
GET /api/tools
```

```json
{
  "tools": [
    {
      "name": "send_message",
      "description": "Send a text message to a chat.",
      "input_schema": { "type": "object", "properties": { "..." : "..." } }
    }
  ]
}
```

### Call a tool

```http
POST /api/tools/send_message
Content-Type: application/json

{
  "chat": "@psyb0t",
  "text": "hello from a container",
  "parse_mode": "md",
  "silent": true
}
```

```json
{
  "result": {
    "id": 4242,
    "date": "2026-04-29T12:00:00+00:00",
    "chat_id": 12345,
    "sender_id": 67890,
    "text": "hello from a container",
    "out": true,
    "reply_to_msg_id": null,
    "media": false,
    "media_type": null
  }
}
```

### Errors

| Status | When |
|---|---|
| `400` | Bad JSON, validation failure, or Telethon said the input is nonsense. Body has details. |
| `404` | You called a tool that doesn't exist. |
| `502` | Telegram threw an RPC error (`FloodWaitError`, `ChatWriteForbiddenError`, etc.). Body has the error class and message. |

### Health

```http
GET /healthz
```

```json
{ "status": "ok", "authorized": true }
```

`authorized: false` means the container started but the session is fucked — bad string, revoked, or Telegram unreachable.

## MCP

Mounted at `/mcp/` using the [streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports#streamable-http). Every tool from the table above shows up automatically as an MCP tool with the same name and schema.

Point your agent at:

```
http://your-host:8080/mcp/
```

Stateless — every request is independent, no session juggling. Drop it into Claude Desktop, a custom agent, anything that speaks MCP over HTTP. Works out of the box.

## Development

```bash
make build        # build psyb0t/telethon:latest
make build-test   # build psyb0t/telethon:latest-test
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
| `test_rest.py` | Tool listing, validation errors, unknown tool 404, full send → edit → fetch → delete roundtrip, dialogs, entity resolution. |
| `test_mcp.py` | MCP streamable HTTP: tool discovery, `get_me`, send + delete roundtrip, validation errors come back as `isError`. |

## License

[WTFPL](LICENSE) — do whatever the fuck you want.
