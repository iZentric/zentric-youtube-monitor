"""Ochii „ca la carte": doar irisul se mișcă, albul rămâne fundal.

    python vtuber/eyes_iris.py            → scrie vtuber/rig-iris/

Ce face, pe fiecare ochi:
  1. ia irisul desenat și îl taie pe **elipsa exactă** (alfa anti-aliasat) — fără
     franjuri albe, fără geană prinsă în decupaj; vârful ascuns sub geană se
     completează radial, din gradientul irisului;
  2. scoate irisul din `head.png` și umple golul cu **albul sclerii**, pe rânduri
     (ca să păstreze umbra albăstruie de sub geană) — deci nu apare „ochi sub ochi"
     când irisul se mută;
  3. lasă restul straturilor neatinse.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import eyes_rebuild as E  # noqa: E402

SRC = HERE / "rig"
DST = HERE / "rig-iris"
SIDES = ("L", "R")


def _ellipse(cx: float, cy: float, r: float, grow: float = 0.0):
    yy, xx = np.mgrid[0:E.H, 0:E.W]
    rr = (r + grow)
    return (((xx - cx) / rr) ** 2 + ((yy - cy) / rr) ** 2) <= 1.0


def iris_layer(rgb: np.ndarray, side: str) -> tuple[np.ndarray, tuple[float, float, float]]:
    info = E.analyse(rgb, side)
    cx, cy, rx, ry = info["iris_fit"]
    r = max(rx, ry)
    full = _ellipse(cx, cy, r)
    hl = np.zeros((E.H, E.W), bool)
    for hx, hy, hrx, hry, _n in info["highlights"]:
        hl |= _ellipse(hx, hy, max(hrx, hry) + 1.5)
    # reflexiile fac parte din iris: se mută odată cu el
    drawn = (info["iris"] | hl) & full

    layer = np.zeros((E.H, E.W, 4), np.uint8)
    layer[drawn, :3] = rgb[drawn, :3].astype(np.uint8)

    # vârful irisului stă sub geană în desen: se continuă radial din irisul desenat
    hole = full & ~drawn
    ys, xs = np.nonzero(hole)
    for y, x in zip(ys, xs):
        dx, dy = x - cx, y - cy
        d = max(abs(dx), abs(dy), 1.0)
        ux, uy = dx / d, dy / d
        for step in range(1, int(r) + 6):
            sx, sy = int(round(x + ux * step)), int(round(y + uy * step))
            if not (0 <= sx < E.W and 0 <= sy < E.H):
                break
            if drawn[sy, sx]:
                layer[y, x, :3] = rgb[sy, sx, :3]
                break
    if hole.any():
        blur = Image.fromarray(layer[..., :3], "RGB").filter(ImageFilter.GaussianBlur(1.6))
        layer[hole, :3] = np.asarray(blur)[hole]

    alpha = Image.fromarray((full * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(0.6))
    layer[..., 3] = np.asarray(alpha)
    return layer, (cx, cy, r)


def head_without_iris(rgb: np.ndarray, fits: dict[str, tuple[float, float, float]]) -> np.ndarray:
    """Scoate irisul din cap și lasă sclera desenului neatinsă.

    Se înlocuiește doar elipsa irisului (+1,5 px pentru contur). Culoarea se
    obține pe orizontală, interpolând între sclera reală din stânga și cea din
    dreapta aceleiași linii, deci cusătura nu se vede.
    """
    head = np.array(Image.open(SRC / "head.png").convert("RGBA"))
    lum = rgb[..., :3].mean(2)
    sclera = (lum > 150) & (np.ptp(rgb[..., :3], axis=2) < 40)
    for side in (list(fits) or ["L", "R"]):
        info = E.analyse(rgb, side)
        cx, cy, r = fits[side]
        hole = _ellipse(cx, cy, r, grow=2.2) & info["ochi"]
        last: np.ndarray | None = None
        for y in np.nonzero(hole.any(1))[0]:
            xs_hole = np.nonzero(hole[y])[0]
            xs_ok = np.nonzero(sclera[y] & info["ochi"][y])[0]
            left = xs_ok[xs_ok < xs_hole[0]]
            right = xs_ok[xs_ok > xs_hole[-1]]
            cl = rgb[y, left[max(0, len(left) - 4)], :3].astype(float) if len(left) else None
            cr = rgb[y, right[min(len(right) - 1, 3)], :3].astype(float) if len(right) else None
            if cl is None and cr is None:
                if last is not None:
                    head[y, xs_hole, :3] = last.astype(np.uint8)
                    head[y, xs_hole, 3] = 255
                continue
            if cl is None:
                cl = cr
            if cr is None:
                cr = cl
            t = np.linspace(0.0, 1.0, len(xs_hole))[:, None]
            colours = cl * (1 - t) + cr * t
            last = colours.mean(axis=0)
            head[y, xs_hole, :3] = np.round(colours).astype(np.uint8)
            head[y, xs_hole, 3] = 255
        # netezire pe verticală: altfel rămân dungi orizontale la cusătură
        blur = Image.fromarray(head[..., :3], "RGB").filter(ImageFilter.GaussianBlur(2.0))
        head[hole, :3] = np.asarray(blur)[hole]
    return head


def main() -> int:
    from rig_preview import LAYER_FILES
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True)
    for name in LAYER_FILES:            # doar straturile, nu și pozele de verificare
        source = SRC / f"{name}.png"
        if source.exists():
            shutil.copy2(source, DST / source.name)
    rgb = E._load("idle.png")

    fits = {}
    for side in SIDES:
        layer, fit = iris_layer(rgb, side)
        fits[side] = fit
        Image.fromarray(layer, "RGBA").save(DST / f"iris_{side}.png")
        ys, xs = np.nonzero(layer[..., 3] > 8)
        print(f"iris_{side}: centru ({fit[0]:.1f},{fit[1]:.1f}) r={fit[2]:.1f}, "
              f"{int((layer[..., 3] > 8).sum())} px")

    Image.fromarray(head_without_iris(rgb, fits), "RGBA").save(DST / "head.png")
    print(f"scris {DST}/ (head fără iris + iris_L/iris_R)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
