"""Declanșează o animație (hotkey) în VTube Studio când monitorul găsește clipuri noi."""

from __future__ import annotations

import json
import os
from pathlib import Path
from time import sleep

from websockets.sync.client import connect

HERE = Path(__file__).resolve().parent
LATEST = HERE.parent / "data" / "latest.json"
STATE = HERE / "state.json"
TOKEN = HERE / "token.json"

VTS_URL = os.environ.get("VTS_URL", "ws://127.0.0.1:8001")
HOTKEY = os.environ.get("VTS_HOTKEY", "Surprised")
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


def unseen_videos(snapshot: dict, seen: set[str]) -> list[dict]:
    return [video for channel in snapshot["channels"] for video in channel["latest"] if video["video_id"] not in seen]


def save_state(seen: set[str], fresh: list[dict]) -> None:
    merged = seen | {video["video_id"] for video in fresh}
    STATE.write_text(json.dumps({"seen": sorted(merged)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def trigger(videos: list[dict]) -> None:
    with connect(VTS_URL) as ws:
        authenticate(ws)
        for video in videos:
            send(ws, "HotkeyTriggerRequest", {"hotkeyID": HOTKEY})
            print(f"hotkey „{HOTKEY}” → {video['title']}")
            sleep(0.2)


def main() -> int:
    snapshot = json.loads(LATEST.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    seen = set(state.get("seen", []))
    fresh = unseen_videos(snapshot, seen)
    if not state:
        save_state(seen, fresh)
        print(f"prima rulare: am memorat {len(fresh)} clipuri existente, nu declanșez nimic")
        return 0
    if not fresh:
        print("niciun clip nou")
        return 0
    try:
        trigger(fresh)
    except OSError as exc:
        print(f"nu mă pot conecta la VTube Studio ({VTS_URL}): {exc}")
        return 1
    save_state(seen, fresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
