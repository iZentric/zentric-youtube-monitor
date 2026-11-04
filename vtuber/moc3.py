"""Scriitor .moc3 (Live2D Cubism 4.00) — port după structura verificată a formatului.

Layout: header 64 B, tabel de offset-uri (SOT) 160 x uint32, corp de la 0x7C0,
secțiuni aliniate la 64 B. Sursa structurii: MOC3_FORMAT.md (MIT, stretchiestudio)
+ verificat pe cele două modele de referință (moc3 v4.2, Core 6.0.1 le încarcă).

Pozițiile se scriu normalizat: (px - origine) / ppu, cu ppu = max(canvas).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

MAGIC = b"MOC3"
HEADER_SIZE = 64
SOT_COUNT = 160
COUNT_INFO_SIZE = 128
CANVAS_INFO_SIZE = 64
BODY_OFFSET = 1984
ALIGN = 64
RUNTIME_UNIT_SIZE = 8
STR_SIZE = 64
V4_00 = 3

I32, F32, I16, U8, BOOL, STR64, RUNTIME = "i32", "f32", "i16", "u8", "bool", "str64", "runtime"

# (nume, tip, index în tabelul de contoare, aliniere) — ordinea e impusă de format
SECTION_LAYOUT = [
    ("part.runtime_space", RUNTIME, 0, ALIGN),
    ("part.ids", STR64, 0, 0),
    ("part.keyform_binding_band_indices", I32, 0, ALIGN),
    ("part.keyform_begin_indices", I32, 0, ALIGN),
    ("part.keyform_counts", I32, 0, ALIGN),
    ("part.visibles", BOOL, 0, ALIGN),
    ("part.enables", BOOL, 0, ALIGN),
    ("part.parent_part_indices", I32, 0, ALIGN),

    ("deformer.runtime_space", RUNTIME, 1, ALIGN),
    ("deformer.ids", STR64, 1, 0),
    ("deformer.keyform_binding_band_indices", I32, 1, ALIGN),
    ("deformer.visibles", BOOL, 1, ALIGN),
    ("deformer.enables", BOOL, 1, ALIGN),
    ("deformer.parent_part_indices", I32, 1, ALIGN),
    ("deformer.parent_deformer_indices", I32, 1, ALIGN),
    ("deformer.types", I32, 1, ALIGN),
    ("deformer.specific_indices", I32, 1, ALIGN),

    ("warp_deformer.keyform_binding_band_indices", I32, 2, ALIGN),
    ("warp_deformer.keyform_begin_indices", I32, 2, ALIGN),
    ("warp_deformer.keyform_counts", I32, 2, ALIGN),
    ("warp_deformer.vertex_counts", I32, 2, ALIGN),
    ("warp_deformer.rows", I32, 2, ALIGN),
    ("warp_deformer.cols", I32, 2, ALIGN),

    ("rotation_deformer.keyform_binding_band_indices", I32, 3, ALIGN),
    ("rotation_deformer.keyform_begin_indices", I32, 3, ALIGN),
    ("rotation_deformer.keyform_counts", I32, 3, ALIGN),
    ("rotation_deformer.base_angles", F32, 3, ALIGN),

    ("art_mesh.runtime_space_0", RUNTIME, 4, ALIGN),
    ("art_mesh.runtime_space_1", RUNTIME, 4, ALIGN),
    ("art_mesh.runtime_space_2", RUNTIME, 4, ALIGN),
    ("art_mesh.runtime_space_3", RUNTIME, 4, ALIGN),
    ("art_mesh.ids", STR64, 4, 0),
    ("art_mesh.keyform_binding_band_indices", I32, 4, ALIGN),
    ("art_mesh.keyform_begin_indices", I32, 4, ALIGN),
    ("art_mesh.keyform_counts", I32, 4, ALIGN),
    ("art_mesh.visibles", BOOL, 4, ALIGN),
    ("art_mesh.enables", BOOL, 4, ALIGN),
    ("art_mesh.parent_part_indices", I32, 4, ALIGN),
    ("art_mesh.parent_deformer_indices", I32, 4, ALIGN),
    ("art_mesh.texture_indices", I32, 4, ALIGN),
    ("art_mesh.drawable_flags", U8, 4, ALIGN),
    ("art_mesh.position_index_counts", I32, 4, ALIGN),
    ("art_mesh.uv_begin_indices", I32, 4, ALIGN),
    ("art_mesh.position_index_begin_indices", I32, 4, ALIGN),
    ("art_mesh.vertex_counts", I32, 4, ALIGN),
    ("art_mesh.mask_begin_indices", I32, 4, ALIGN),
    ("art_mesh.mask_counts", I32, 4, ALIGN),

    ("parameter.runtime_space", RUNTIME, 5, ALIGN),
    ("parameter.ids", STR64, 5, 0),
    ("parameter.max_values", F32, 5, ALIGN),
    ("parameter.min_values", F32, 5, ALIGN),
    ("parameter.default_values", F32, 5, ALIGN),
    ("parameter.repeats", BOOL, 5, ALIGN),
    ("parameter.decimal_places", I32, 5, ALIGN),
    ("parameter.keyform_binding_begin_indices", I32, 5, ALIGN),
    ("parameter.keyform_binding_counts", I32, 5, ALIGN),

    ("part_keyform.draw_orders", F32, 6, ALIGN),

    ("warp_deformer_keyform.opacities", F32, 7, ALIGN),
    ("warp_deformer_keyform.keyform_position_begin_indices", I32, 7, ALIGN),

    ("rotation_deformer_keyform.opacities", F32, 8, ALIGN),
    ("rotation_deformer_keyform.angles", F32, 8, ALIGN),
    ("rotation_deformer_keyform.origin_xs", F32, 8, ALIGN),
    ("rotation_deformer_keyform.origin_ys", F32, 8, ALIGN),
    ("rotation_deformer_keyform.scales", F32, 8, ALIGN),
    ("rotation_deformer_keyform.reflect_xs", BOOL, 8, ALIGN),
    ("rotation_deformer_keyform.reflect_ys", BOOL, 8, ALIGN),

    ("art_mesh_keyform.opacities", F32, 9, ALIGN),
    ("art_mesh_keyform.draw_orders", F32, 9, ALIGN),
    ("art_mesh_keyform.keyform_position_begin_indices", I32, 9, ALIGN),

    ("keyform_position.xys", F32, 10, ALIGN),
    ("keyform_binding_index.indices", I32, 11, ALIGN),
    ("keyform_binding_band.begin_indices", I32, 12, ALIGN),
    ("keyform_binding_band.counts", I32, 12, ALIGN),
    ("keyform_binding.keys_begin_indices", I32, 13, ALIGN),
    ("keyform_binding.keys_counts", I32, 13, ALIGN),
    ("keys.values", F32, 14, ALIGN),
    ("uv.xys", F32, 15, ALIGN),
    ("position_index.indices", I16, 16, ALIGN),
    ("drawable_mask.art_mesh_indices", I32, 17, ALIGN),
    ("draw_order_group.object_begin_indices", I32, 18, ALIGN),
    ("draw_order_group.object_counts", I32, 18, ALIGN),
    ("draw_order_group.object_total_counts", I32, 18, ALIGN),
    ("draw_order_group.min_draw_orders", I32, 18, ALIGN),
    ("draw_order_group.max_draw_orders", I32, 18, ALIGN),
    ("draw_order_group_object.types", I32, 19, ALIGN),
    ("draw_order_group_object.indices", I32, 19, ALIGN),
    ("draw_order_group_object.group_indices", I32, 19, ALIGN),
    ("glue.runtime_space", RUNTIME, 20, ALIGN),
    ("glue.ids", STR64, 20, 0),
    ("glue.keyform_binding_band_indices", I32, 20, ALIGN),
    ("glue.keyform_begin_indices", I32, 20, ALIGN),
    ("glue.keyform_counts", I32, 20, ALIGN),
    ("glue.art_mesh_index_as", I32, 20, ALIGN),
    ("glue.art_mesh_index_bs", I32, 20, ALIGN),
    ("glue.info_begin_indices", I32, 20, ALIGN),
    ("glue.info_counts", I32, 20, ALIGN),
    ("glue_info.weights", F32, 21, ALIGN),
    ("glue_info.position_indices", I16, 21, ALIGN),
    ("glue_keyform.intensities", F32, 22, ALIGN),
]

COUNT_NAMES = ["parts", "deformers", "warp_deformers", "rotation_deformers", "art_meshes",
               "parameters", "part_keyforms", "warp_deformer_keyforms",
               "rotation_deformer_keyforms", "art_mesh_keyforms", "keyform_positions",
               "keyform_binding_indices", "keyform_binding_bands", "keyform_bindings",
               "keys", "uvs", "position_indices", "drawable_masks", "draw_order_groups",
               "draw_order_group_objects", "glues", "glue_infos", "glue_keyforms"]


@dataclass
class Binding:
    """O dimensiune de keyform: parametrul care o conduce + valorile cheie."""
    param: int
    keys: list[float]


@dataclass
class Mesh:
    """Un art mesh. `verts`/`uvs` în pixeli, respectiv 0..1 din textura sursă.

    Cu `bindings`, mesh-ul are len(product(keys)) keyforms, în ordinea
    mixed-radix a legăturilor (prima legătură se schimbă cel mai repede).
    """
    id: str
    verts: list[tuple[float, float]]
    uvs: list[tuple[float, float]]
    tris: list[tuple[int, int, int]]
    part: int = 0
    texture: int = 0
    opacity: float = 1.0
    masks: list[int] = field(default_factory=list)   # indici de art mesh folosiți ca mască
    bindings: list[Binding] = field(default_factory=list)
    keyforms: list[list[tuple[float, float]]] = field(default_factory=list)
    keyform_opacities: list[float] = field(default_factory=list)
    # ordinea de desenare: 0–1000, valoarea mai MARE stă mai în față (Cubism)
    draw_order: float = 500.0


@dataclass
class Model:
    canvas: tuple[float, float]
    parts: list[str] = field(default_factory=lambda: ["PartRoot"])
    params: list[tuple[str, float, float, float]] = field(default_factory=lambda: [("ParamOpacity", 0, 1, 1)])
    meshes: list[Mesh] = field(default_factory=list)


def _f32(v):
    return struct.pack("<f", float(v))


def _i32(v):
    return struct.pack("<i", int(v))


def _i16(v):
    return struct.pack("<h", int(v))


def _pad(buf, align):
    rem = len(buf) % align
    if rem:
        buf += b"\0" * (align - rem)
    return buf


def _write_section(buf, kind, data, count):
    if kind == RUNTIME:
        return buf + b"\0" * (count * RUNTIME_UNIT_SIZE)
    if kind == STR64:
        for s in data:
            raw = s.encode("utf-8")
            if len(raw) >= STR_SIZE:
                raise ValueError(f"id prea lung: {s}")
            buf += raw + b"\0" * (STR_SIZE - len(raw))
        return buf
    if kind == I32:
        return buf + b"".join(_i32(v) for v in data)
    if kind == F32:
        return buf + b"".join(_f32(v) for v in data)
    if kind == I16:
        return buf + b"".join(_i16(v) for v in data)
    if kind == U8:
        return buf + bytes(int(v) & 0xFF for v in data)
    if kind == BOOL:
        return buf + b"".join(_i32(1 if v else 0) for v in data)
    raise ValueError(kind)


def build(m: Model) -> bytes:
    """Întoarce octeții unui .moc3 v4.00 valid pentru Cubism Core."""
    cw, ch = m.canvas
    ppu = max(cw, ch)
    ox, oy = cw / 2.0, ch / 2.0

    def nrm(x, y):
        return ((x - ox) / ppu, (y - oy) / ppu)

    n_mesh, n_part, n_param = len(m.meshes), len(m.parts), len(m.params)
    counts = [0] * 23
    counts[0], counts[4], counts[5] = n_part, n_mesh, n_param
    counts[6] = n_part
    counts[17] = 1                      # drawable masks (SDK cere total > 0)
    counts[18] = 1                      # un singur draw order group
    counts[19] = n_mesh

    # Legăturile se ordonează pe parametri: fiecare parametru deține un interval
    # contiguu din tabelul de bindings (altfel parameter.keyform_binding_begin minte).
    bindings, bind_pos = [], {}
    for p in range(n_param):
        for mi, mesh in enumerate(m.meshes):
            for bi, b in enumerate(mesh.bindings):
                if b.param == p:
                    bind_pos[(mi, bi)] = len(bindings)
                    bindings.append(b)

    band_begin, band_count, binding_index = [], [], []
    for mi, mesh in enumerate(m.meshes):
        if mesh.bindings:
            band_begin.append(len(binding_index))
            band_count.append(len(mesh.bindings))
            binding_index += [bind_pos[(mi, bi)] for bi in range(len(mesh.bindings))]
        else:
            band_begin.append(0)
            band_count.append(0)
    for _ in range(n_part):             # benzi nule pentru părți
        band_begin.append(0)
        band_count.append(0)
    counts[11] = len(binding_index)
    counts[12] = len(band_begin)
    counts[13] = len(bindings)
    counts[14] = sum(len(b.keys) for b in bindings)

    pos, uv, idx = [], [], []
    uv_begin, idx_begin = [], []
    mesh_kf_begin, mesh_kf_count = [], []
    kf_pos_begin, kf_opac, kf_draw = [], [], []
    for mesh in m.meshes:
        assert len(mesh.uvs) == len(mesh.verts), mesh.id
        uv_begin.append(len(uv))
        idx_begin.append(len(idx))
        frames = mesh.keyforms if mesh.bindings else [mesh.verts]
        opacities = mesh.keyform_opacities if mesh.bindings else [mesh.opacity]
        assert len(opacities) == len(frames), mesh.id
        mesh_kf_begin.append(len(kf_opac))
        mesh_kf_count.append(len(frames))
        for frame, op in zip(frames, opacities):
            assert len(frame) == len(mesh.verts), mesh.id
            kf_pos_begin.append(len(pos))
            for x, y in frame:
                nx, ny = nrm(x, y)
                pos += [nx, ny]
            kf_opac.append(op)
            kf_draw.append(mesh.draw_order)
        for u, v in mesh.uvs:
            uv += [u, v]
        for t in mesh.tris:
            idx += list(t)
    counts[9] = len(kf_opac)
    counts[10] = len(pos)               # floate (x,y intercalate), nu perechi
    counts[15] = len(uv)
    counts[16] = len(idx)

    s = {}
    s["part.ids"] = list(m.parts)
    s["part.keyform_binding_band_indices"] = [n_mesh + j for j in range(n_part)]
    s["part.keyform_begin_indices"] = list(range(n_part))
    s["part.keyform_counts"] = [1] * n_part
    s["part.visibles"] = [True] * n_part
    s["part.enables"] = [True] * n_part
    s["part.parent_part_indices"] = [-1] * n_part
    s["part_keyform.draw_orders"] = [500.0] * n_part

    s["art_mesh.ids"] = [mesh.id for mesh in m.meshes]
    s["art_mesh.keyform_binding_band_indices"] = list(range(n_mesh))
    s["art_mesh.keyform_begin_indices"] = mesh_kf_begin
    s["art_mesh.keyform_counts"] = mesh_kf_count
    s["art_mesh.visibles"] = [True] * n_mesh
    s["art_mesh.enables"] = [True] * n_mesh
    s["art_mesh.parent_part_indices"] = [mesh.part for mesh in m.meshes]
    s["art_mesh.parent_deformer_indices"] = [-1] * n_mesh
    s["art_mesh.texture_indices"] = [mesh.texture for mesh in m.meshes]
    s["art_mesh.drawable_flags"] = [4] * n_mesh
    s["art_mesh.position_index_counts"] = [len(mesh.verts) for mesh in m.meshes]
    s["art_mesh.uv_begin_indices"] = uv_begin
    s["art_mesh.position_index_begin_indices"] = idx_begin
    s["art_mesh.vertex_counts"] = [len(mesh.tris) * 3 for mesh in m.meshes]
    mask_begin, mask_count, mask_list = [], [], []
    for mesh in m.meshes:
        mask_begin.append(len(mask_list))
        mask_count.append(len(mesh.masks))
        mask_list += mesh.masks
    s["art_mesh.mask_begin_indices"] = mask_begin if mask_list else [0] * n_mesh
    s["art_mesh.mask_counts"] = mask_count
    counts[17] = len(mask_list) or 1          # SDK cere total > 0

    s["parameter.ids"] = [p[0] for p in m.params]
    s["parameter.max_values"] = [p[2] for p in m.params]
    s["parameter.min_values"] = [p[1] for p in m.params]
    s["parameter.default_values"] = [p[3] for p in m.params]
    s["parameter.repeats"] = [False] * n_param
    s["parameter.decimal_places"] = [1] * n_param
    p_begin, p_count = [], []
    for pi in range(n_param):
        owned = [k for k, b in enumerate(bindings) if b.param == pi]
        p_begin.append(owned[0] if owned else 0)
        p_count.append(len(owned))
    s["parameter.keyform_binding_begin_indices"] = p_begin
    s["parameter.keyform_binding_counts"] = p_count

    s["art_mesh_keyform.opacities"] = kf_opac
    s["art_mesh_keyform.draw_orders"] = kf_draw
    s["art_mesh_keyform.keyform_position_begin_indices"] = kf_pos_begin

    s["keyform_position.xys"] = pos
    s["keyform_binding_index.indices"] = binding_index
    s["keyform_binding_band.begin_indices"] = band_begin
    s["keyform_binding_band.counts"] = band_count
    keys_begin, keys_count, key_values = [], [], []
    for b in bindings:
        keys_begin.append(len(key_values))
        keys_count.append(len(b.keys))
        key_values += list(b.keys)
    s["keyform_binding.keys_begin_indices"] = keys_begin
    s["keyform_binding.keys_counts"] = keys_count
    s["keys.values"] = key_values
    s["uv.xys"] = uv
    s["position_index.indices"] = idx
    s["drawable_mask.art_mesh_indices"] = mask_list or [-1]
    s["draw_order_group.object_begin_indices"] = [0]
    s["draw_order_group.object_counts"] = [n_mesh]
    s["draw_order_group.object_total_counts"] = [n_mesh]
    # ATENȚIE: `min_draw_orders`/`max_draw_orders` trebuie să fie 500 / 499.
    # Orice altă pereche (ex. min/max calculate din ordinele reale) face Cubism Core
    # să CRAPE la încărcare (SIGSEGV, nu mesaj de eroare) — dovedit prin bisecție:
    #   w1 (toate ordinele egale) → ok; w2 (500/510/520, min=500 max=520) → crash;
    #   w2 cu min=500 max=499 → ok. Modelul real ellot.moc3 are tot 500 / 499.
    # Verificare: `python vtuber/check_moc3.py <fisier.moc3>`.
    s["draw_order_group.min_draw_orders"] = [500]
    s["draw_order_group.max_draw_orders"] = [499]
    s["draw_order_group_object.types"] = [0] * n_mesh
    s["draw_order_group_object.indices"] = [n_mesh - 1 - i for i in range(n_mesh)]
    s["draw_order_group_object.group_indices"] = [-1] * n_mesh

    body = b""
    sot = []
    sot.append(BODY_OFFSET + len(body))
    body += b"".join(_i32(c) for c in counts) + b"\0" * (COUNT_INFO_SIZE - len(counts) * 4)
    sot.append(BODY_OFFSET + len(body))
    body += _f32(ppu) + _f32(ox) + _f32(oy) + _f32(cw) + _f32(ch) + b"\0"
    body += b"\0" * (CANVAS_INFO_SIZE - 5 * 4 - 1)

    for name, kind, _ci, align in SECTION_LAYOUT:
        if align:
            body = _pad(body, align)
        sot.append(BODY_OFFSET + len(body))
        data = s.get(name, [])
        count = counts[_ci] if kind == RUNTIME else len(data)
        body = _write_section(body, kind, data, count)

    body = _pad(body, ALIGN)
    sot.append(BODY_OFFSET + len(body))   # quad_transforms (0 warp deformeri)

    sot += [sot[-1]] * (SOT_COUNT - len(sot))
    out = MAGIC + bytes([V4_00, 0]) + b"\0" * (HEADER_SIZE - 6)
    out += b"".join(struct.pack("<I", v) for v in sot)
    out += b"\0" * (BODY_OFFSET - len(out))
    out += body
    return _pad(out, ALIGN)
