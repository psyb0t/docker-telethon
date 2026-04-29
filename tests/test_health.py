"""Container boots, /healthz reports authorized."""

from __future__ import annotations

import httpx


def test_healthz_ok(http: httpx.Client) -> None:
    resp = http.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["authorized"] is True


def test_openapi_present(http: httpx.Client) -> None:
    resp = http.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    paths = spec.get("paths", {})
    assert "/api/me" in paths
    assert "/api/messages" in paths
    assert "/api/dialogs" in paths
    assert "/healthz" in paths
