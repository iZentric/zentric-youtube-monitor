"""Reacții instantanee în VTube Studio: tag de emoție → expresie + smucitură de cap.

Fluxul e cel din specificație: LLM-ul scrie un tag ascuns în replică (`[anger]`), textul e
curățat înainte de TTS, iar tag-ul devine imediat (a) o expresie activată și (b) o
smucitură de cap pe parametrii de unghi.

Cum se trimite la VTS (API-ul oficial, `README.md` secțiunile „Injecting parameter data" și
„Requesting activation or deactivation of expressions"):

  * `ExpressionActivationRequest` cu `expressionFile` + `fadeTime` + `active`
    (funcționează fără hotkey; documentația recomandă hotkey-uri, de aceea modulul poate
    trimite și `HotkeyTriggerRequest` cu numele hotkey-ului, dacă îl dai în config);
  * `InjectParameterDataRequest` cu `mode = "set"`, `faceFound = false` și
    `parameterValues` = unghiurile capului.

Valorile de unghi sunt cele din specificație (±30° stânga/dreapta, ±20° sus/jos, ±15°
înclinare, corp ±10°) și se țin în parametrii modelului, care are exact aceste intervale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TAG_RE = re.compile(r"\[([a-z_]+)\]")

# tag → expresia din model + unghiurile capului (grade) + cât ține smucitura (secunde)
# Expresiile sunt cele 5 generate în pachetul VTS (izentric.<slug>.exp3.json).
@dataclass(frozen=True)
class Reactie:
    tag: str
    expression: str | None = None
    hotkey: str | None = None
    angle: dict[str, float] = field(default_factory=dict)
    hold: float = 0.35


REACTII: dict[str, Reactie] = {
    # neutral: fără expresie, doar revenirea la poziția de repaus
    "neutral": Reactie("neutral", angle={"ParamAngleX": 0, "ParamAngleY": 0, "ParamAngleZ": 0}),
    # rânjet / sarcasm: capul se înclină lateral, privirea fuge într-o parte
    "smirk": Reactie("smirk", expression="sus", hotkey="Suspicios",
                     angle={"ParamAngleZ": -9, "ParamAngleX": -5, "ParamEyeBallX": -0.5}, hold=0.6),
    # furie: capul înainte și smucit, corpul se înclină spre cameră
    "anger": Reactie("anger", expression=None, hotkey="Suspicios",
                     angle={"ParamAngleX": 14, "ParamAngleZ": 6, "ParamBodyAngleX": 8}, hold=0.5),
    # șoc: cap pe spate, ochii largi (expresia Șocat)
    "shock": Reactie("shock", expression="shocked", hotkey="Șocat",
                     angle={"ParamAngleX": -16, "ParamAngleY": 8, "ParamAngleZ": 5}, hold=0.45),
    # hype: râs, capul se leagănă amplu
    "hype": Reactie("hype", expression="laugh", hotkey="Râs",
                    angle={"ParamAngleX": -6, "ParamAngleY": -10, "ParamBodyAngleZ": 6}, hold=0.8),
    # tristețe / milă
    "sad": Reactie("sad", expression="sad", hotkey="Trist",
                   angle={"ParamAngleX": 8, "ParamAngleZ": -8}, hold=0.7),
    # dragoste (donation / compliment)
    "love": Reactie("love", expression="love", hotkey="Îndrăgostit",
                    angle={"ParamAngleZ": 10, "ParamAngleY": 5}, hold=0.8),
}

ALIASES = {"angry": "anger", "rage": "anger", "surprised": "shock", "shocked": "shock",
           "excited": "hype", "happy": "hype", "sarcasm": "smirk", "sassy": "smirk"}


def parse_tags(text: str) -> tuple[str, list[str]]:
    """Scoate tag-urile din text și întoarce (text curat pentru TTS, lista de emoții).

    Tag-urile necunoscute sunt ignorate (nu strică textul), iar cele cunoscute se întorc
    în ordinea apariției, fără dubluri consecutive.
    """
    gasite: list[str] = []
    for tag in TAG_RE.findall(text):
        nume = ALIASES.get(tag, tag)
        if nume in REACTII and gasite[-1:] != [nume]:
            gasite.append(nume)
    curat = TAG_RE.sub("", text)
    curat = re.sub(r"\s{2,}", " ", curat).strip()
    return curat, gasite


def expression_request(slug: str, active: bool = True, fade: float = 0.12) -> tuple[str, dict]:
    """Cererea oficială de activare a unei expresii, fără hotkey."""
    return "ExpressionActivationRequest", {
        "expressionFile": f"izentric.{slug}.exp3.json",
        "fadeTime": max(0.0, min(2.0, fade)),
        "active": active,
    }


def head_request(angle: dict[str, float]) -> tuple[str, dict]:
    """Smucitura de cap: parametrii se scriu direct, cu `mode = set`."""
    return "InjectParameterDataRequest", {
        "faceFound": False,
        "mode": "set",
        "parameterValues": [{"id": pid, "value": float(v), "weight": 1.0}
                            for pid, v in angle.items()],
    }


def requests_for(tag: str) -> list[tuple[str, dict]]:
    """Toate cererile pentru un tag, în ordine: expresie, apoi cap."""
    nume = ALIASES.get(tag, tag)
    reactie = REACTII.get(nume)
    if reactie is None:
        return []
    cereri: list[tuple[str, dict]] = []
    if reactie.expression:
        cereri.append(expression_request(reactie.expression))
    if reactie.angle:
        cereri.append(head_request(reactie.angle))
    return cereri


def main(argv: list[str]) -> int:
    """Test manual: `python vtuber/reactii.py "Ce naiba ai zis?! [anger]"`."""
    import time
    from pathlib import Path

    from websockets.sync.client import connect

    from vts import VTS_URL, authenticate, send

    text = " ".join(argv) or "Test [anger] gata"
    curat, tags = parse_tags(text)
    print(f"text pentru TTS: {curat!r}")
    print(f"reacții: {tags or 'niciuna'}")
    if not tags:
        return 0
    try:
        ws_ctx = connect(VTS_URL)
        ws_ctx.__enter__()
    except OSError as exc:
        print(f"nu mă pot conecta la VTube Studio ({VTS_URL}): {exc}")
        print("deschide VTS, pornește „Allow Plugin API access” și rulează din nou")
        return 1
    ws = ws_ctx
    try:
        authenticate(ws)
        for tag in tags:
            for message, data in requests_for(tag):
                send(ws, message, data)
            time.sleep(REACTII[tag].hold)
            for message, data in requests_for("neutral"):
                send(ws, message, data)
    finally:
        ws_ctx.__exit__(None, None, None)
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
