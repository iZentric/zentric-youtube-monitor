"""Ce au modelele „complete" din VTube Studio și ne lipsea: icon + animație de repaus.

    python vtuber/make_extras.py OUTPUT/A_original [alt folder ...]

Scrie în folderul de model:
  - `icon.png`      — pictograma modelului (VTS o arată în listă);
  - `izentric.idle.motion3.json` — buclă de 5 s (capul se leagănă, corpul respiră);
  - legătura `IdleAnimation` din `izentric.vtube.json`.

Formatul `motion3.json` e cel din modelul real de referință (ellot/Scene1.motion3.json):
`Segments` = [tip, (timp, valoare), …], tip 0 = liniar; `Meta` numără exact:
CurveCount = câte curbe, TotalPointCount = suma punctelor, TotalSegmentCount = suma (puncte-1).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
DURATION = 5.0
FPS = 30.0

# (parametru, [(timp, valoare), …]) — o buclă care se închide pe sine
CURVES: list[tuple[str, list[tuple[float, float]]]] = [
    ("ParamAngleX", [(0.0, 0.0), (1.7, 7.0), (3.3, -7.0), (5.0, 0.0)]),
    ("ParamAngleY", [(0.0, 0.0), (2.5, 3.0), (5.0, 0.0)]),
    ("ParamAngleZ", [(0.0, 0.0), (2.0, -3.0), (4.0, 3.0), (5.0, 0.0)]),
    ("ParamBodyAngleZ", [(0.0, 0.0), (2.5, 2.0), (5.0, 0.0)]),
    ("ParamBreath", [(0.0, 0.0), (2.5, 1.0), (5.0, 0.0)]),
]


def motion() -> dict:
    curves = []
    for param, points in CURVES:
        seg = [0]
        for t, v in points:
            seg += [t, v]
        curves.append({"Target": "Parameter", "Id": param, "Segments": seg})
    return {
        "Version": 3,
        "Meta": {
            "Duration": DURATION,
            "Fps": FPS,
            "Loop": True,
            "AreBeziersRestricted": True,
            "CurveCount": len(curves),
            # Segments = [tip, (t, v) × n] → n = (len-1)/2 puncte, n-1 segmente
            "TotalSegmentCount": sum((len(c["Segments"]) - 1) // 2 - 1 for c in curves),
            "TotalPointCount": sum((len(c["Segments"]) - 1) // 2 for c in curves),
            "UserDataCount": 0,
            "TotalUserDataSize": 0,
        },
        "Curves": curves,
    }


def icon(path: Path) -> None:
    src = Image.open(ASSETS / "idle.png").convert("RGBA")
    # capul, pătrat, centrat pe față
    box = (250, 130, 774, 654)
    src.crop(box).resize((256, 256), Image.LANCZOS).save(path)


def apply(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    icon(folder / "icon.png")
    (folder / "izentric.idle.motion3.json").write_text(
        json.dumps(motion(), indent=2, ensure_ascii=False), encoding="utf-8")
    vtube = folder / "izentric.vtube.json"
    if vtube.exists():
        data = json.loads(vtube.read_text(encoding="utf-8"))
        refs = data.setdefault("FileReferences", {})
        refs["Icon"] = "icon.png"
        refs["IdleAnimation"] = "izentric.idle.motion3.json"
        refs["IdleAnimationWhenTrackingLost"] = ""
        vtube.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{folder}: icon.png + izentric.idle.motion3.json + legături în .vtube.json")


def main(argv: list[str]) -> int:
    for target in argv:
        apply(Path(target))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
