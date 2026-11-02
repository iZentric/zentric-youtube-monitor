"""Teste pentru face_reactions.py: motorul de reguli și protocolul VTS."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager

import pytest
from websockets.sync.client import connect
from websockets.sync.server import serve

import face_reactions
import vts

RULES = [{
    "name": "happy",
    "expressionFile": "happy.exp3.json",
    "when": {"MouthSmile": {"min": 0.5}},
    "holdSeconds": 1.0,
    "cooldownSeconds": 2.0,
}]

RESPONSES = {
    "AuthenticationTokenRequest": "AuthenticationTokenResponse",
    "AuthenticationRequest": "AuthenticationResponse",
    "ExpressionStateRequest": "ExpressionStateResponse",
    "InputParameterListRequest": "InputParameterListResponse",
    "ExpressionActivationRequest": "ExpressionActivationResponse",
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
def vts_server(values: list[dict]):
    """Server VTS fals; servește pe rând valorile de tracking primite."""
    received: list[dict] = []
    pending = list(values)

    def handler(conn) -> None:
        for raw in conn:
            request = json.loads(raw)
            received.append(request)
            kind = request["messageType"]
            if kind == "ExpressionStateRequest":
                conn.send(json.dumps(reply(request, {"expressions": [{"name": "Happy", "file": "happy.exp3.json"}]})))
            elif kind == "InputParameterListRequest":
                current = pending.pop(0) if pending else {}
                params = [{"name": name, "value": value} for name, value in current.items()]
                conn.send(json.dumps(reply(request, {"defaultParameters": params, "customParameters": []})))
            else:
                conn.send(json.dumps(reply(request, {"authenticationToken": "tok-1", "authenticated": True})))

    server = serve(handler, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.socket.getsockname()[1], received
    finally:
        server.shutdown()


def test_matches_checks_all_bounds():
    rule = {"MouthOpen": {"min": 0.6}, "Brows": {"max": 0.4}}
    assert face_reactions.matches(rule, {"MouthOpen": 0.7, "Brows": 0.1})
    assert not face_reactions.matches(rule, {"MouthOpen": 0.7, "Brows": 0.9})
    assert not face_reactions.matches(rule, {"MouthOpen": 0.5})


def test_step_activates_once_then_holds_then_cools_down():
    state: dict = {}
    smile = {"MouthSmile": 0.9}

    assert face_reactions.step(RULES, smile, state, now=0.0) == [("happy.exp3.json", True)]
    # ține expresia cât timp e în hold, fără activări repetate
    assert face_reactions.step(RULES, smile, state, now=0.5) == []
    assert face_reactions.step(RULES, smile, state, now=1.0) == [("happy.exp3.json", False)]
    # cooldown activ: fața zâmbește în continuare, dar nu repornim
    assert face_reactions.step(RULES, smile, state, now=2.5) == []
    assert face_reactions.step(RULES, smile, state, now=3.0) == [("happy.exp3.json", True)]


def test_step_neutral_face_does_nothing():
    assert face_reactions.step(RULES, {"MouthSmile": 0.1}, {}, now=0.0) == []


def test_run_sends_expression_activation(monkeypatch, tmp_path):
    monkeypatch.setattr(vts, "TOKEN", tmp_path / "token.json")
    monkeypatch.setattr(face_reactions, "sleep", lambda seconds: None)

    with vts_server([{"MouthSmile": 0.9}]) as (port, received):
        with connect(f"ws://127.0.0.1:{port}") as ws:
            vts.authenticate(ws)
            face_reactions.run(ws, RULES, iterations=2)

    activations = [request["data"] for request in received if request["messageType"] == "ExpressionActivationRequest"]
    # a doua intrare e curățenia de la ieșire: expresia rămasă pornită e oprită
    assert activations == [
        {"expressionFile": "happy.exp3.json", "active": True, "fadeTime": 0.3},
        {"expressionFile": "happy.exp3.json", "active": False, "fadeTime": 0.1},
    ]


def test_available_expressions_reads_model_expressions(monkeypatch, tmp_path):
    monkeypatch.setattr(vts, "TOKEN", tmp_path / "token.json")

    with vts_server([]) as (port, _):
        with connect(f"ws://127.0.0.1:{port}") as ws:
            vts.authenticate(ws)
            assert face_reactions.available_expressions(ws) == {"happy.exp3.json": "Happy"}
