"""Poarta de runtime: modelul trebuie să treacă prin **Cubism Core** (SDK-ul oficial).

Testele din `test_ochi.py` verifică desenul; acesta verifică binarul. Un `.moc3`
scris de noi poate fi perfect coerent pentru cititorul propriu și totuși să crape
în VTube Studio — exact asta s-a întâmplat (Core ieșea cu SIGSEGV din cauza
`draw_order_group.min/max_draw_orders`). Fără testul ăsta, regresia e invizibilă.

Rulează: `python -m pytest vtuber/test_moc3_core.py -q`
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_moc3  # noqa: E402
import validate_moc3  # noqa: E402

BUILD_DIRS = [HERE / "rig", HERE / "rig-2048", HERE / "rig-safe"]


def _builds():
    return [d for d in BUILD_DIRS if (d / "izentric.moc3").exists()]


@pytest.mark.parametrize("build", _builds(), ids=lambda p: p.name)
def test_core_accepta_moc3(build: Path):
    """Cubism Core trebuie să încarce fișierul: orice altceva = crash în VTS."""
    report = check_moc3.core_accepts(str(build / "izentric.moc3"))
    assert report["available"], "live2d-py lipsește — testul nu poate verifica nimic"
    assert report["ok"], f"Core a respins {build.name}: {report.get('error')}"
    assert report["params"] >= 18, f"prea puțini parametri: {report['params']}"


@pytest.mark.parametrize("build", _builds(), ids=lambda p: p.name)
def test_indici_in_limite(build: Path):
    """Niciun index din fișier să nu iasă din secțiunea lui (validator semantic)."""
    m = validate_moc3.M(str(build / "izentric.moc3"))
    rele = {nume: bad for nume, bad in validate_moc3.checks(m) if bad}
    assert not rele, f"verificări picate în {build.name}: {rele}"


def test_ordine_de_desanare_in_sentinel():
    """Regresia care a crăpat VTS: min/max trebuie 500/499 (dovedit prin bisecție)."""
    from moc3 import SECTION_LAYOUT

    for build in _builds():
        m = validate_moc3.M(str(build / "izentric.moc3"))
        for name, want in (("draw_order_group.min_draw_orders", 500),
                           ("draw_order_group.max_draw_orders", 499)):
            assert m.sec[name] == [want], f"{build.name}: {name} = {m.sec[name]} (trebuie {want})"
        assert len(SECTION_LAYOUT) == 99


def test_varianta_simpla_are_ochii_in_cap():
    """Varianta „simplu" nu are mesh-uri de ochi: ochii stau în stratul capului.

    Dacă apar din nou mesh-uri eye_L/eye_R acolo, revine riscul ca un strat de
    deasupra să acopere un ochi (pata albă văzută în VTube Studio).
    """
    from pathlib import Path

    rig = Path(__file__).resolve().parent / "rig-safe"
    moc = rig / "izentric.moc3"
    if not moc.exists():
        pytest.skip("build-ul rig-safe nu există")
    m = validate_moc3.M(str(moc))
    ids = m.sec["art_mesh.ids"]
    assert "eye_L" not in ids and "eye_R" not in ids, f"mesh-uri de ochi în rig-safe: {ids}"

    # capul trebuie să conțină culoarea irisului (altfel ochiul e alb)
    from PIL import Image
    import numpy as np
    head = np.asarray(Image.open(rig / "head.png").convert("RGBA"))
    albastru = (head[..., 2] > head[..., 0] + 30) & (head[..., 2] > 90)
    rosu = (head[..., 0] > head[..., 2] + 40) & (head[..., 0] > 90) & (head[..., 1] < 90)
    assert int(albastru.sum()) > 1500, f"iris albastru lipsește din cap ({int(albastru.sum())} px)"
    assert int(rosu.sum()) > 1500, f"iris roșu lipsește din cap ({int(rosu.sum())} px)"
