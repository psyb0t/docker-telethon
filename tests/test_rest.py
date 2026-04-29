"""REST API surface."""

from __future__ import annotations

import httpx


def test_unknown_route(http: httpx.Client) -> None:
    resp = http.get("/api/nonexistent")
    assert resp.status_code == 404


def test_validation_error(http: httpx.Client) -> None:
    resp = http.post("/api/messages", json={"chat": "me"})
    assert resp.status_code == 400
    assert "detail" in resp.json()


def test_extra_fields_rejected(http: httpx.Client) -> None:
    resp = http.post("/api/messages", json={"chat": "me", "text": "hi", "surprise": "field"})
    assert resp.status_code == 400


def test_invalid_json_body(http: httpx.Client) -> None:
    resp = http.post(
        "/api/messages",
        content=b"{not json",
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 400


def test_get_me(http: httpx.Client) -> None:
    resp = http.get("/api/me")
    assert resp.status_code == 200
    me = resp.json()["result"]
    assert isinstance(me["id"], int)
    assert me["type"]


def test_send_and_read_roundtrip(http: httpx.Client, env: dict[str, str]) -> None:
    chat = env["TEST_CHAT"]
    marker = f"docker-telethon-test-{httpx.__name__}-roundtrip"

    sent = http.post("/api/messages", json={"chat": chat, "text": marker, "silent": True})
    assert sent.status_code == 200, sent.text
    sent_msg = sent.json()["result"]
    msg_id = sent_msg["id"]
    assert sent_msg["text"] == marker
    assert sent_msg["out"] is True

    edit = http.patch(
        f"/api/messages/{msg_id}",
        json={"chat": chat, "text": marker + " (edited)"},
    )
    assert edit.status_code == 200, edit.text
    assert edit.json()["result"]["text"].endswith("(edited)")

    fetched = http.get("/api/messages", params={"chat": chat, "limit": 10})
    assert fetched.status_code == 200, fetched.text
    msgs = fetched.json()["result"]
    assert any(m["id"] == msg_id for m in msgs)

    deleted = http.request("DELETE", "/api/messages", json={"chat": chat, "message_ids": [msg_id]})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["result"]["requested"] == 1


def test_get_dialogs(http: httpx.Client) -> None:
    resp = http.get("/api/dialogs", params={"limit": 5})
    assert resp.status_code == 200, resp.text
    dialogs = resp.json()["result"]
    assert isinstance(dialogs, list)
    if dialogs:
        assert "id" in dialogs[0]
        assert "type" in dialogs[0]


def test_get_entity_self(http: httpx.Client, env: dict[str, str]) -> None:
    resp = http.get("/api/entities", params={"chat": env["TEST_CHAT"]})
    assert resp.status_code == 200, resp.text
    assert "id" in resp.json()["result"]


def test_get_entity_unknown_username(http: httpx.Client) -> None:
    resp = http.get(
        "/api/entities",
        params={"chat": "@this_username_should_not_exist_xyzzy_42"},
    )
    assert resp.status_code in (400, 502)


def test_read_public_channel(http: httpx.Client) -> None:
    resp = http.get("/api/messages", params={"chat": "@telegram", "limit": 5})
    assert resp.status_code == 200, resp.text
    msgs = resp.json()["result"]
    assert isinstance(msgs, list)
    assert len(msgs) > 0
    msg = msgs[0]
    assert isinstance(msg["id"], int)
    assert msg["chat_id"] is not None


def test_create_and_delete_group(http: httpx.Client) -> None:
    created = http.post("/api/chats", json={"title": "docker-telethon-test-group"})
    assert created.status_code == 200, created.text
    group = created.json()["result"]
    assert group["title"] == "docker-telethon-test-group"
    assert isinstance(group["id"], int)

    chat_id = str(group["id"])
    deleted = http.request("DELETE", "/api/chats", json={"chat": chat_id})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["result"]["ok"] is True


def test_get_participants_of_own_group(http: httpx.Client) -> None:
    created = http.post("/api/chats", json={"title": "docker-telethon-test-participants"})
    assert created.status_code == 200, created.text
    chat_id = str(created.json()["result"]["id"])

    try:
        resp = http.get("/api/participants", params={"chat": chat_id, "limit": 10})
        assert resp.status_code == 200, resp.text
        participants = resp.json()["result"]
        assert isinstance(participants, list)
        assert len(participants) >= 1
        assert all("id" in p for p in participants)
    finally:
        http.request("DELETE", "/api/chats", json={"chat": chat_id})
