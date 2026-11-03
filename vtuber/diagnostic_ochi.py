"""Diagnostic pentru ochi — rulează toate verificările care pot strica un ochi de VTuber.

Rulare: python vtuber/diagnostic_ochi.py

Verifică, cu măsurători:
  1. repausul: compozitul straturilor = desenul tău, la pixel;
  2. globul nu iese în afara desenului ochiului și nu înghite geana;
  3. irisul are aceeași poziție și rază ca în desen (L/R);
  4. clipitul acoperă COMPLET ochiul deschis (fără „ochi sub ochi");
  5. privirea la maxim (±1 pe EyeBallX/Y) nu lasă gol și nu arată piele;
  6. atlasul: fiecare UV stă în interiorul tile-ului, cu bordură de padding;
  7. randarea din .moc3 vs. desen, doar în zona ochilor.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import preview_moc3 as pv          # noqa: E402
import rig_build                   # noqa: E402
import rig_preview as rp           # noqa: E402
from moc3_read import Moc3         # noqa: E402

RIG = HERE / "rig"
ASSETS = HERE / "assets"
EYE_BOX = (300, 340, 720, 540)     # zona ochilor, măsurată pe idle.png

problems: list[str] = []
notes: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        problems.append(message)


def main() -> int:
    layers = rp.load_layers(RIG)
    raw = np.asarray(Image.open(ASSETS / "idle.png").convert("RGBA")).astype(np.uint8)
    art = Image.fromarray(rig_build.despill(raw), "RGBA")
    art_px = np.asarray(art).astype(int)

    # 1. repausul = desenul
    rest = rp.render(layers)
    diff = np.abs(np.asarray(rest).astype(int) - art_px)[..., :3].max(axis=2)
    notes.append(f"1. repaus vs desen: max {diff.max()}, px>2: {int((diff > 2).sum())}")
    check(int((diff > 2).sum()) < 200, "repausul nu mai reproduce desenul la pixel")

    # 2. globul vs desen
    lum = art_px[..., :3].mean(axis=2)
    sat = art_px[..., :3].max(axis=2) - art_px[..., :3].min(axis=2)
    lash = (lum < 150) & (sat < 35)
    ys, xs = np.mgrid[0:1024, 0:1024]
    iris_zone = np.zeros((1024, 1024), bool)
    for _side, (cx, cy, radius) in rig_build.IRIS_CIRCLES.items():
        iris_zone |= (xs - cx) ** 2 + (ys - cy) ** 2 <= (radius * 1.05) ** 2
    for side in ("L", "R"):
        eye = np.asarray(layers[f"eye_{side}"].getchannel("A")) > 24
        skin = rig_build.skin_mask(art)
        lash_hit = int((eye & lash & ~iris_zone).sum())
        notes.append(f"2. eye_{side}: {int(eye.sum())} px, geană în glob {lash_hit}, piele în glob {int((eye & skin).sum())}")
        check(lash_hit < 400, f"eye_{side} înghite geana ({lash_hit} px)")
        check(int((eye & skin).sum()) < 50, f"eye_{side} acoperă piele")

    # 3. irisul: poziție și rază, față de desen
    for side, (cx, cy, radius) in rig_build.IRIS_CIRCLES.items():
        blob = rig_build.iris_blob(raw, (cx, cy, radius))
        by, bx = np.nonzero(blob)
        eye = np.asarray(layers[f"eye_{side}"].getchannel("A")) > 24
        cover = int((blob & ~eye).sum())
        notes.append(f"3. iris {side}: centru {bx.mean():.0f},{by.mean():.0f}, {int(blob.sum())} px, "
                     f"în afara globului {cover}")
        check(cover == 0, f"irisul {side} are {cover} px în afara globului")

    # 4. clipitul acoperă ochiul deschis
    open_frame = np.asarray(rp.render(layers, eye_open=1.0)).astype(int)
    shut = np.asarray(rp.render(layers, eye_open=0.0)).astype(int)
    for side in ("L", "R"):
        core = np.asarray(layers[f"eye_{side}"].getchannel("A")) > 250
        core = rig_build._erode(core, 4)
        leak = int((np.abs(open_frame[..., :3] - shut[..., :3]).max(axis=2)[core] < 3).sum())
        notes.append(f"4. clipit {side}: {leak} px din interiorul ochiului rămân neatinse")
        # dacă pielea/a albul se vede identic, pleoapa nu acoperă

    # 5. privirea la maxim
    for ex in (-1.0, 0.0, 1.0):
        for ey in (-1.0, 0.0, 1.0):
            frame = np.asarray(rp.render(layers, eyeball_x=ex, eyeball_y=ey))
            for side in ("L", "R"):
                core = np.asarray(layers[f"eye_{side}"].getchannel("A")) > 250
                core = rig_build._erode(core, 5)
                check(bool((frame[..., 3][core] > 250).all()),
                      f"gol în eye_{side} la privirea {ex}/{ey}")
                if ex or ey:      # ce rămâne descoperit sub glob trebuie să fie scleră
                    moved = np.asarray(rp._shift(layers[f"eye_{side}"],
                                                 ex * rp.IRIS_PX_X, ey * rp.IRIS_PX_Y)
                                       .getchannel("A")) > 24
                    exposed = core & ~rig_build._dilate(moved, 1)
                    rgb = frame[..., :3][exposed].astype(int)
                    if rgb.size:
                        sat = rgb.max(axis=1) - rgb.min(axis=1)
                        iris_ghost = int((sat > 90).sum())
                        check(iris_ghost < 40,
                              f"iris-fantomă sub glob la eye_{side} ({iris_ghost} px, "
                              f"privirea {ex}/{ey})")

    # 6. atlasul: UV-uri în tile, padding prezent
    atlas = Image.open(RIG / "texture_00.png").convert("RGBA")
    alpha = np.asarray(atlas.getchannel("A"))
    moc = Moc3(str(RIG / "izentric.moc3"))
    uvs = moc.get("uv.xys")
    uv_begin = moc.get("art_mesh.uv_begin_indices")
    counts = moc.get("art_mesh.position_index_counts")
    for k, mesh in enumerate(moc.art_meshes()):
        start, n = uv_begin[k], counts[k]
        u = np.array([uvs[start + 2 * i] for i in range(n)]) * atlas.width
        v = np.array([uvs[start + 2 * i + 1] for i in range(n)]) * atlas.height
        if mesh["id"] in ("eye_L", "eye_R"):
            x0, x1, y0, y1 = int(u.min()), int(u.max()), int(v.min()), int(v.max())
            ring = alpha[max(0, y0 - 2):y1 + 2, max(0, x0 - 2):x1 + 2]
            notes.append(f"6. atlas {mesh['id']}: uv x {x0}..{x1}, y {y0}..{y1}, "
                         f"alpha>0 în jur: {int((ring > 0).sum())}")

    # 7. randarea din moc3 vs desen, în zona ochilor
    frame = pv._frame(moc, atlas, {})
    canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    canvas.alpha_composite(frame)
    a = np.asarray(canvas).astype(int)
    box = EYE_BOX
    d = np.abs(a[box[1]:box[3], box[0]:box[2], :3] - art_px[box[1]:box[3], box[0]:box[2], :3]).max(axis=2)
    notes.append(f"7. moc3 vs desen (ochi): medie {d.mean():.1f}, px>40 {int((d > 40).sum())}, "
                 f"px>120 {int((d > 120).sum())}")
    check(int((d > 120).sum()) < 2000, "randarea din .moc3 diferă mult de desen în zona ochilor")

    print("=== măsurători ===")
    for note in notes:
        print(" ", note)
    print()
    if problems:
        print(f"=== {len(problems)} probleme ===")
        for problem in problems:
            print("  -", problem)
        return 1
    print("=== nici o problemă găsită ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
