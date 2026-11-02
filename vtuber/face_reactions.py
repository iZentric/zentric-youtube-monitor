"""Pornește expresii Live2D când fața ta face o anumită formă, citind parametrii de tracking din VTube Studio.

Exemplu: zâmbești -> „happy”, deschizi gura + ridici sprâncenele -> „surprised”, faci cu ochiul -> „wink”.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from time import monotonic, sleep

from websockets.sync.client import connect

from vts import VTS_URL, authenticate, send

RULES = Path(__file__).with_name("reactions.json")
FADE = 0.3


def read_values(ws) -> dict:
    """Toți parametrii de tracking, într-un singur request."""
    data = send(ws, "InputParameterListRequest")["data"]
    params = data.get("defaultParameters", []) + data.get("customParameters", [])
    return {param["name"]: param["value"] for param in params}


def available_expressions(ws) -> dict:
    """{fișier .exp3.json: nume} pentru expresiile modelului încărcat."""
    data = send(ws, "ExpressionStateRequest", {"details": False})["data"]
    return {expression["file"]: expression["name"] for expression in data.get("expressions", [])}


def resolve(expression_file: str, available: dict) -> str | None:
    """Găsește numele exact folosit de VTS; acceptă și doar numele fișierului."""
    if expression_file in available:
        return expression_file
    wanted = Path(expression_file).name
    for file in available:
        if Path(file).name == wanted:
            return file
    return None


def matches(when: dict, values: dict) -> bool:
    for name, bounds in when.items():
        value = values.get(name)
        if value is None:
            return False
        if value < bounds.get("min", float("-inf")) or value > bounds.get("max", float("inf")):
            return False
    return True


def step(rules: list[dict], values: dict, state: dict, now: float) -> list[tuple[str, bool]]:
    """O iterație a motorului: întoarce [(fișier expresie, activează?)]."""
    actions = []
    for rule in rules:
        current = state.setdefault(rule["name"], {"active": False, "until": 0.0, "cooldown": 0.0})
        if current["active"]:
            if now >= current["until"]:
                current["active"] = False
                current["cooldown"] = now + rule.get("cooldownSeconds", 3.0)
                actions.append((rule["expressionFile"], False))
        elif now >= current["cooldown"] and matches(rule["when"], values):
            current["active"] = True
            current["until"] = now + rule.get("holdSeconds", 1.5)
            actions.append((rule["expressionFile"], True))
    return actions


def run(ws, rules: list[dict], iterations: int | None = None) -> None:
    state: dict = {}
    count = 0
    try:
        while iterations is None or count < iterations:
            count += 1
            for expression_file, active in step(rules, read_values(ws), state, monotonic()):
                send(ws, "ExpressionActivationRequest", {"expressionFile": expression_file, "active": active, "fadeTime": FADE})
                print(("pornit " if active else "oprit  ") + expression_file)
            sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        for name, current in state.items():
            if current["active"]:
                file = next(rule["expressionFile"] for rule in rules if rule["name"] == name)
                send(ws, "ExpressionActivationRequest", {"expressionFile": file, "active": False, "fadeTime": 0.1})


def main() -> int:
    rules = json.loads(RULES.read_text(encoding="utf-8"))["rules"]
    try:
        with connect(VTS_URL) as ws:
            authenticate(ws)
            expressions = available_expressions(ws)
            if "--list" in sys.argv:
                print("expresii în modelul încărcat:")
                for file, name in expressions.items():
                    print(f"  {file}  ({name})")
                return 0
            usable = []
            for rule in rules:
                resolved = resolve(rule["expressionFile"], expressions)
                if resolved:
                    usable.append({**rule, "expressionFile": resolved})
                else:
                    print(f"! {rule['name']}: modelul nu are {rule['expressionFile']} — rulez --list și corectez reactions.json")
            if not usable:
                print("nicio regulă folosibilă: niciun fișier din reactions.json nu există în model")
                return 1
            run(ws, usable)
    except OSError as exc:
        print(f"nu mă pot conecta la VTube Studio ({VTS_URL}): {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
