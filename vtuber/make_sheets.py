"""Foi de verificare: fiecare parametru al modelului, randat din `.moc3`.

    python vtuber/make_sheets.py vtuber/rig-hybrid OUTPUT/A_original

Ce iese (în folderul de model, sub `VERIFICARE/`) — exact ce vede VTube Studio:
  - `foaie-cap.png`   — cap stânga/dreapta/sus/jos, înclinat, corp
  - `foaie-ochi.png`  — privire stânga/dreapta/sus/jos, clipit, semi-clipit
  - `foaie-gura.png`  — gură închisă/deschisă, cele 5 expresii, coarne ascunse
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import preview_moc3 as P  # noqa: E402
from moc3_read import Moc3  # noqa: E402

CELL = 300
FONT_POS = (10, CELL - 22)

SHEETS = {
    "foaie-cap": [
        ("repaus", {}),
        ("cap stânga", {"ParamAngleX": -30}),
        ("cap dreapta", {"ParamAngleX": 30}),
        ("cap sus", {"ParamAngleY": 30}),
        ("cap jos", {"ParamAngleY": -30}),
        ("înclinat", {"ParamAngleZ": 30}),
        ("corp stânga", {"ParamBodyAngleX": -10}),
        ("corp dreapta", {"ParamBodyAngleX": 10}),
        ("respirație", {"ParamBreath": 1}),
    ],
    "foaie-ochi": [
        ("repaus", {}),
        ("privire stânga", {"ParamEyeBallX": -1}),
        ("privire dreapta", {"ParamEyeBallX": 1}),
        ("privire sus", {"ParamEyeBallY": 1}),
        ("privire jos", {"ParamEyeBallY": -1}),
        ("clipit", {"ParamEyeLOpen": 0, "ParamEyeROpen": 0}),
        ("pe jumătate", {"ParamEyeLOpen": 0.5, "ParamEyeROpen": 0.5}),
        ("clipit + stânga", {"ParamEyeLOpen": 0, "ParamEyeROpen": 0, "ParamEyeBallX": -1}),
        ("cap + privire", {"ParamAngleX": 30, "ParamEyeBallX": -1}),
    ],
    "foaie-gura": [
        ("gură închisă", {"ParamMouthOpenY": 0}),
        ("gură deschisă", {"ParamMouthOpenY": 1}),
        ("râs", {"ParamExprLaugh": 1}),
        ("îndrăgostit", {"ParamExprLove": 1}),
        ("trist", {"ParamExprSad": 1}),
        ("șocat", {"ParamExprShocked": 1}),
        ("suspicios", {"ParamExprSus": 1}),
        ("coarne ascunse", {"ParamHornsVis": 1, "ParamExprHornsOff": 0}),
        ("gură + privire", {"ParamMouthOpenY": 1, "ParamEyeBallX": 1}),
    ],
}

# numele din SHEETS → parametrul real al expresiei (coarnele folosesc ParamHornsVis)
ALIAS = {"ParamExprHornsOff": "ParamHornsVis"}


def render(moc, atlas, values: dict[str, float]) -> Image.Image:
    vals = {}
    for k, v in values.items():
        vals[ALIAS.get(k, k)] = v
    if "ParamHornsVis" in values and not values["ParamHornsVis"]:
        vals["ParamHornsVis"] = 0.0
    frame = P._frame(moc, atlas, vals)
    bg = Image.new("RGBA", (P.W, P.H), (18, 18, 22, 255))
    bg.alpha_composite(frame)
    return bg.convert("RGB")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    rig, out = Path(argv[0]), Path(argv[1]) / "VERIFICARE"
    only = set(argv[2].split(",")) if len(argv) > 2 else None
    out.mkdir(parents=True, exist_ok=True)
    moc = Moc3(str(rig / "izentric.moc3"))
    atlas = Image.open(rig / "texture_00.png").convert("RGBA")
    params = {p["id"] for p in moc.parameters()}

    for name, shots in SHEETS.items():
        if only and name not in only:
            continue
        shots = [(label, {k: v for k, v in vals.items() if ALIAS.get(k, k) in params})
                 for label, vals in shots]
        sheet = Image.new("RGB", (CELL * 3, CELL * 3), (0, 0, 0))
        draw = ImageDraw.Draw(sheet)
        for i, (label, vals) in enumerate(shots[:9]):
            tile = render(moc, atlas, vals).resize((CELL, CELL), Image.LANCZOS)
            x, y = (i % 3) * CELL, (i // 3) * CELL
            sheet.paste(tile, (x, y))
            draw.text((x + FONT_POS[0], y + FONT_POS[1]), label, fill=(255, 255, 255))
        path = out / f"{name}.png"
        sheet.save(path)
        print(f"scris {path}  ({len(shots[:9])} poziții)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
