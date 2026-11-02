"""Teste pentru doctor.py, rulate contra unui server VTube Studio fals."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager

import pytest
from websockets.sync.server import serve

import doctor
import vts

RESPONSES = {
    "AuthenticationTokenRequest": "AuthenticationTokenResponse",
    "AuthenticationRequest": "AuthenticationResponse",
    "APIStateRequest": "APIStateResponse",
    "CurrentModelRequest": "CurrentModelResponse",
    "FaceFoundRequest": "FaceFoundResponse",
    "InputParameterListRequest": "InputParameterListResponse",
    "ExpressionStateRequest": "ExpressionStateResponse",
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
def vts_server(model_loaded: bool = True, face_found: bool = True, expressions: list[str] | None = None):
    def handler(conn) -> None:
        for raw in conn:
            request = json.loads(raw)
            kind = request["messageType"]
            if kind == "CurrentModelRequest":
                data = {"modelLoaded": model_loaded, "modelName": "Mao", "numberOfLive2DParameters": 29, "hasPhysicsFile": True}
            elif kind == "FaceFoundRequest":
                data = {"found": face_found}
            elif kind == "InputParameterListRequest":
                names = ("MouthSmile", "MouthOpen", "Brows", "EyeOpenLeft", "EyeOpenRight")
                data = {"defaultParameters": [{"name": name, "value": 0.5} for name in names], "customParameters": []}
            elif kind == "ExpressionStateRequest":
                data = {"expressions": [{"name": file.split(".")[0], "file": file} for file in expressions or []]}
            else:
                data = {"authenticationToken": "tok", "authenticated": True, "vTubeStudioVersion": "1.30.0"}
            conn.send(json.dumps(reply(request, data)))

    server = serve(handler, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"ws://127.0.0.1:{server.socket.getsockname()[1]}"
    finally:
        server.shutdown()


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(vts, "TOKEN", tmp_path / "token.json")


def test_doctor_reports_ready_setup(monkeypatch, capsys):
    with vts_server(expressions=["exp_02.exp3.json", "exp_04.exp3.json", "exp_05.exp3.json", "exp_08.exp3.json"]) as url:
        monkeypatch.setattr(doctor, "VTS_URL", url)
        assert doctor.main() == 0

    out = capsys.readouterr().out
    assert "model: Mao" in out
    assert "reguli folosibile 4/4" in out
    assert "gata de înregistrare" in out


def test_doctor_fails_without_loaded_model(monkeypatch, capsys):
    with vts_server(model_loaded=False, expressions=["exp_02.exp3.json"]) as url:
        monkeypatch.setattr(doctor, "VTS_URL", url)
        assert doctor.main() == 1

    assert "niciun model încărcat" in capsys.readouterr().out


def test_doctor_fails_when_rules_have_no_expression(monkeypatch, capsys):
    with vts_server(expressions=["altceva.exp3.json"]) as url:
        monkeypatch.setattr(doctor, "VTS_URL", url)
        assert doctor.main() == 1

    out = capsys.readouterr().out
    assert "reguli folosibile 0/4" in out
    assert "nicio regulă din reactions.json" in out


def test_doctor_warns_when_face_not_found(monkeypatch, capsys):
    with vts_server(face_found=False, expressions=["exp_02.exp3.json"]) as url:
        monkeypatch.setattr(doctor, "VTS_URL", url)
        assert doctor.main() == 0

    assert "trackerul nu vede fața" in capsys.readouterr().out


def test_doctor_reports_missing_vts(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "VTS_URL", "ws://127.0.0.1:1")
    assert doctor.main() == 1
    assert "nu răspunde" in capsys.readouterr().out
