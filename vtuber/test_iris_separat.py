"""Teste pentru varianta cu iris separat: se mișcă doar irisul, sclera rămâne fundal.

Ce prind concret:
- irisul decupat iese din elipsa lui sau are franjuri albe la margine;
- în `head.png` a rămas iris (atunci când se uită într-o parte se vede „ochi sub ochi");
- modelul nu mișcă irisul deloc sau îl mișcă împreună cu sclera.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import eyes_rebuild as E
from moc3_read import Moc3
import preview_moc3 as P

RIG = Path(__file__).parent / "rig-iris"
FITS = {"L": (416.5, 438.5, 42.5), "R": (599.0, 430.0, 42.0)}


def _ellipse(cx, cy, r, h=E.H, w=E.W, scale=1.0):
    yy, xx = np.mgrid[0:h, 0:w]
    return ((xx - cx) ** 2 + (yy - cy) ** 2) <= (r * scale) ** 2


@pytest.fixture(scope="module")
def drawing():
    return E._load("idle.png")


def test_irisul_e_taiat_exact_pe_elipsa(drawing):
    """Nici un pixel opacity nu are voie să iasă din elipsă (decupaj grosier = „tăiat prost")."""
    for side, (cx, cy, r) in FITS.items():
        alpha = np.asarray(Image.open(RIG / f"iris_{side}.png").convert("RGBA"))[..., 3] > 128
        inside = _ellipse(cx, cy, r + 1.0)
        outside = int((alpha & ~inside).sum())
        assert outside <= 40, f"iris_{side}: {outside} px în afara elipsei"
        # elipsa trebuie umplută, nu găurită (gaură = se vede sclera prin iris);
        # ultimii 2 px sunt marginea anti-aliasată, unde alfa scade firesc
        hole = int((_ellipse(cx, cy, r - 2.0) & ~alpha).sum())
        assert hole == 0, f"iris_{side}: marginea nu e plină ({hole} px lipsă)"


def test_irisul_nu_are_franjuri_albe(drawing):
    """Marginea irisului vine din desen, nu din albul din jur: altfel apare un halo alb."""
    for side, (cx, cy, r) in FITS.items():
        rgb = np.asarray(Image.open(RIG / f"iris_{side}.png").convert("RGBA")).astype(int)
        rim = _ellipse(cx, cy, r, scale=1.0) & ~_ellipse(cx, cy, r, scale=0.90)
        lum = rgb[..., :3].mean(2)[rim]
        assert lum.mean() < 190, f"iris_{side}: marginea e albă (lum {lum.mean():.0f})"


def test_capul_nu_mai_are_iris_in_elipsa_lui(drawing):
    """Ce rămâne în `head` sub iris trebuie să fie sclera: altfel, la privire, rămâne o verigă."""
    head = np.asarray(Image.open(RIG / "head.png").convert("RGBA")).astype(int)
    for side, (cx, cy, r) in FITS.items():
        zone = _ellipse(cx, cy, r, scale=0.90)
        patch = head[zone][:, :3]
        lum = patch.mean(1)
        assert np.percentile(lum, 20) > 195, f"capul {side}: zonă întunecată sub iris"
        blue = (patch[:, 2] - patch[:, 0]) > 30
        assert blue.mean() < 0.02, f"capul {side}: a rămas albastru de iris"


def test_modelul_mișcă_irisul_dar_nu_sclera():
    """ParamEyeBallX ±1 mută irisul cu ~2×6 px; conturul ochiului (geana) rămâne pe loc."""
    moc = Moc3(str(RIG / "izentric.moc3"))
    atlas = Image.open(RIG / "texture_00.png").convert("RGBA")
    ids = [m["id"] for m in moc.art_meshes()]
    assert "iris_L" in ids and "iris_R" in ids, "mesh-urile de iris lipsesc din .moc3"

    def frame(x):
        return np.asarray(P._frame(moc, atlas, {"ParamEyeBallX": x}, scale=1).convert("RGB")).astype(int)

    left, centre, right = frame(-1.0), frame(0.0), frame(1.0)
    box = (325, 365, 472, 488)          # ochiul stâng, din geometria desenului
    x0, y0, x1, y1 = box

    def centroid(img, pick):
        sub = img[y0:y1, x0:x1]
        mask = pick(sub)
        ys, xs = np.nonzero(mask)
        assert len(xs), "nu s-a găsit irisul în randare"
        return xs.mean() + x0, ys.mean() + y0

    blue = lambda s: (s[..., 2] - s[..., 0] > 40) & (s[..., 2] > 60)
    move = centroid(right, blue)[0] - centroid(left, blue)[0]
    assert 8.0 <= move <= 14.0, f"irisul se mișcă {move:.1f} px, ar trebui ~12"

    # tot ce e în afara irisului (geana, sclera, pielea) trebuie să fie identic
    yy, xx = np.mgrid[0:E.H, 0:E.W]
    away = np.ones((E.H, E.W), bool)
    for cx, cy, r in FITS.values():
        away &= ~(((xx - cx) ** 2 + (yy - cy) ** 2) <= (r + 8) ** 2)
    box_mask = np.zeros((E.H, E.W), bool)
    box_mask[300:560, 300:720] = True
    fixed = away & box_mask
    drift = int((np.abs(right - left).max(2)[fixed] > 8).sum())
    assert drift <= 12, f"sclera/geana se mișcă odată cu irisul ({drift} px)"


def test_la_repaus_modelul_arată_ca_desenul(drawing):
    """head + iris puse la loc trebuie să dea desenul (în iris), altfel tăierea se vede."""
    head = Image.open(RIG / "head.png").convert("RGBA").copy()
    for side in ("L", "R"):
        head.alpha_composite(Image.open(RIG / f"iris_{side}.png").convert("RGBA"))
    got = np.asarray(head).astype(int)
    want = np.asarray(Image.open(E.ASSETS / "idle.png").convert("RGBA")).astype(int)
    for side, (cx, cy, r) in FITS.items():
        zone = _ellipse(cx, cy, r, scale=0.95) & (want[..., 3] > 128)
        diff = np.abs(got[..., :3] - want[..., :3]).max(2)[zone]
        bad = float((diff > 40).mean())
        assert bad < 0.03, f"iris_{side}: {bad:.1%} pixeli diferiți de desen"
