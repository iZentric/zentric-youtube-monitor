"""Teste pentru vts_bridge.py, rulate contra unui server VTube Studio fals."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest
from websockets.sync.server import serve

import vts_bridge

RESPONSES = {
    "AuthenticationTokenRequest": "AuthenticationTokenResponse",
    "AuthenticationRequest": "AuthenticationResponse",
    "HotkeyTriggerRequest": "HotkeyTriggerResponse",
}


def reply(request: dict, data: dict) -> dict:
    return {
        "apiName": "VTubeStudioPublicAPI",
        "apiVersion": "1.0",
        "requestID": request["requestID"],
        "messageType": RESPONSES[request["messageType"]],
        "data": data,
    }


@contextmanager
def vts_server(respond):
    received: list[dict] = []

    def handler(conn) -> None:
        for raw in conn:
            request = json.loads(raw)
            received.append(request)
            conn.send(json.dumps(respond(request)))

    server = serve(handler, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.socket.getsockname()[1], received
    finally:
        server.shutdown()


@pytest.fixture
def bridge(monkeypatch, tmp_path: Path):
    """Bridge cu fișiere în tmp_path și un snapshot cu un clip nedetectat."""
    snapshot = {
        "fetched_at": "2026-11-02T00:00:00+00:00",
        "channels": [
            {"name": "Zentric Minecraft", "latest": [{"video_id": "new1", "title": "Clip nou"}]},
            {"name": "Klorna", "latest": [{"video_id": "old1", "title": "Clip vechi"}]},
        ],
        "errors": [],
    }
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps(snapshot), encoding="utf-8")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"seen": ["old1"]}), encoding="utf-8")
    monkeypatch.setattr(vts_bridge, "LATEST", latest)
    monkeypatch.setattr(vts_bridge, "STATE", state)
    monkeypatch.setattr(vts_bridge, "TOKEN", tmp_path / "token.json")
    return vts_bridge


def test_unseen_videos_filters_seen_ids(bridge):
    snapshot = json.loads(bridge.LATEST.read_text(encoding="utf-8"))
    fresh = bridge.unseen_videos(snapshot, {"old1"})
    assert [video["video_id"] for video in fresh] == ["new1"]


def test_first_run_only_seeds_state(bridge, monkeypatch):
    bridge.STATE.unlink()
    monkeypatch.setattr(bridge, "trigger", pytest.fail)
    assert bridge.main() == 0
    assert json.loads(bridge.STATE.read_text(encoding="utf-8"))["seen"] == ["new1", "old1"]


def test_authenticates_and_triggers_hotkey(bridge, monkeypatch):
    def respond(request):
        kind = request["messageType"]
        if kind == "AuthenticationTokenRequest":
            return reply(request, {"authenticationToken": "tok-1"})
        if kind == "AuthenticationRequest":
            return reply(request, {"authenticated": True})
        return reply(request, {"hotkeyID": request["data"]["hotkeyID"]})

    with vts_server(respond) as (port, received):
        monkeypatch.setattr(bridge, "VTS_URL", f"ws://127.0.0.1:{port}")
        assert bridge.main() == 0

    assert [request["messageType"] for request in received] == [
        "AuthenticationTokenRequest",
        "AuthenticationRequest",
        "HotkeyTriggerRequest",
    ]
    assert received[2]["data"]["hotkeyID"] == bridge.HOTKEY
    assert bridge.TOKEN.read_text(encoding="utf-8") == "tok-1"
    assert json.loads(bridge.STATE.read_text(encoding="utf-8"))["seen"] == ["new1", "old1"]


def test_stale_token_is_replaced_once(bridge, monkeypatch):
    bridge.TOKEN.write_text("expired", encoding="utf-8")

    def respond(request):
        kind = request["messageType"]
        if kind == "AuthenticationTokenRequest":
            return reply(request, {"authenticationToken": "tok-2"})
        if kind == "AuthenticationRequest":
            valid = request["data"]["authenticationToken"] == "tok-2"
            return reply(request, {"authenticated": valid, "reason": "Token not found"} if not valid else {"authenticated": True})
        return reply(request, {"hotkeyID": request["data"]["hotkeyID"]})

    with vts_server(respond) as (port, received):
        monkeypatch.setattr(bridge, "VTS_URL", f"ws://127.0.0.1:{port}")
        assert bridge.main() == 0

    assert [(request["messageType"], request["data"].get("authenticationToken")) for request in received][:3] == [
        ("AuthenticationRequest", "expired"),
        ("AuthenticationTokenRequest", None),
        ("AuthenticationRequest", "tok-2"),
    ]
    assert bridge.TOKEN.read_text(encoding="utf-8") == "tok-2"


def test_vts_error_is_reported_and_state_kept(bridge, monkeypatch):
    def respond(request):
        if request["messageType"] == "HotkeyTriggerRequest":
            return {**reply(request, {}), "errorID": 8, "errorMessage": "Hotkey not found"}
        return reply(request, {"authenticationToken": "tok-1", "authenticated": True})

    with vts_server(respond) as (port, _):
        monkeypatch.setattr(bridge, "VTS_URL", f"ws://127.0.0.1:{port}")
        with pytest.raises(RuntimeError, match="Hotkey not found"):
            bridge.main()

    assert json.loads(bridge.STATE.read_text(encoding="utf-8"))["seen"] == ["old1"]


def test_missing_vts_is_reported(bridge, monkeypatch, capsys):
    monkeypatch.setattr(bridge, "VTS_URL", "ws://127.0.0.1:1")
    assert bridge.main() == 1
    assert "nu mă pot conecta" in capsys.readouterr().out
    assert json.loads(bridge.STATE.read_text(encoding="utf-8"))["seen"] == ["old1"]
