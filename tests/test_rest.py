"""REST tool surface."""

from __future__ import annotations

import httpx


EXPECTED_TOOLS = {
    "get_me",
    "get_entity",
    "send_message",
    "get_messages",
    "get_dialogs",
    "forward_messages",
    "delete_messages",
    "edit_message",
    "mark_read",
    "send_file",
}


def test_list_tools(http: httpx.Client) -> None:
    resp = http.get("/api/tools")
    assert resp.status_code == 200
    tools = resp.json()["tools"]
    names = {t["name"] for t in tools}
    assert names == EXPECTED_TOOLS

    for tool in tools:
        assert tool["description"]
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema


def test_unknown_tool(http: httpx.Client) -> None:
    resp = http.post("/api/tools/does_not_exist", json={})
    assert resp.status_code == 404


def test_validation_error(http: httpx.Client) -> None:
    resp = http.post("/api/tools/send_message", json={"chat": "me"})
    assert resp.status_code == 400
    body = resp.json()
    assert "detail" in body


def test_extra_fields_rejected(http: httpx.Client) -> None:
    resp = http.post(
        "/api/tools/get_me",
        json={"surprise": "field"},
    )
    assert resp.status_code == 400


def test_invalid_json_body(http: httpx.Client) -> None:
    resp = http.post(
        "/api/tools/get_me",
        content=b"{not json",
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 400


def test_get_me(http: httpx.Client) -> None:
    resp = http.post("/api/tools/get_me", json={})
    assert resp.status_code == 200
    me = resp.json()["result"]
    assert isinstance(me["id"], int)
    assert me["type"]


def test_send_and_read_roundtrip(http: httpx.Client, env: dict[str, str]) -> None:
    chat = env["TEST_CHAT"]
    marker = f"docker-telethon-test-{httpx.__name__}-roundtrip"

    sent = http.post(
        "/api/tools/send_message",
        json={"chat": chat, "text": marker, "silent": True},
    )
    assert sent.status_code == 200, sent.text
    sent_msg = sent.json()["result"]
    msg_id = sent_msg["id"]
    assert sent_msg["text"] == marker
    assert sent_msg["out"] is True

    edit = http.post(
        "/api/tools/edit_message",
        json={"chat": chat, "message_id": msg_id, "text": marker + " (edited)"},
    )
    assert edit.status_code == 200, edit.text
    assert edit.json()["result"]["text"].endswith("(edited)")

    fetched = http.post(
        "/api/tools/get_messages",
        json={"chat": chat, "limit": 10},
    )
    assert fetched.status_code == 200, fetched.text
    msgs = fetched.json()["result"]
    assert any(m["id"] == msg_id for m in msgs)

    deleted = http.post(
        "/api/tools/delete_messages",
        json={"chat": chat, "message_ids": [msg_id]},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["result"]["requested"] == 1


def test_get_dialogs(http: httpx.Client) -> None:
    resp = http.post("/api/tools/get_dialogs", json={"limit": 5})
    assert resp.status_code == 200, resp.text
    dialogs = resp.json()["result"]
    assert isinstance(dialogs, list)
    if dialogs:
        assert "id" in dialogs[0]
        assert "type" in dialogs[0]


def test_get_entity_self(http: httpx.Client, env: dict[str, str]) -> None:
    resp = http.post("/api/tools/get_entity", json={"chat": env["TEST_CHAT"]})
    assert resp.status_code == 200, resp.text
    entity = resp.json()["result"]
    assert "id" in entity


def test_get_entity_unknown_username(http: httpx.Client) -> None:
    resp = http.post(
        "/api/tools/get_entity",
        json={"chat": "@this_username_should_not_exist_xyzzy_42"},
    )
    assert resp.status_code in (400, 502)
