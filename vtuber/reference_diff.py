"""Comparație cu modelele oficiale Live2D: ce au ele și nu are rigul iZentric.

Nu copiem nimic din ele (licența nu permite redistribuire) — doar citim structura și
comparăm ID-urile de parametri, intervalele și grupurile, ca să nu inventăm nume.

Sursa: github.com/Live2D/CubismWebSamples (Samples/Resources/<Model>/<Model>.cdi3.json).
Rulează: python vtuber/reference_diff.py
"""

from __future__ import annotations

import base64
import json
import sys
import urllib.request
from pathlib import Path

RAW = "https://api.github.com/repos/Live2D/CubismWebSamples/contents/Samples/Resources/{model}/{model}.{kind}.json"
MODELS = ("Haru", "Hiyori", "Mao")


def fetch(model: str, kind: str) -> dict:
    request = urllib.request.Request(RAW.format(model=model, kind=kind),
                                     headers={"Accept": "application/vnd.github+json",
                                              "User-Agent": "izentric-rig"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return json.loads(base64.b64decode(payload["content"]).decode("utf-8"))


def reference_parameters() -> tuple[set[str], dict[str, tuple[float, float]]]:
    ids: set[str] = set()
    ranges: dict[str, tuple[float, float]] = {}
    for model in MODELS:
        try:
            cdi = fetch(model, "cdi3")
        except Exception as error:                     # rețea sau model mutat
            print(f"  {model}: nu am putut citi cdi3 ({error})", file=sys.stderr)
            continue
        for entry in cdi.get("Parameters", []):
            ids.add(entry["Id"])
            if "Range" in entry:
                ranges.setdefault(entry["Id"], (entry["Range"]["Minimum"], entry["Range"]["Maximum"]))
    return ids, ranges


def main() -> int:
    local = json.loads((Path(__file__).parent / "rig" / "izentric.cdi3.json").read_text(encoding="utf-8"))
    mine = {entry["Id"] for entry in local["Parameters"]}
    ids, ranges = reference_parameters()
    if not ids:
        print("fără referință: nu am putut descărca nici un cdi3")
        return 2

    print(f"referință: {len(MODELS)} modele oficiale, {len(ids)} parametri cunoscuți\n")
    unknown = sorted(mine - ids)
    print(f"parametri inventați de noi: {unknown or 'niciunul'}")
    missing = sorted(ids - mine)
    print(f"parametri standard pe care nu îi avem: {len(missing)}")
    for name in missing[:12]:
        print(f"  - {name}")

    if not ranges:
        print("\nintervale: modelele oficiale nu publică intervale în cdi3 (sunt în moc3)")
        return 0 if not unknown else 1
    print("\nintervale comparate cu referința:")
    for entry in local["Parameters"]:
        name = entry["Id"]
        if name in ranges:
            ref = ranges[name]
            ours = (entry["Range"]["Minimum"], entry["Range"]["Maximum"])
            mark = "ok" if ref == ours else f"diferă (la ei {ref})"
            print(f"  {name:18s} {ours}  {mark}")
    return 0 if not unknown else 1


if __name__ == "__main__":
    raise SystemExit(main())
