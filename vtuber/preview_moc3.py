"""Randează ce spune `.moc3`-ul: ia vertecșii keyform-urilor și deformează textura.

Nu folosește rig_preview: dacă poza iese corectă, geometria din fișier e corectă.
Rulare: python vtuber/preview_moc3.py  →  rig/verificare-moc3.png
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from moc3_read import Moc3

HERE = Path(__file__).parent
RIG = HERE / "rig"
W = H = 1024


def _frame(moc: Moc3, atlas: Image.Image, values: dict[str, float], scale: int = 3) -> Image.Image:
    meta = moc.parameters()
    params = [p["id"] for p in meta]
    defaults = {p["id"]: p["default"] for p in meta}      # ce face modelul când nu i se spune nimic
    values = {**defaults, **values}
    band_begin = moc.get("keyform_binding_band.begin_indices")
    band_count = moc.get("keyform_binding_band.counts")
    bind_idx = moc.get("keyform_binding_index.indices")
    keys_begin = moc.get("keyform_binding.keys_begin_indices")
    keys_count = moc.get("keyform_binding.keys_counts")
    keys = moc.get("keys.values")
    mesh_band = moc.get("art_mesh.keyform_binding_band_indices")
    bind_begin = moc.get("parameter.keyform_binding_begin_indices")
    bind_count = moc.get("parameter.keyform_binding_counts")
    kf_begin = moc.get("art_mesh.keyform_begin_indices")
    kf_count = moc.get("art_mesh.keyform_counts")
    kf_pos = moc.get("art_mesh_keyform.keyform_position_begin_indices")
    positions = moc.get("keyform_position.xys")
    opac = moc.get("art_mesh_keyform.opacities")
    uvs = moc.get("uv.xys")
    uv_begin = moc.get("art_mesh.uv_begin_indices")
    vert_counts = moc.get("art_mesh.position_index_counts")
    indices = moc.get("position_index.indices")
    idx_begin = moc.get("art_mesh.position_index_begin_indices")
    order = moc.get("art_mesh_keyform.draw_orders")

    # legătură → ce parametru o conduce
    owner = {}
    for pi, pid in enumerate(params):
        for j in range(bind_count[pi]):
            owner[bind_begin[pi] + j] = pid

    meshes = []
    for k in range(len(mesh_band)):
        band = mesh_band[k]
        binds = [bind_idx[band_begin[band] + j] for j in range(band_count[band])]
        index = 0
        stride = 1
        for b in binds:                     # prima legătură variază cel mai repede
            pid = owner.get(b, "")
            key_values = [keys[keys_begin[b] + j] for j in range(keys_count[b])]
            wanted = values.get(pid, 0.0)
            best = min(range(len(key_values)), key=lambda j: abs(key_values[j] - wanted))
            index += best * stride
            stride *= len(key_values)
        f = kf_begin[k] + min(index, kf_count[k] - 1)
        start = kf_pos[f]
        n = vert_counts[k]
        verts = [(positions[start + 2 * i] * W + W / 2, positions[start + 2 * i + 1] * H + H / 2)
                 for i in range(n)]
        uv_s = uv_begin[k]
        uv = [(uvs[uv_s + 2 * i] * atlas.width, uvs[uv_s + 2 * i + 1] * atlas.height)
              for i in range(n)]
        meshes.append((order[f], opac[f], verts, uv, indices, idx_begin[k], k))
    meshes.sort(key=lambda m: m[0])

    return _draw(atlas, meshes, scale)


def _draw(atlas: Image.Image, meshes, scale: int = 3) -> Image.Image:
    """Compune mesh-urile: fiecare celulă e mapată biliniar din atlas în canvas."""
    import numpy as np

    src_px = np.asarray(atlas.convert("RGBA")).astype(np.float32)
    sh, sw = src_px.shape[:2]
    # randare la rezoluție mare apoi micșorare: altfel marginile ies dințate și par defecte
    # de model când de fapt e doar eșantionarea previzualizării
    SW, SH = W * scale, H * scale
    canvas = np.zeros((SH, SW, 4), dtype=np.float32)

    for _order, opacity, verts, uv, _tri, _ib, k in meshes:
        if opacity <= 0.01:
            continue
        cols = int(round(len(verts) ** 0.5)) - 1
        # acumulare cu medie: celulele vecine se suprapun pe muchia comună, iar „ultima
        # câștigă" lăsa o linie dreaptă vizibilă peste ochi/păr (defect de randare)
        layer = np.zeros((SH, SW, 4), dtype=np.float32)
        weight = np.zeros((SH, SW, 1), dtype=np.float32)
        big = [(x * scale, y * scale) for x, y in verts]
        for r in range(cols):
            for c in range(cols):
                a = r * (cols + 1) + c
                dst = [big[a], big[a + 1], big[a + cols + 2], big[a + cols + 1]]
                src = [uv[a], uv[a + 1], uv[a + cols + 2], uv[a + cols + 1]]
                _map_quad(layer, weight, src_px, sh, sw, dst, src)
        weight[weight == 0] = 1.0
        layer = layer / weight
        alpha = layer[..., 3:4] * opacity
        layer[..., 3:4] = alpha
        canvas = canvas * (1 - alpha / 255.0) + layer * (alpha / 255.0)
    out = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8))
    return out.resize((W, H), Image.LANCZOS) if scale > 1 else out


def _map_quad(dst_img, weight, src_px, sh, sw, dst, src):
    """Umple patrulaterul destinație cu textura din patrulaterul sursă (afin pe 2 triunghiuri)."""
    import numpy as np

    for corners in ((0, 1, 3), (1, 2, 3)):
        i0, i1, i2 = corners
        d = np.array([dst[i0], dst[i1], dst[i2]], dtype=np.float64)
        s = np.array([src[i0], src[i1], src[i2]], dtype=np.float64)
        hh, ww = dst_img.shape[:2]
        x0, y0 = int(max(0, np.floor(d[:, 0].min()))), int(max(0, np.floor(d[:, 1].min())))
        x1, y1 = int(min(ww, np.ceil(d[:, 0].max()) + 1)), int(min(hh, np.ceil(d[:, 1].max()) + 1))
        if x1 <= x0 or y1 <= y0:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1]
        px = np.stack([xx + 0.5, yy + 0.5], axis=-1)
        a = np.array([d[1] - d[0], d[2] - d[0]]).T          # dst = d0 + A·(u,v)
        try:
            inv = np.linalg.inv(a)
        except np.linalg.LinAlgError:
            continue
        rel = px - d[0]
        u = rel[..., 0] * inv[0, 0] + rel[..., 1] * inv[0, 1]
        v = rel[..., 0] * inv[1, 0] + rel[..., 1] * inv[1, 1]
        inside = (u >= -0.002) & (v >= -0.002) & (u + v <= 1.002)
        if not inside.any():
            continue
        sx = s[0, 0] + u * (s[1, 0] - s[0, 0]) + v * (s[2, 0] - s[0, 0])
        sy = s[0, 1] + u * (s[1, 1] - s[0, 1]) + v * (s[2, 1] - s[0, 1])
        # UV-ul e în „muchia stângă a texelului"; eșantionarea biliniară de aici are
        # centrele texelilor la coordonate întregi, deci -0.5. Fără el, tot ce e tăiat
        # (iris, gene, gura) iese spălăcit cu jumătate de pixel — exact ca o tăietură.
        sx = np.clip(sx - 0.5, 0, sw - 1)
        sy = np.clip(sy - 0.5, 0, sh - 1)
        ix, iy = np.floor(sx).astype(int), np.floor(sy).astype(int)
        fx, fy = (sx - ix)[..., None], (sy - iy)[..., None]
        ix1, iy1 = np.clip(ix + 1, 0, sw - 1), np.clip(iy + 1, 0, sh - 1)
        top = src_px[iy, ix] * (1 - fx) + src_px[iy, ix1] * fx
        bottom = src_px[iy1, ix] * (1 - fx) + src_px[iy1, ix1] * fx
        sample = top * (1 - fy) + bottom * fy
        region = dst_img[y0:y1, x0:x1]
        w = weight[y0:y1, x0:x1]
        region[inside] += sample[inside]
        w[inside] += 1.0


def main() -> int:
    moc = Moc3(str(RIG / "izentric.moc3"))
    atlas = Image.open(RIG / "texture_00.png").convert("RGBA")
    shots = [("repaus", {}), ("cap stânga", {"ParamAngleX": -30}), ("cap dreapta", {"ParamAngleX": 30}),
             ("clipit", {"ParamEyeLOpen": 0, "ParamEyeROpen": 0}), ("gură", {"ParamMouthOpenY": 1}),
             ("râs", {"ParamExprLaugh": 1}),
             ("pr. stânga", {"ParamEyeBallX": -1}), ("pr. dreapta", {"ParamEyeBallX": 1}),
             ("înclinat", {"ParamAngleZ": 30})]
    tiles = []
    for label, values in shots:
        frame = _frame(moc, atlas, values)
        background = Image.new("RGBA", (W, H), (24, 24, 28, 255))
        background.alpha_composite(frame)
        draw = ImageDraw.Draw(background)
        draw.text((16, H - 28), label, fill=(255, 255, 255, 255))
        tiles.append(background.resize((384, 384), Image.LANCZOS))

    sheet = Image.new("RGBA", (384 * 3, 384 * 3), (0, 0, 0, 255))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % 3) * 384, (i // 3) * 384))
    out = RIG / "verificare-moc3.png"
    sheet.save(out)
    print(f"scris {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
