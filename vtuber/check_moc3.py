"""Validare .moc3 cu Cubism Core oficial (pachetul `live2d-py`).

Core e runtime-ul folosit și de VTube Studio: un fișier acceptat aici e acceptat
și acolo. Core nu are erori grațioase — pe un fișier invalid poate segfaulta — deci
verificarea rulează într-un subproces, iar un crash contează ca „respins".
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile

# 1x1 PNG transparent, ca Core să aibă pe ce mapa textura 0
_PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360000002000100ffff03000006000557bfabd40000000049454e44ae426082")

_PROBE = r"""
import json, sys
import live2d
live2d.init()
model = live2d.Model()
model.LoadModelJson(sys.argv[1], create_renderer=False)
report = {"params": model.GetParamCount(), "ids": model.GetParamIds(),
          "canvas": list(model.GetCanvasSize())}
print("REZULTAT" + json.dumps(report))
"""


def available() -> bool:
    try:
        import live2d  # noqa: F401
    except Exception:
        return False
    return True


def core_accepts(moc3_path: str, textures: list[str] | None = None) -> dict:
    """Întoarce {'available', 'ok', 'params', 'canvas'} sau {'ok': False, 'error'}."""
    if not available():
        return {"available": False, "ok": False, "error": "live2d-py nu e instalat"}

    with tempfile.TemporaryDirectory() as tmp:
        tex = os.path.join(tmp, "tex.png")
        with open(tex, "wb") as fh:
            fh.write(_PNG_1PX)
        model3 = os.path.join(tmp, "probe.model3.json")
        with open(model3, "w", encoding="utf-8") as fh:
            json.dump({"Version": 3, "FileReferences": {
                "Moc": os.path.abspath(moc3_path),
                "Textures": [os.path.abspath(t) for t in (textures or [tex])],
            }}, fh, indent=2)
        proc = subprocess.run([sys.executable, "-c", _PROBE, model3],
                              capture_output=True, text=True)
    if proc.returncode != 0:
        return {"available": True, "ok": False,
                "error": f"Core a respins fișierul (cod {proc.returncode})"}
    line = next((l for l in proc.stdout.splitlines() if l.startswith("REZULTAT")), None)
    if not line:
        return {"available": True, "ok": False, "error": "fără raport de la Core"}
    data = json.loads(line[len("REZULTAT"):])
    if not data["params"]:
        return {"available": True, "ok": False, "error": "Core nu a găsit niciun parametru"}
    return {"available": True, "ok": True, **data}


def header(moc3_path: str) -> dict:
    """Câteva invariante de format, fără Core."""
    with open(moc3_path, "rb") as fh:
        blob = fh.read()
    sot = struct.unpack_from("<160I", blob, 64)
    used = [v for v in sot if v]
    return {
        "size": len(blob),
        "magic": blob[:4],
        "version": blob[4],
        "sections": len(used),
        "first_section": sot[0],
        "last_offset": max(used),
        "in_file": max(used) <= len(blob),
        "increasing": all(used[i] <= used[i + 1] for i in range(len(used) - 1)),
    }


def main(argv: list[str]) -> int:
    if not argv:
        print("folosire: python vtuber/check_moc3.py <fisier.moc3>")
        return 2
    report = {**header(argv[0]), **core_accepts(argv[0])}
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
