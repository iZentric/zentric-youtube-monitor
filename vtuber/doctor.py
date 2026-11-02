"""Verifică tot lanțul VTuber într-o comandă: monitor, VTube Studio, model, tracker, expresii, reguli.

    python vtuber/doctor.py
"""

from __future__ import annotations

import json
from pathlib import Path

from websockets.sync.client import connect

from face_reactions import RULES, available_expressions, read_values, resolve
from vts import VTS_URL, authenticate, send

LATEST = Path(__file__).resolve().parent.parent / "data" / "latest.json"
REQUIRED = ("MouthSmile", "MouthOpen", "Brows", "EyeOpenLeft", "EyeOpenRight")


def check_monitor() -> str | None:
    if not LATEST.exists():
        return f"nu găsesc {LATEST} — rulează `python monitor.py`"
    snapshot = json.loads(LATEST.read_text(encoding="utf-8"))
    videos = sum(len(channel["latest"]) for channel in snapshot["channels"])
    print(f"✓ monitor: {len(snapshot['channels'])} canale, {videos} clipuri, actualizat {snapshot['fetched_at']}")
    return None


def main() -> int:
    problems: list[str] = []
    warnings: list[str] = []

    monitor_problem = check_monitor()
    if monitor_problem:
        warnings.append(monitor_problem)
        print(f"! {monitor_problem}")

    try:
        with connect(VTS_URL) as ws:
            authenticate(ws)
            state = send(ws, "APIStateRequest")["data"]
            print(f"✓ VTube Studio conectat pe {VTS_URL} (v{state.get('vTubeStudioVersion')})")

            model = send(ws, "CurrentModelRequest")["data"]
            if model.get("modelLoaded"):
                print(f"✓ model: {model.get('modelName')} ({model.get('numberOfLive2DParameters')} parametri, physics={model.get('hasPhysicsFile')})")
            else:
                problems.append("niciun model încărcat în VTube Studio")
                print("✗ niciun model încărcat")

            if send(ws, "FaceFoundRequest")["data"].get("found"):
                print("✓ trackerul vede fața")
            else:
                warnings.append("trackerul nu vede fața — verifică webcam-ul, lumina sau calibrararea")
                print("! trackerul nu vede fața")

            values = read_values(ws)
            missing = [name for name in REQUIRED if name not in values]
            if missing:
                problems.append(f"parametri de tracking lipsă: {', '.join(missing)}")
                print(f"✗ lipsesc parametri de tracking: {', '.join(missing)}")
            else:
                print("✓ tracking: " + ", ".join(f"{name}={values[name]:.2f}" for name in REQUIRED))

            expressions = available_expressions(ws)
            rules = json.loads(RULES.read_text(encoding="utf-8"))["rules"]
            usable = [rule for rule in rules if resolve(rule["expressionFile"], expressions)]
            unusable = [rule["name"] for rule in rules if not resolve(rule["expressionFile"], expressions)]
            print(f"{'✓' if usable else '✗'} expresii: modelul are {len(expressions)}, reguli folosibile {len(usable)}/{len(rules)}")
            if unusable:
                print(f"! reguli fără expresie în model: {', '.join(unusable)} — rulează face_reactions.py --list")
            if not usable:
                problems.append("nicio regulă din reactions.json nu are expresie în model")
    except OSError as exc:
        problems.append(f"VTube Studio nu răspunde pe {VTS_URL}: {exc}")
        print(f"✗ {problems[-1]}")

    print()
    for problem in problems:
        print(f"× {problem}")
    if problems:
        return 1
    for warning in warnings:
        print(f"! {warning}")
    print("gata de înregistrare" if not warnings else "merge, cu atenționările de mai sus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
