from __future__ import annotations

import struct

import pytest

import check_moc3
from moc3 import Mesh, Model, build


def _minimal() -> bytes:
    model = Model(canvas=(1024, 1024), parts=["PartHead"])
    model.params = [("ParamAngleX", -30, 30, 0)]
    model.meshes = [Mesh("ArtMesh0",
                         [(0, 0), (1024, 0), (1024, 1024), (0, 1024)],
                         [(0, 0), (1, 0), (1, 1), (0, 1)],
                         [(0, 1, 2), (0, 2, 3)])]
    return build(model)


def test_header_and_section_table_are_sane():
    blob = _minimal()
    assert blob[:4] == b"MOC3"
    assert blob[4] == 3                    # V4.00
    sot = struct.unpack_from("<160I", blob, 64)
    assert sot[0] == 1984                  # tabelul de contoare e primul din corp
    assert sot[1] == 1984 + 128            # apoi canvas info
    used = [v for v in sot if v]
    assert all(used[i] <= used[i + 1] for i in range(len(used) - 1))
    assert max(used) == len(blob)          # ultima secțiune se termină la EOF


def test_keyform_positions_are_counted_in_floats():
    """Core compară mărimea secțiunii cu count * 4; perechile ar da jumătate."""
    blob = _minimal()
    sot = struct.unpack_from("<160I", blob, 64)
    counts = struct.unpack_from("<32I", blob, sot[0])
    assert counts[10] == 8                 # 4 vertecși x 2 coordonate


@pytest.mark.skipif(not check_moc3.available(), reason="live2d-py nu e instalat")
def test_cubism_core_accepts_the_generated_file(tmp_path):
    path = tmp_path / "min.moc3"
    path.write_bytes(_minimal())
    report = check_moc3.core_accepts(str(path))
    assert report["ok"], report.get("error")
    assert report["ids"] == ["ParamAngleX"]
    assert report["canvas"] == [1.0, 1.0]


@pytest.mark.skipif(not check_moc3.available(), reason="live2d-py nu e instalat")
def test_cubism_core_rejects_a_broken_file(tmp_path):
    """Dovada că validatorul nu e orb: același fișier, stricat, e respins."""
    blob = bytearray(_minimal())
    blob[4] = 9
    path = tmp_path / "broken.moc3"
    path.write_bytes(bytes(blob))
    assert not check_moc3.core_accepts(str(path))["ok"]
