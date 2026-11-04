"""Ochii refăcuți din piese întregi, separate — nu decupați din imaginea plată.

Piesele, per ochi:
  skin_under_eye   pielea din jur, plată și continuă (la clipit nu rămâne nici un contur)
  eye_white        albul întreg + umbra albăstruie, întins 20 px SUB geană
  iris             elipsa COMPLETĂ a irisului (gradient + pupilă), inclusiv sub pleoapă
  highlight_1..3   fiecare reflexie, disc vectorial neted (4× apoi redus)
  upper_lash       linia neagră de sus, strat propriu, capete complete
  eyelid_closed    linia de ochi închis

Geometria nu vine din dreptunghi, ci din UMPLEREA ochiului mărginită de geană (aceeași
metodă ca la glob): așa nu intră părul și nu se inventează forme.
Tăierea (irisul se vede doar în alb) se face la rig, prin Clipping Mask.
Rulare:  python vtuber/eyes_rebuild.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).parent
ASSETS = HERE / "assets"
OUT = HERE / "rig" / "eyes"
W = H = 1024

IRIS = {"L": (410, 427, 52), "R": (607, 424, 52)}
EYE = {"L": (410, 427, 88, 62), "R": (607, 424, 88, 62)}     # elipsa de siguranță
UNDER_LASH = 20
SUPERSAMPLE = 4


# ------------------------------------------------------------------ utilitare
def _load(name: str = "idle.png") -> np.ndarray:
    return np.asarray(Image.open(ASSETS / name).convert("RGBA")).astype(np.int16)


def _components(mask: np.ndarray, min_px: int = 20) -> list[np.ndarray]:
    rest = mask.copy()
    out = []
    while rest.any():
        ys, xs = np.nonzero(rest)
        comp = np.zeros_like(mask)
        stack = [(int(ys[0]), int(xs[0]))]
        comp[stack[0]] = True
        rest[stack[0]] = False
        while stack:
            y, x = stack.pop()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and rest[ny, nx]:
                    rest[ny, nx] = False
                    comp[ny, nx] = True
                    stack.append((ny, nx))
        if comp.sum() >= min_px:
            out.append(comp)
    return out


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    out = mask.copy()
    for _ in range(radius):
        g = out.copy()
        g[1:, :] |= out[:-1, :]
        g[:-1, :] |= out[1:, :]
        g[:, 1:] |= out[:, :-1]
        g[:, :-1] |= out[:, 1:]
        out = g
    return out


def _grow_into(mask: np.ndarray, target: np.ndarray, limit: int) -> np.ndarray:
    """Extinde `mask` în `target`, maximum `limit` pași."""
    out = mask.copy()
    for _ in range(limit):
        g = out.copy()
        g[1:, :] |= out[:-1, :]
        g[:-1, :] |= out[1:, :]
        g[:, 1:] |= out[:, :-1]
        g[:, :-1] |= out[:, 1:]
        new = g & target & ~out
        if not new.any():
            break
        out |= new
    return out


def _soft_disc(size, cx, cy, rx, ry) -> np.ndarray:
    """Disc/elipsă cu margine netedă: desenat la 4×, apoi redus."""
    s = SUPERSAMPLE
    img = Image.new("L", (size[0] * s, size[1] * s), 0)
    ImageDraw.Draw(img).ellipse([(cx - rx) * s, (cy - ry) * s,
                                 (cx + rx) * s, (cy + ry) * s], fill=255)
    return np.asarray(img.resize(size, Image.LANCZOS)).astype(np.float32) / 255.0


def _flood(start_free: np.ndarray, seed: tuple[int, int]) -> np.ndarray:
    out = np.zeros_like(start_free)
    y0, x0 = seed
    if not start_free[y0, x0]:
        ys, xs = np.nonzero(start_free)
        if not len(ys):
            return out
        i = int(np.argmin((ys - y0) ** 2 + (xs - x0) ** 2))
        y0, x0 = int(ys[i]), int(xs[i])
    stack = [(y0, x0)]
    out[y0, x0] = True
    while stack:
        y, x = stack.pop()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < start_free.shape[0] and 0 <= nx < start_free.shape[1] \
                    and start_free[ny, nx] and not out[ny, nx]:
                out[ny, nx] = True
                stack.append((ny, nx))
    return out


# ------------------------------------------------------------------ analiză
def analyse(rgb: np.ndarray, side: str) -> dict:
    cx, cy, _r = IRIS[side]
    ecx, ecy, erx, ery = EYE[side]
    yy, xx = np.mgrid[0:H, 0:W]
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lum = rgb[..., :3].mean(axis=2)
    sat = rgb[..., :3].max(axis=2) - rgb[..., :3].min(axis=2)
    alpha = rgb[..., 3] > 200

    elipsa = (((xx - ecx) / erx) ** 2 + ((yy - ecy) / ery) ** 2) <= 1.0
    # Deschiderea ochiului NU se ghicește din culori: se ia din diferența dintre poza cu
    # ochiul deschis și cea cu ochiul închis — acolo se schimbă exact ochiul și nimic altceva.
    blink_rgb = _load("blink.png")
    diff = np.abs(rgb[..., :3] - blink_rgb[..., :3]).max(axis=2)
    schimbat = (diff > 30) & alpha & elipsa
    comps0 = _components(schimbat, 200)
    ochi = max(comps0, key=lambda c: c.sum()) if comps0 else schimbat
    canvas = Image.fromarray(ochi.astype(np.uint8) * 255, "L").copy()
    ImageDraw.floodfill(canvas, (0, 0), 128)
    ochi = ochi | (np.asarray(canvas) == 0)
    ochi = _dilate(ochi, 1) & elipsa

    # irisul: colorat spre culoarea lui, în interiorul ochiului
    skin = (R > G + 40) & (G > B) & (G > 90)
    geana = (lum < 95) & (sat < 45) & alpha
    if side == "L":
        # irisul albastru e ÎNTUNECAT; umbra albăstruie a sclerii e deschisă (lum>200),
        # deci pragul de luminozitate separă irisul de umbră
        tint = (B > R + 12) & (lum < 165)
    else:
        tint = (R > G + 45) & (R > B + 45) & (lum < 235)
    iris = tint & ochi & ~skin
    comps = _components(iris, 200)
    iris = max(comps, key=lambda c: c.sum()) if comps else iris
    # Elipsa COMPLETĂ: vârful irisului e acoperit de geană, deci nu se poate lua din
    # momentele formei (ar ieși turtit și coborât). Lățimea maximă e vizibilă întreagă,
    # iar baza irisului se vede — deci cercul are raza = jumătatea lățimii și se așază
    # cu baza pe baza văzută; partea de sus intră sub geană.
    ys, xs = np.nonzero(iris)
    ir = float((xs.max() - xs.min()) / 2.0)
    icx = float((xs.max() + xs.min()) / 2.0)
    icy = float(ys.max()) - ir
    irx = iry = ir

    # reflexii: alb pur în elipsa irisului
    inside = (((xx - icx) / max(irx, 1)) ** 2 + ((yy - icy) / max(iry, 1)) ** 2) <= 1.0
    hl = (lum > 235) & (sat < 30) & alpha & inside
    highlights = []
    for c in _components(hl, 20):
        ys2, xs2 = np.nonzero(c)
        hx, hy = float(xs2.mean()), float(ys2.mean())
        highlights.append((hx, hy,
                           max(float(np.sqrt(((xs2 - hx) ** 2).mean()) * 2), 1.8),
                           max(float(np.sqrt(((ys2 - hy) ** 2).mean()) * 2), 1.8),
                           int(c.sum())))
    highlights.sort(key=lambda t: -t[4])

    return {"ochi": ochi, "geana": geana, "iris": iris, "skin": skin,
            "iris_fit": (icx, icy, irx, iry), "highlights": highlights}


# ------------------------------------------------------------------ piese
def build_side(rgb: np.ndarray, side: str) -> tuple[dict[str, Image.Image], tuple]:
    info = analyse(rgb, side)
    ochi, geana, iris = info["ochi"], info["geana"], info["iris"]
    icx, icy, irx, iry = info["iris_fit"]
    yy, xx = np.mgrid[0:H, 0:W]
    lum = rgb[..., :3].mean(axis=2)

    ys, xs = np.nonzero(ochi)
    x0, x1 = int(xs.min()) - 30, int(xs.max()) + 31
    y0, y1 = int(ys.min()) - 30, int(ys.max()) + 31
    bbox = np.zeros((H, W), bool)
    bbox[y0:y1, x0:x1] = True

    ellipse = (((xx - icx) / irx) ** 2 + ((yy - icy) / iry) ** 2) <= 1.0

    # ---------------------------------------------------------------- reflexii
    hl_layers, hl_mask = [], np.zeros((H, W), bool)
    for hx, hy, hrx, hry, _n in info["highlights"][:3]:
        a = _soft_disc((W, H), hx, hy, hrx, hry)
        layer = np.zeros((H, W, 4), np.int16)
        layer[..., :3] = 255
        layer[..., 3] = (a * 255).astype(np.int16)
        hl_layers.append(layer)
        hl_mask |= a > 0.35

    # ---------------------------------------------------------------- geana
    lash_zone = _dilate(ochi, 8) & ~ochi & bbox
    lash_mask = np.zeros((H, W), bool)
    for c in _components(geana & lash_zone, 40):
        ys_c, xs_c = np.nonzero(c)
        # linia ochiului e o bandă; părul are bbox mare și taie tot cadrul
        if c.sum() < 3500 and (xs_c.max() - xs_c.min()) < 200:
            lash_mask |= c
    # părul trece peste colțul ochiului: geana rămâne strict în inelul ochiului
    lash_mask &= _dilate(ochi, 8)

    # ---------------------------------------------------------------- iris
    # irisul fără reflexii: reflexiile sunt piese separate, altfel s-ar dubla.
    # Golurile (reflexii + vârful ascuns sub geană) se umplu prin OGLINDIRE față de
    # centrul irisului — dă o continuare naturală a gradientului, nu pete de medie.
    clean = iris & ~hl_mask & (lum < 200)
    iris_layer = np.zeros((H, W, 4), np.int16)
    iris_layer[clean] = rgb[clean]
    # Golurile se umplu RADIAL: din centrul irisului spre exterior, până la primul pixel
    # curat din aceeași direcție. Irisul desenat are gradient radial, deci continuarea
    # iese natural — oglindirea aducea culoarea de jos (deschisă) în vârf (închis).
    hole = ellipse & ~clean
    ys_h, xs_h = np.nonzero(hole)
    for y, x in zip(ys_h, xs_h):
        dx, dy = (x - icx), (y - icy)
        dist = max(abs(dx), abs(dy), 1.0)
        ux, uy = dx / dist, dy / dist
        for step in range(2, 90):
            sx = int(round(x + ux * step))
            sy = int(round(y + uy * step))
            if not (0 <= sx < W and 0 <= sy < H):
                break
            if clean[sy, sx]:
                iris_layer[y, x, :3] = rgb[sy, sx, :3]
                break
        else:
            iris_layer[y, x, :3] = rgb[int(icy), int(icx), :3]
    if hole.any():
        from PIL import ImageFilter
        tmp = Image.fromarray(np.clip(iris_layer[..., :3], 0, 255).astype(np.uint8), "RGB")
        iris_layer[hole, :3] = np.asarray(tmp.filter(ImageFilter.GaussianBlur(2.0))).astype(np.int16)[hole]
    iris_layer[..., 3] = np.where(ellipse, 255, 0)

    # ---------------------------------------------------------------- alb
    white_in = ochi & ~iris & ~hl_mask
    alb = np.median(rgb[white_in & (lum > 200)][:, :3].reshape(-1, 3), axis=0) \
        if (white_in & (lum > 200)).any() else np.array([250, 250, 252])
    extend = _grow_into(ochi | _dilate(ochi, 1), lash_mask | ochi, UNDER_LASH) & ~ochi
    white_layer = np.zeros((H, W, 4), np.int16)
    white_layer[ochi | extend] = np.append(alb, 255).astype(np.int16)
    # umbra albăstruie desenată se păstrează (face parte din strat)
    # umbra sclerii e albăstruie; marginile anti-aliased ale irisului/geanii nu intră
    shadow = white_in & (lum > 150) & (lum < 245) & (rgb[..., 2] >= rgb[..., 0] + 8)
    white_layer[shadow] = rgb[shadow]
    from PIL import ImageFilter as _IF
    _a = Image.fromarray(((ochi | extend) * 255).astype(np.uint8), "L").filter(_IF.GaussianBlur(0.6))
    white_layer[..., 3] = np.asarray(_a).astype(np.int16)

    # ---------------------------------------------------------------- geana sus
    upper = lash_mask & (yy < icy + iry * 0.35)
    lash_layer = np.zeros((H, W, 4), np.int16)
    lash_layer[upper] = rgb[upper]
    lash_layer[..., 3] = np.where(upper, 255, 0)

    # ---------------------------------------------------------------- pleoapa închisă
    blink = _load("blink.png")
    bl = blink[..., :3].mean(axis=2)
    bs = blink[..., :3].max(axis=2) - blink[..., :3].min(axis=2)
    zone = _dilate(ochi, 10) & bbox
    dark = (bl < 95) & (bs < 45) & (blink[..., 3] > 200) & zone
    lid = np.zeros((H, W), bool)
    for c in _components(dark, 150):
        ys2, xs2 = np.nonzero(c)
        # linia pleoapei stă în interiorul ochiului; părul are bbox mult mai mare
        if c.sum() < 3000 and ys2.min() > ys.min() - 6:
            lid |= c
    lid_layer = np.zeros((H, W, 4), np.int16)
    lid_layer[lid] = blink[lid]
    lid_layer[..., 3] = np.where(lid, 255, 0)

    # ---------------------------------------------------------------- pielea
    ring = _dilate(ochi, 30) & ~_dilate(ochi, 4) & bbox & info["skin"]
    skin_col = np.median(rgb[ring][:, :3].reshape(-1, 3), axis=0) if ring.any() \
        else np.array([252, 186, 158])
    skin_soft = _soft_disc((W, H), icx, icy, irx + 46, iry + 44)
    skin_zone = skin_soft > 0.02
    skin_layer = np.zeros((H, W, 4), np.int16)
    skin_layer[skin_zone] = np.append(skin_col, 255).astype(np.int16)
    skin_layer[..., 3] = (skin_soft * 255).astype(np.int16)

    pieces = {
        "skin_under_eye": skin_layer, "eye_white": white_layer, "iris": iris_layer,
        "upper_lash": lash_layer, "eyelid_closed": lid_layer,
    }
    for i, layer in enumerate(hl_layers, start=1):
        pieces[f"highlight_{i}"] = layer
    out = {n: Image.fromarray(np.clip(v, 0, 255).astype(np.uint8), "RGBA")
           for n, v in pieces.items()}
    return out, (x0, y0, x1, y1)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rgb = _load()
    for side in ("L", "R"):
        pieces, box = build_side(rgb, side)
        for name, img in pieces.items():
            img.save(OUT / f"{name}_{side}.png")
        (OUT / f"box_{side}.txt").write_text(" ".join(str(v) for v in box))
        print(f"{side}: {len(pieces)} piese, cutie {box}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
