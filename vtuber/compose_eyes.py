"""Stratul de ochi al modelului = pixelii desenului, cu alfa din masca ochiului.

De ce nu compun piesele: piesele (`eyes_rebuild.py`) sunt făcute pentru straturi
separate în Cubism și verificate la G-OCHI. Comprimate într-un singur strat ele
lasă cusături (inel de piele, halou alb) — s-a văzut la zoom 400%: marginea
`skin_under_eye` ieșea din pielea desenului. Modelul care se încarcă în VTube
Studio trebuie să arate exact ca desenul, deci aici se taie din desen.

    python vtuber/compose_eyes.py            # scrie eye_L.png / eye_R.png
    python vtuber/compose_eyes.py --pieces   # varianta cu piese (pentru G-OCHI)

Alfa: masca ochiului = diferența dintre desenul cu ochiul deschis și cel cu ochiul
închis (acolo se schimbă exact ochiul), dilatată 2 px ca să nu rămână fir de piele
între ochi și pleoapă.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import eyes_rebuild as E  # noqa: E402

RIG = HERE / "rig"
EYES = RIG / "eyes"

ORDER = ["skin_under_eye", "eye_white", "iris",
         "highlight_3", "highlight_2", "highlight_1", "upper_lash"]


def from_drawing(side: str) -> None:
    rgb = E._load("idle.png")
    info = E.analyse(rgb, side)
    alpha = E._dilate(info["ochi"], 2)
    layer = np.zeros((E.H, E.W, 4), np.uint8)
    layer[alpha, :3] = rgb[alpha, :3].astype(np.uint8)
    a = Image.fromarray((alpha * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(0.5))
    layer[..., 3] = np.asarray(a)
    out = RIG / f"eye_{side}.png"
    Image.fromarray(layer, "RGBA").save(out)
    ys, xs = np.nonzero(alpha)
    print(f"{side}: desen tăiat, {int(alpha.sum())} px, "
          f"cutie ({xs.min()},{ys.min()},{xs.max()},{ys.max()}) → {out.name}")


def build_eyes_closed() -> None:
    """Stratul „ochi închiși" = desenul cu ochii închiși peste EXACT aceeași mască.

    Altfel pleoapa desenată e mai mică decât globul, iar la clipit rămâne o dunga
    de iris la vedere (584 px măsurați de test). Cu aceeași mască, acoperirea e exactă
    și arată ca desenul.
    """
    rgb = E._load("idle.png")
    blink = E._load("blink.png")
    ochi = np.zeros((E.H, E.W), bool)
    for side in ("L", "R"):
        ochi |= E.analyse(rgb, side)["ochi"]
    alpha = E._dilate(ochi, 2)
    layer = np.zeros((E.H, E.W, 4), np.uint8)
    layer[alpha, :3] = blink[alpha, :3].astype(np.uint8)
    # margine mai moale: la 0,5 px se vedea conturul dreptunghiular al petecului
    # peste pielea capului (umbra desenului cu ochii închiși e ușor diferită)
    a = Image.fromarray((alpha * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(1.0))
    layer[..., 3] = np.asarray(a)
    Image.fromarray(layer, "RGBA").save(RIG / "eyes_closed.png")
    print(f"eyes_closed: {int(alpha.sum())} px din desenul cu ochii închiși")


def from_pieces(side: str) -> None:
    x0, y0, x1, y1 = [int(v) for v in (EYES / f"box_{side}.txt").read_text().split()]
    base = Image.open(RIG / f"eye_{side}.png").convert("RGBA")
    canvas = Image.new("RGBA", base.size, (0, 0, 0, 0))
    for name in ORDER:
        canvas = Image.alpha_composite(canvas, Image.open(EYES / f"{name}_{side}.png").convert("RGBA"))
    base.paste(canvas.crop((x0, y0, x1, y1)), (x0, y0))
    base.save(RIG / f"eye_{side}.png")
    print(f"{side}: piese compuse în cutia ({x0},{y0},{x1},{y1})")


def main(argv: list[str]) -> int:
    build = from_pieces if "--pieces" in argv else from_drawing
    for side in ("L", "R"):
        build(side)
    build_eyes_closed()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
