"""Validator semantic pentru .moc3 — prinde ce nu prinde un cititor tolerant.

Rulează pe orice fișier:

    python vtuber/validate_moc3.py fisier.moc3 [altul.moc3 ...]

Verifică exact lucrurile pe care Cubism Core le citește ca indici: dacă un index
iese din secțiune, Core nu zice „invalid", ci crapă (SIGSEGV). Un fișier valid
(model real) trebuie să treacă toate verificările — altfel verificarea e greșită.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from moc3 import SECTION_LAYOUT  # noqa: E402


class M:
    def __init__(self, path: str):
        self.path, self.b = path, Path(path).read_bytes()
        self.sot = struct.unpack_from("<160I", self.b, 64)
        self.counts = list(struct.unpack_from("<32i", self.b, self.sot[0]))
        self.sec = {}
        for k, (name, kind, _ci, _al) in enumerate(SECTION_LAYOUT):
            start = self.sot[2 + k]
            n = self.counts[SECTION_LAYOUT[k][2]]
            if kind == "str64":
                v = [self.b[start + i * 64:start + i * 64 + 64].split(b"\0")[0].decode("utf-8", "replace")
                     for i in range(n)]
            elif kind == "runtime":
                v = [0] * n
            elif kind == "u8":
                v = list(self.b[start:start + n])
            elif kind == "bool":
                v = list(struct.unpack_from(f"<{n}i", self.b, start))
            else:
                v = list(struct.unpack_from("<%d%s" % (n, {"i32": "i", "f32": "f", "i16": "h"}[kind]),
                                            self.b, start))
            self.sec[name] = v


def checks(m: M):
    s, c, out = m.sec, m.counts, []
    nmesh, npar = c[4], c[5]

    def add(name, bad):
        out.append((name, bad))

    # 1. art_mesh: keyform-uri în limite
    beg, cnt = s["art_mesh.keyform_begin_indices"], s["art_mesh.keyform_counts"]
    add("art_mesh keyform_begin+count ≤ total",
        [(k, beg[k], cnt[k]) for k in range(nmesh) if beg[k] + cnt[k] > c[9]])

    # 2/3. NU se verifică „Σ verts×keyforms" sau „uv_begin+2*verts": pe modelul real
    # ellot.moc3 ambele ies „greșite" (keyform-urile partajează poziții, iar contoarele
    # nu sunt în unitatea presupusă) — deci presupunerea era a mea, nu a formatului.
    # Un validator care pică pe un fișier valid e mai rău decât lipsa lui.

    # 4. indicii de poziție sunt în limitele mesh-ului lor
    verts = s["art_mesh.vertex_counts"]
    pib, pic = s["art_mesh.position_index_begin_indices"], s["art_mesh.position_index_counts"]
    idx = s["position_index.indices"]
    bad = []
    for k in range(nmesh):
        if pib[k] + pic[k] > c[16]:
            bad.append(("secțiune", k, pib[k], pic[k], c[16]))
            continue
        seg = idx[pib[k]:pib[k] + pic[k]]
        if seg and (max(seg) >= verts[k] or min(seg) < 0):
            bad.append(("index", k, min(seg), max(seg), verts[k]))
    add("position_index în limitele mesh-ului", bad)

    # 5. parametri → legături
    pb, pc = s["parameter.keyform_binding_begin_indices"], s["parameter.keyform_binding_counts"]
    add("parameter binding_begin+count ≤ total",
        [(k, pb[k], pc[k]) for k in range(npar) if pb[k] + pc[k] > c[13]])

    # 6. benzi → indici de legătură
    bb, bc = s["keyform_binding_band.begin_indices"], s["keyform_binding_band.counts"]
    add("band begin+count ≤ binding indices",
        [(k, bb[k], bc[k]) for k in range(c[12]) if bb[k] + bc[k] > c[11]])

    # 7. legături → chei
    kb, kc = s["keyform_binding.keys_begin_indices"], s["keyform_binding.keys_counts"]
    add("binding keys_begin+count ≤ keys",
        [(k, kb[k], kc[k]) for k in range(c[13]) if kb[k] + kc[k] > c[14]])

    # 8. band index per mesh/part în limitele benzilor
    bad = []
    for sec, n in (("art_mesh.keyform_binding_band_indices", nmesh),
                   ("part.keyform_binding_band_indices", c[0]),
                   ("deformer.keyform_binding_band_indices", c[1])):
        vals = s[sec]
        bad += [(sec, k, vals[k]) for k in range(n) if vals[k] >= c[12] or vals[k] < -1]
    add("band index valid", bad)

    # 9. măști
    mb, mc = s["art_mesh.mask_begin_indices"], s["art_mesh.mask_counts"]
    add("mask begin+count ≤ drawable_masks",
        [(k, mb[k], mc[k]) for k in range(nmesh) if mc[k] and mb[k] + mc[k] > c[17]])

    # 10. grupuri de ordine de desenare
    ogb, ogc = s["draw_order_group.object_begin_indices"], s["draw_order_group.object_counts"]
    add("draw_order_group begin+count ≤ objects",
        [(k, ogb[k], ogc[k]) for k in range(c[18]) if ogb[k] + ogc[k] > c[19]])

    # 11. canvas nenul (Core împarte la el)
    canvas = struct.unpack_from("<2f", m.b, m.sot[1])
    add("canvas > 0", [] if canvas[0] > 0 and canvas[1] > 0 else [canvas])

    # 12. contoare care nu pot fi 0
    add("contoare obligatorii > 0",
        [n for n, i in (("parts", 0), ("art_meshes", 4), ("parameters", 5),
                        ("drawable_masks", 17), ("draw_order_groups", 18)) if c[i] <= 0])
    return out


def main(argv: list[str]) -> int:
    rc = 0
    for path in argv:
        m = M(path)
        print(f"\n=== {path}  (v{m.b[4]}, {len(m.b)} B, "
              f"{m.counts[4]} mesh, {m.counts[5]} parametri)")
        bad_any = False
        for name, bad in checks(m):
            if bad:
                bad_any = True
                print(f"  FAIL {name}: {bad[:4]}{' …' if len(bad) > 4 else ''}")
            else:
                print(f"  ok   {name}")
        if bad_any:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
