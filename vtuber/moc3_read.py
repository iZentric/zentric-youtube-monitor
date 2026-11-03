"""Cititor .moc3 — folosește același tabel de secțiuni ca scriitorul (moc3.py)."""

from __future__ import annotations

import struct

from moc3 import SECTION_LAYOUT

_ELEM = {"i32": ("<i", 4), "f32": ("<f", 4), "i16": ("<h", 2), "u8": ("<B", 1),
         "bool": ("<i", 4), "str64": (None, 64), "runtime": (None, 8)}


class Moc3:
    def __init__(self, path: str):
        self.blob = open(path, "rb").read()
        self.sot = struct.unpack_from("<160I", self.blob, 64)
        self.counts = struct.unpack_from("<32I", self.blob, self.sot[0])
        self.sections = {}
        for k, (name, kind, _ci, _al) in enumerate(SECTION_LAYOUT):
            self.sections[name] = self._read(k, kind)

    def _read(self, k, kind):
        start = self.sot[2 + k]
        count = self.counts[SECTION_LAYOUT[k][2]]
        fmt, size = _ELEM[kind]
        if kind == "str64":
            return [self.blob[start + i * 64:start + i * 64 + 64].split(b"\0")[0].decode("utf-8", "replace")
                    for i in range(count)]
        if kind == "runtime":
            return count
        n = count
        if kind == "u8":
            return list(self.blob[start:start + n])
        return list(struct.unpack_from("<%d%s" % (n, fmt[1]), self.blob, start))

    # --- accesoriere comode -------------------------------------------------
    def get(self, name):
        return self.sections[name]

    def parameters(self):
        return [{"id": i, "min": self.get("parameter.min_values")[k],
                 "max": self.get("parameter.max_values")[k],
                 "default": self.get("parameter.default_values")[k]}
                for k, i in enumerate(self.get("parameter.ids"))]

    def art_meshes(self):
        ids = self.get("art_mesh.ids")
        tex = self.get("art_mesh.texture_indices")
        nvert = self.get("art_mesh.position_index_counts")
        mask_b = self.get("art_mesh.mask_begin_indices")
        mask_c = self.get("art_mesh.mask_counts")
        uv_begin = self.get("art_mesh.uv_begin_indices")
        flags = self.get("art_mesh.drawable_flags")
        uvs = self.get("uv.xys")
        orders = self.get("art_mesh_keyform.draw_orders")
        out = []
        for k, name in enumerate(ids):
            b = uv_begin[k]
            v = nvert[k]
            uv = uvs[b:b + 2 * v]
            xs = uv[0::2] or [0.0]
            ys = uv[1::2] or [0.0]
            out.append({
                "id": name, "texture": tex[k], "vertices": v,
                "uv": (min(xs), min(ys), max(xs), max(ys)),
                "draw_order": orders[k] if k < len(orders) else None,
                "masked": bool(mask_c[k]),
                "mask_count": mask_c[k], "mask_begin": mask_b[k],
                "flags": flags[k] if k < len(flags) else None,
            })
        return out

    def parts(self):
        return self.get("part.ids")

    def deformers(self):
        return list(zip(self.get("deformer.ids"), self.get("deformer.types")))
