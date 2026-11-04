"""Teste pentru ochi — prind exact defectele reclamate: bucată de iris detașată și
geană mâncată din zona neagră de deasupra ochilor.

Rulează pe straturile deja construite (``vtuber/rig``), deci e rapid. Pentru rebuild:
``python vtuber/rig_build.py && python vtuber/rig_moc3.py``.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import rig_build as rb
import rig_preview as rp

RIG = Path(__file__).resolve().parent / "rig"
DESEN = Path(__file__).resolve().parent / "assets" / "idle.png"


@pytest.fixture(scope="module")
def desen() -> np.ndarray:
    raw = np.asarray(Image.open(DESEN).convert("RGBA")).astype(np.uint8)
    return np.asarray(Image.fromarray(rb.despill(raw), "RGBA"))


@pytest.fixture(scope="module")
def straturi() -> dict[str, Image.Image]:
    return rp.load_layers(RIG)


@pytest.fixture(scope="module")
def repaus(straturi) -> np.ndarray:
    return np.asarray(rp.render(straturi)).astype(int)


def _opening(straturi) -> np.ndarray:
    out = np.zeros((1024, 1024), bool)
    for side in ("L", "R"):
        out |= np.asarray(straturi[f"eye_{side}"].getchannel("A")) > 24
    return out


def piele_desen(desen: np.ndarray) -> np.ndarray:
    r, g, b = desen[..., 0].astype(int), desen[..., 1].astype(int), desen[..., 2].astype(int)
    return (r > g + 40) & (g > b) & (g > 90)


def _lash(desen: np.ndarray) -> np.ndarray:
    lum = desen[..., :3].mean(axis=2)
    sat = desen[..., :3].astype(np.int16)
    sat = sat.max(axis=2) - sat.min(axis=2)
    return (lum < 95) & (sat < 75) & (desen[..., 3] > 200)


def test_repausul_reproduce_desenul(repaus, desen):
    """Nici un pixel pus prost: la repaus randarea = desenul, pixel cu pixel."""
    delta = np.abs(repaus[..., :3] - desen[..., :3].astype(int)).max(axis=2)
    rau = int((delta > 2).sum())
    assert rau == 0, f"{rau} pixeli diferă de desen (max {int(delta.max())})"


@pytest.mark.parametrize("side", ["L", "R"])
def test_globul_e_o_singura_bucata(straturi, side):
    """Fără bucăți detașate de glob (reclamația „bucată de iris albastru detașată")."""
    ball = np.asarray(straturi[f"eye_{side}"].getchannel("A")) > 24
    rest = ball.copy()
    total, biggest = int(ball.sum()), 0
    while rest.any():
        ys, xs = np.nonzero(rest)
        comp = rb._blob_at(rest, (int(xs[0]), int(ys[0])))
        biggest = max(biggest, int(comp.sum()))
        rest &= ~comp
    assert total - biggest < 5, f"eye_{side}: {total - biggest} px detașați de glob"


@pytest.mark.parametrize("side", ["L", "R"])
def test_geana_nu_se_misca_cu_privirea(straturi, desen, repaus, side):
    """Banda neagră de lângă ochi trebuie să rămână identică la orice privire."""
    band = _lash(desen) & rb._dilate(_opening(straturi), 8) & ~_opening(straturi)
    assert band.sum() > 500, "nu am găsit banda de geană — testul nu ar dovedi nimic"
    for ex, ey in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1)):
        miscat = np.asarray(rp.render(straturi, eyeball_x=ex, eyeball_y=ey)).astype(int)
        delta = np.abs(miscat[..., :3] - repaus[..., :3]).max(axis=2)
        schimbati = int((delta[band] > 6).sum())
        assert schimbati < 30, f"{side}: {schimbati} px de geană se mișcă la privirea {ex}/{ey}"


