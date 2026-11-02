"""Conexiune comună la API-ul VTube Studio (WebSocket local, port 8001)."""

from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKEN = HERE / "token.json"

VTS_URL = os.environ.get("VTS_URL", "ws://127.0.0.1:8001")
PLUGIN = {"pluginName": "iZentric YouTube Monitor", "pluginDeveloper": "iZentric"}


def send(ws, message_type: str, data: dict | None = None) -> dict:
    ws.send(json.dumps({
        "apiName": "VTubeStudioPublicAPI",
        "apiVersion": "1.0",
        "requestID": message_type,
        "messageType": message_type,
        "data": data or {},
    }))
    reply = json.loads(ws.recv(timeout=5))
    if "errorMessage" in reply:
        raise RuntimeError(f"{message_type}: {reply['errorMessage']} (errorID {reply.get('errorID')})")
    return reply


def authenticate(ws) -> None:
    for attempt in (1, 2):
        token = TOKEN.read_text(encoding="utf-8").strip() if TOKEN.exists() else ""
        if not token:
            token = send(ws, "AuthenticationTokenRequest", PLUGIN)["data"]["authenticationToken"]
            TOKEN.write_text(token, encoding="utf-8")
        reply = send(ws, "AuthenticationRequest", {**PLUGIN, "authenticationToken": token})
        if reply["data"].get("authenticated"):
            return
        if attempt == 1 and TOKEN.exists():
            TOKEN.unlink()  # token vechi (plugin șters din VTS) -> cerem altul
            continue
        raise RuntimeError(f"autentificare refuzată: {reply['data'].get('reason', 'fără motiv')}")