@pytest.mark.parametrize("side", ["L", "R"])
def test_capul_nu_mai_are_iris(straturi, desen, side):
    """Iris-fantomă în `head` = „bucata detașată" care apare când se mișcă globul."""
    head = np.asarray(straturi["head"].convert("RGBA")).astype(int)
    ball = np.asarray(straturi[f"eye_{side}"].getchannel("A")) > 24
    # doar inelul de sub marginea globului poate fi descoperit când se mișcă privirea
    zona = ball & ~rb._erode(ball, 6)
    r, g, b = head[..., 0], head[..., 1], head[..., 2]
    skin = (r > g + 40) & (g > b) & (g > 90)
    albastru = (b > r + 60) & (b > 70) & (b < 210)      # irisul, nu umbra albăstruie a sclerii
    rosu = (r > g + 60) & (r > b + 60) & (g < 70)
    ramas = int(((albastru | rosu) & ~skin & zona & (head[..., 3] > 200)).sum())
    assert ramas < 20, f"eye_{side}: {ramas} px de iris au rămas în cap"


@pytest.mark.parametrize("side", ["L", "R"])
def test_clipitul_acopera_ochiul(straturi, side):
    """Clipit complet opac: nici un pixel din glob nu rămâne la vedere."""
    ball = np.asarray(straturi[f"eye_{side}"].getchannel("A")) > 24
    clipit = np.asarray(straturi["eyes_closed"].getchannel("A")) > 200
    liber = int((ball & ~rb._dilate(clipit, 0)).sum())
    assert liber < 20, f"eye_{side}: {liber} px din glob rămân neacoperiți la clipit"


def test_privirea_nu_descopera_iris_sau_piele(straturi, desen):
    """Când globul alunecă, în urmă nu are voie să apară iris rămas sau o pată de piele."""
    repaus_px = np.asarray(rp.render(straturi)).astype(int)
    r, g, b = desen[..., 0].astype(int), desen[..., 1].astype(int), desen[..., 2].astype(int)
    piele = (r > g + 40) & (g > b) & (g > 90)
    albastru = (b > r + 60) & (b > 70) & (b < 210)      # irisul, nu umbra albăstruie a sclerii
    for ex, ey in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1)):
        miscat = np.asarray(rp.render(straturi, eyeball_x=ex, eyeball_y=ey)).astype(int)
        delta = np.abs(miscat[..., :3] - repaus_px[..., :3]).max(axis=2)
        descoperit = delta > 12
        iris_d = (desen[..., :3].astype(np.int16).max(axis=2)
                  - desen[..., :3].astype(np.int16).min(axis=2)) > 55
        nu_era_acolo = ~piele_desen(desen) & ~iris_d
        rau = int((descoperit & (piele | albastru) & nu_era_acolo).sum())
        assert rau < 30, f"privirea {ex}/{ey} descoperă {rau} px de iris/piele"


# ---------------------------------------------------------------- ce se vede în VTS
# Straturile pot fi perfecte și tot să arate greșit după ce trec prin `.moc3` (atlas,
# UV-uri, poziția mesh-ului). De aceea se verifică și cadrul randat din `.moc3`.


@pytest.fixture(scope="module")
def cadru_moc3() -> np.ndarray:
    from moc3_read import Moc3
    import preview_moc3 as pv

    moc = Moc3(str(RIG / "izentric.moc3"))
    atlas = Image.open(RIG / "texture_00.png").convert("RGBA")
    frame = pv._frame(moc, atlas, {}, scale=1)   # 1:1, fără micșorare care ascunde defecte
    canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    canvas.alpha_composite(frame)
    return np.asarray(canvas.convert("RGB")).astype(int)


def test_moc3_arata_ca_desenul_in_ochi(cadru_moc3, desen):
    """Cadrul din `.moc3` (ce vede VTS) trebuie să semene cu desenul în zona ochilor."""
    zona = (slice(350, 520), slice(330, 700))
    delta = np.abs(cadru_moc3[zona] - desen[zona][..., :3].astype(int)).max(axis=2)
    peste40 = int((delta > 40).sum())
    peste120 = int((delta > 120).sum())
    medie = float(delta.mean())
    assert peste40 < 150, f"{peste40} px diferă tare în ochi (medie {medie:.2f})"
    assert peste120 < 20, f"{peste120} px complet alți în ochi"
    assert medie < 1.0, f"diferență medie prea mare în ochi: {medie:.2f}"


@pytest.mark.parametrize("side", ["L", "R"])
def test_irisul_din_moc3_e_la_locul_lui(cadru_moc3, desen, side):
    """Centrul irisului în randare trebuie să fie unde e în desen (±3 px)."""
    def masca(img):
        r, g, b = img[..., 0], img[..., 1], img[..., 2]
        if side == "L":
            return (b > r + 60) & (b > 70)
        return (r > g + 60) & (r > b + 60) & (g < 70)

    def centru(m):
        ys, xs = np.nonzero(m)
        return (float(xs.mean()), float(ys.mean())), int(len(xs))

    cd, nd = centru(masca(desen[..., :3].astype(int)))
    cm, nm = centru(masca(cadru_moc3))
    d = max(abs(cd[0] - cm[0]), abs(cd[1] - cm[1]))
    assert d < 3.0, f"{side}: irisul e la ({cm[0]:.0f},{cm[1]:.0f}) în loc de ({cd[0]:.0f},{cd[1]:.0f})"
    assert abs(nd - nm) / nd < 0.30, f"{side}: altă formă de iris ({nd} vs {nm} px)"


@pytest.mark.parametrize("side", ["L", "R"])
def test_sclera_din_cap_e_goala(straturi, side):
    """Sub glob, capul trebuie să fie scleră (alb), nu iris — altfel iese la iveală."""
    head = np.asarray(straturi["head"].convert("RGBA")).astype(int)
    ball = np.asarray(straturi[f"eye_{side}"].getchannel("A")) > 24
    miez = rb._erode(ball, 3)
    lum = head[..., :3].mean(axis=2)
    sat = head[..., :3].astype(np.int16)
    sat = sat.max(axis=2) - sat.min(axis=2)
    colorat = (sat > 60) & (lum < 200) & miez & (head[..., 3] > 200)
    r, g, b = head[..., 0], head[..., 1], head[..., 2]
    skin = (r > g + 40) & (g > b) & (g > 90)
    ramas = int((colorat & ~skin).sum())
    assert ramas < 200, f"eye_{side}: {ramas} px colorați sub glob în cap"


# ------------------------------------------------- ce vede VTS: geometrie și ordine


def test_moc3_se_potriveste_cu_straturile(cadru_moc3_straturi):
    """`.moc3` nu are voie să difere de straturi: prinde UV greșit (jumătate de texel),
    plasă strâmbă, atlas greșit."""
    moc3, straturi = cadru_moc3_straturi
    d = np.abs(moc3 - straturi).max(axis=2)
    peste40 = int((d > 40).sum())
    assert peste40 < 400, f"{peste40} px diferă între .moc3 și straturi (max {int(d.max())})"


@pytest.fixture(scope="module")
def cadru_moc3_straturi(cadru_moc3):
    from pathlib import Path as _P
    import rig_preview as _rp
    sus = np.asarray(_rp.render(_rp.load_layers(RIG)).convert("RGB")).astype(int)
    return cadru_moc3, sus


def test_ordinea_de_desenare_e_explicita():
    """În .moc3, valoarea mai MARE stă mai în față; la valori egale ordinea e nedefinită
    (în VTS poate ieși capul peste ochi = „tăiat"). Toate mesh-urile trebuie să aibă
    ordini distincte, crescătoare în ordinea în care le-așez eu."""
    from moc3_read import Moc3
    moc = Moc3(str(RIG / "izentric.moc3"))
    opac = moc.get("art_mesh_keyform.opacities")
    draws = moc.get("art_mesh_keyform.draw_orders")
    kf_begin = moc.get("art_mesh.keyform_begin_indices")
    orders = [draws[b] for b in kf_begin]
    assert len(set(orders)) == len(orders), f"ordini de desenare duplicate: {sorted(orders)}"
    assert orders == sorted(orders), f"ordinea nu crește: {orders}"
    assert min(orders) >= 0 and max(orders) <= 1000, f"în afara 0–1000: {orders}"
    assert len(opac) == len(draws)
