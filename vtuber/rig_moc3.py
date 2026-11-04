"""Construiește modelul Live2D complet din straturile din `rig/` și scrie pachetul VTS.

Geometria folosește exact transformările din `rig_preview.py` (aceleași valori din
`rigspec`), dar aplicate pe vertecși — adică ce ajunge în `.moc3`.

Ieșire: `rig/izentric.moc3`, texturile, `model3/cdi3/physics3/exp3`, `vtube.json`.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image

import moc3
from moc3 import Binding, Mesh, Model
from rig_preview import (EXPRESSION_LAYERS, HEAD_DEGREES_PER_DEGREE_Z, HEAD_PX_PER_DEGREE_X,
                         HEAD_PX_PER_DEGREE_Y, IRIS_PX_X, IRIS_PX_Y, LAYER_FILES,
                         ROTATION_CENTER, WARP_ANCHOR, WARP_TOP, load_layers)

HERE = Path(__file__).parent
RIG = HERE / "rig"

ATLAS = 4096
CANVAS = (1024, 1024)

# parametru: (min, max, default)
PARAMS = [
    ("ParamAngleX", -30, 30, 0), ("ParamAngleY", -30, 30, 0), ("ParamAngleZ", -30, 30, 0),
    ("ParamBodyAngleX", -10, 10, 0), ("ParamBodyAngleZ", -10, 10, 0),
    ("ParamEyeLOpen", 0, 1, 1), ("ParamEyeROpen", 0, 1, 1),
    ("ParamEyeBallX", -1, 1, 0), ("ParamEyeBallY", -1, 1, 0),
    ("ParamMouthOpenY", 0, 1, 0), ("ParamBreath", 0, 1, 0),
    ("ParamHairSwayX", -1, 1, 0), ("ParamHornsVis", 0, 1, 1),
    ("ParamExprLaugh", 0, 1, 0), ("ParamExprLove", 0, 1, 0), ("ParamExprSad", 0, 1, 0),
    ("ParamExprShocked", 0, 1, 0), ("ParamExprSus", 0, 1, 0),
]
P = {name: i for i, (name, *_rest) in enumerate(PARAMS)}

# ordinea de desenare: de la spate spre față
DRAW = ["backing", "body", "head", "horns", "eye_L", "eye_R",
        "expr_laugh", "expr_love", "expr_sad", "expr_shocked", "expr_sus",
        "mouth_open", "eyes_closed"]
# numele din .moc3: zonele de click trebuie să aibă exact ID-ul din HitAreas
MESH_ID = {"head": "HitAreaHead", "body": "HitAreaBody"}
GRID = {"horns": 6, "head": 10, "body": 8, "eye_L": 6, "eye_R": 6, "eye_mask_L": 4, "eye_mask_R": 4,
        "eyes_closed": 7, "mouth_open": 5, "backing": 4,
        "expr_laugh": 7, "expr_love": 7, "expr_sad": 7, "expr_shocked": 7, "expr_sus": 7}

# câte chei are fiecare parametru care conduce keyform-uri
KEYS = {
    "ParamAngleX": [-30.0, 0.0, 30.0], "ParamAngleY": [-30.0, 0.0, 30.0],
    "ParamAngleZ": [-30.0, 0.0, 30.0], "ParamBodyAngleX": [-10.0, 0.0, 10.0],
    "ParamEyeBallX": [-1.0, 0.0, 1.0], "ParamEyeBallY": [-1.0, 0.0, 1.0],
    "ParamHairSwayX": [-1.0, 0.0, 1.0], "ParamHornsVis": [0.0, 1.0], "ParamBreath": [0.0, 1.0],
    "ParamEyeLOpen": [1.0, 0.0], "ParamEyeROpen": [1.0, 0.0],
    "ParamMouthOpenY": [0.0, 1.0],
    "ParamExprLaugh": [0.0, 1.0], "ParamExprLove": [0.0, 1.0], "ParamExprSad": [0.0, 1.0],
    "ParamExprShocked": [0.0, 1.0], "ParamExprSus": [0.0, 1.0],
}

HEAD_LAYERS = {"head", "horns", "eye_L", "eye_R", "eye_mask_L", "eye_mask_R", "eyes_closed", "mouth_open",
               *EXPRESSION_LAYERS}


def head_point(x: float, y: float, ax: float, ay: float, az: float, hair: float = 0.0):
    """Rotire în jurul gâtului + warp care scade la zero spre guler (ca în rig_preview)."""
    rad = math.radians(az * HEAD_DEGREES_PER_DEGREE_Z)
    cx, cy = ROTATION_CENTER
    dx, dy = x - cx, y - cy
    x = cx + dx * math.cos(rad) + dy * math.sin(rad)
    y = cy - dx * math.sin(rad) + dy * math.cos(rad)
    ramp = max(0.0, min(1.0, (WARP_ANCHOR - y) / (WARP_ANCHOR - WARP_TOP)))
    x += (ax * HEAD_PX_PER_DEGREE_X + hair * 9.0) * ramp
    y += (-ay * HEAD_PX_PER_DEGREE_Y) * ramp
    return x, y


def body_point(x: float, y: float, bx: float, breath: float):
    """Împinge corpul lateral, tot mai mult spre talie; gulerul (sub 800) stă pe loc."""
    start = 800
    ratio = ((y - start) / (CANVAS[1] - start)) ** 1.5 if y > start else 0.0
    scale = 1.0 + 0.02 * breath
    return x + bx * 1.6 * ratio, y * scale


def _grid(region, cols, rows):
    """Grilă de vertecși peste o regiune din desen, cu UV-urile ei din atlas."""
    x0, y0, w, h, au, av, aw, ah = region
    verts, uvs = [], []
    for r in range(rows + 1):
        for c in range(cols + 1):
            verts.append((x0 + w * c / cols, y0 + h * r / rows))
            uvs.append(((au + aw * c / cols) / ATLAS, (av + ah * r / rows) / ATLAS))
    tris = []
    for r in range(rows):
        for c in range(cols):
            a = r * (cols + 1) + c
            tris += [(a, a + 1, a + cols + 1), (a + 1, a + cols + 2, a + cols + 1)]
    return verts, uvs, tris


def _patch_fill(base, fill):
    """Umple o gaură din păr copiind bucata de păr cea mai potrivită din aceeași poză.

    Se caută offset-ul (dy, dx) care seamănă cel mai bine pe inelul din jurul găurii, apoi
    gaura se umple cu pixelii de la acel offset and the edge e estompat pe 2 px. E o
    potrivire de textură simplă (PatchMatch cu un singur pas), suficientă pentru o zonă
    de ~100 px — o umplere plată se vedea ca o pată.
    """
    import numpy as np

    def dilate(mask, radius):
        out = mask.copy()
        for _ in range(radius):
            grown = out.copy()
            grown[1:, :] |= out[:-1, :]
            grown[:-1, :] |= out[1:, :]
            grown[:, 1:] |= out[:, :-1]
            grown[:, :-1] |= out[:, 1:]
            out = grown
        return out

    alpha = base[..., 3] > 60
    ring = dilate(fill, 4) & ~dilate(fill, 1) & alpha
    ys, xs = np.nonzero(ring)
    if not len(ys):
        return base
    ring_rgb = base[ys, xs, :3].astype(np.float32)
    ring_mean = float(ring_rgb.mean())

    best = None
    for dy in range(-260, 261, 4):
        for dx in range(-260, 261, 4):
            if abs(dy) < 30 and abs(dx) < 30:
                continue
            sy, sx = ys + dy, xs + dx
            ok = (sy >= 0) & (sy < base.shape[0]) & (sx >= 0) & (sx < base.shape[1])
            if ok.mean() < 0.9:
                continue
            cand = base[sy[ok], sx[ok], :3].astype(np.float32)
            if (base[sy[ok], sx[ok], 3] < 60).any():
                continue                      # sursa trebuie să fie păr, nu fundal
            if abs(float(cand.mean()) - ring_mean) > 30:
                continue                      # nu amestecăm părul alb cu cel negru
            score = float(np.abs(cand - ring_rgb[ok]).mean())
            if best is None or score < best[0]:
                best = (score, dy, dx)
    if best is None:
        return base

    _score, dy, dx = best
    src_y = np.arange(base.shape[0])[:, None] + dy
    src_x = np.arange(base.shape[1])[None, :] + dx
    valid = (src_y >= 0) & (src_y < base.shape[0]) & (src_x >= 0) & (src_x < base.shape[1])
    sy = np.clip(src_y, 0, base.shape[0] - 1)
    sx = np.clip(src_x, 0, base.shape[1] - 1)
    patch = base[sy, sx, :3]
    patch_alpha = base[sy, sx, 3]
    take = fill & valid & (patch_alpha > 60)
    base[take, :3] = patch[take]
    base[take, 3] = 255
    # estompare pe 2 px la cusătură, ca să nu se vadă dreptunghiul copiat
    from PIL import ImageFilter

    rgb = base[..., :3].astype(np.float32)
    soft = np.asarray(Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")
                      .filter(ImageFilter.GaussianBlur(1.5))).astype(np.float32)
    edge = take & ~dilate(~take, 0)          # pixeli de umplutură lipiți de margine
    base[edge, :3] = soft[edge].astype(base.dtype)
    return base


def split_horns(layers: dict[str, Image.Image]) -> dict[str, Image.Image]:
    """Scoate coarnele într-un strat propriu și repară părul rămas dedesubt.

    Regula de umplere e geometrică, nu pe culoare: după ce scoatem coarnele, alpha-ul
    capului are găuri. Umplem **doar găurile interioare** (componente transparente care nu
    ating marginea pozei) — adică locurile unde coarnele erau peste păr. Porțiunile care
    ieșeau pe fundal rămân transparente, altfel rămânea silueta coarnelor umplută cu păr.
    Culoarea se copiază de la cel mai apropiat pixel opac din aceeași coloană.
    """
    import numpy as np
    from PIL import ImageDraw

    head = np.array(layers["head"].convert("RGBA")).astype(np.int16)
    r, g, b, al = head[..., 0], head[..., 1], head[..., 2], head[..., 3]
    # prag larg (și pe alpha mic) ca să prindă și conturul închis al coarnelor; pielea are
    # r/g ≈ 1.35, deci nu intră, iar irisul roșu e sub y=250
    horn = (al > 40) & (r > 50) & (r > g * 1.6) & (r > b * 1.6) & (g < 160)
    horn[262:] = False   # baza coarnelor coboară până la ~y 250 în păr
    for _ in range(3):                    # prinde și conturul închis de pe marginea coarnelor
        grown = horn.copy()
        grown[1:, :] |= horn[:-1, :]
        grown[:-1, :] |= horn[1:, :]
        grown[:, 1:] |= horn[:, :-1]
        grown[:, :-1] |= horn[:, 1:]
        horn = grown

    horns = np.zeros_like(head)
    horns[horn] = head[horn]

    base = head.copy()
    base[horn] = 0

    # găurile interioare din alpha (nu ating marginea pozei)
    solid = Image.fromarray((base[..., 3] > 60).astype(np.uint8) * 255, "L").copy()
    ImageDraw.floodfill(solid, (0, 0), 128)
    pocket = np.asarray(solid) == 0
    grown = horn.copy()
    for _ in range(2):
        g2 = grown.copy()
        g2[1:, :] |= grown[:-1, :]
        g2[:-1, :] |= grown[1:, :]
        g2[:, 1:] |= grown[:, :-1]
        g2[:, :-1] |= grown[:, 1:]
        grown = g2
    # Coarnele stau peste păr, deci locul lor trebuie reumplut cu păr. Dar vârfurile lor
    # ies în fundal: ca să nu creăm o cocoașă de păr, umplem doar ce intră în silueta
    # așteptată a părului (închidere morfologică = umple crăpăturile de sub horn).
    def _grow(mask, radius):
        out = mask.copy()
        for _ in range(radius):
            g = out.copy()
            g[1:, :] |= out[:-1, :]
            g[:-1, :] |= out[1:, :]
            g[:, 1:] |= out[:, :-1]
            g[:, :-1] |= out[:, 1:]
            out = g
        return out

    def _shrink(mask, radius):
        return ~_grow(~mask, radius)

    hair = base[..., 3] > 60
    closed = _shrink(_grow(hair, 18), 18)       # silueta fără crăpături
    fill = horn.copy()      # tot locul coarnelor se reumple cu păr (vezi _patch_fill)

    height, width = horn.shape
    if fill.any():
        # fiecare corn separat: își alege offset-ul potrivit (unul stă pe păr negru,
        # celălalt pe păr alb — altfel se copiază părul de pe partea cealaltă)
        seen = np.zeros_like(fill)
        for _ in range(2):
            rest = fill & ~seen
            if not rest.any():
                break
            ys, xs = np.nonzero(rest)
            seed = (int(ys[0]), int(xs[0]))
            comp = np.zeros_like(fill)
            comp[seed] = True
            while True:
                grown = comp.copy()
                grown[1:, :] |= comp[:-1, :]
                grown[:-1, :] |= comp[1:, :]
                grown[:, 1:] |= comp[:, :-1]
                grown[:, :-1] |= comp[:, 1:]
                grown &= fill
                if (grown == comp).all():
                    break
                comp = grown
            seen |= comp
            base = _patch_fill(base, comp)
    out = dict(layers)
    out["head"] = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGBA")
    out["horns"] = Image.fromarray(np.clip(horns, 0, 255).astype(np.uint8), "RGBA")
    return out


PAD = 2


def _padded(tile: Image.Image) -> Image.Image:
    """Bordură de PAD px care repetă marginea — altfel bilingărul ia pixeli din tile-ul vecin."""
    import numpy as np

    arr = np.array(tile)
    h, w = arr.shape[:2]
    out = np.zeros((h + 2 * PAD, w + 2 * PAD, 4), dtype=arr.dtype)
    out[PAD:PAD + h, PAD:PAD + w] = arr
    out[:PAD, PAD:PAD + w] = arr[0]
    out[PAD + h:, PAD:PAD + w] = arr[-1]
    out[:, :PAD] = out[:, PAD:PAD + 1]
    out[:, PAD + w:] = out[:, PAD + w - 1:PAD + w]
    return Image.fromarray(out, "RGBA")


def pack(layers: dict[str, Image.Image]):
    """Așază fiecare strat decupat în atlas (rafturi), întoarce imaginea și regiunile."""
    atlas = Image.new("RGBA", (ATLAS, ATLAS), (0, 0, 0, 0))
    regions, x, y, shelf = {}, 0, 0, 0
    for name in DRAW:
        layer = layers[name]
        box = layer.getchannel("A").getbbox()
        if box is None:
            raise ValueError(f"strat gol: {name}")
        tile = _padded(layer.crop(box))
        w, h = tile.size
        if x + w > ATLAS:
            x, y, shelf = 0, y + shelf, 0
        assert y + h <= ATLAS, f"atlas plin la {name}"
        atlas.paste(tile, (x, y))
        regions[name] = (box[0], box[1], w - 2 * PAD, h - 2 * PAD, x + PAD, y + PAD,
                         w - 2 * PAD, h - 2 * PAD)
        x += w
        shelf = max(shelf, h)
    return atlas, regions


def build(first_level: bool = False):
    layers = split_horns(load_layers(RIG))
    atlas, regions = pack(layers)
    meshes, order = {}, []
    for draw_i, name in enumerate(DRAW):
        cols = rows = GRID[name]
        verts, uvs, tris = _grid(regions[name], cols, rows)
        # ordinea de desenare: DRAW merge din spate în față, iar în .moc3 valoarea mai
        # MARE stă mai în față (Cubism, 0–1000). Cu toate pe 500, ordinea depindea de
        # runtime — în VTS se putea vedea capul peste ochi, adică exact „tăiat".
        kwargs = {"part": 0, "texture": 0,
                  "draw_order": 10.0 * (draw_i + 1)}
        if name in HEAD_LAYERS:
            bindings = [Binding(P["ParamAngleX"], KEYS["ParamAngleX"]),
                        Binding(P["ParamAngleY"], KEYS["ParamAngleY"]),
                        Binding(P["ParamAngleZ"], KEYS["ParamAngleZ"])]
            extra = None
            if name in ("eye_L", "eye_R"):
                extra = (("ParamEyeBallX", IRIS_PX_X), ("ParamEyeBallY", IRIS_PX_Y))
                bindings += [Binding(P["ParamEyeBallX"], KEYS["ParamEyeBallX"]),
                             Binding(P["ParamEyeBallY"], KEYS["ParamEyeBallY"])]
            if name == "head":
                bindings.append(Binding(P["ParamHairSwayX"], KEYS["ParamHairSwayX"]))
            if name == "horns":
                bindings.append(Binding(P["ParamHornsVis"], KEYS["ParamHornsVis"]))
            opacity_param = {"eyes_closed": "ParamEyeLOpen", "mouth_open": "ParamMouthOpenY"}.get(name)
            if name in EXPRESSION_LAYERS:
                opacity_param = "ParamExpr" + name.split("_")[1].capitalize()
            if name == "horns":
                opacity_param = "ParamHornsVis"
            if opacity_param:
                bindings.append(Binding(P[opacity_param], KEYS[opacity_param]))
            frames, opacities = [], []
            names = [_name_of(b.param) for b in bindings]
            for combo in _combos([KEYS[n] for n in names]):
                values = dict(zip(names, combo))
                frame = []
                for vx, vy in verts:
                    hx, hy = head_point(vx, vy, values.get("ParamAngleX", 0.0),
                                        values.get("ParamAngleY", 0.0),
                                        values.get("ParamAngleZ", 0.0),
                                        values.get("ParamHairSwayX", 0.0))
                    if extra:
                        hx += values.get("ParamEyeBallX", 0.0) * extra[0][1]
                        hy += values.get("ParamEyeBallY", 0.0) * extra[1][1]
                    frame.append((hx, hy))
                frames.append(frame)
                op = 1.0
                if opacity_param == "ParamEyeLOpen":
                    op = 1.0 - values[opacity_param]
                elif opacity_param:
                    op = values[opacity_param]
                opacities.append(op)
            kwargs |= {"bindings": bindings, "keyforms": frames, "keyform_opacities": opacities}
        elif name == "body":
            bindings = [Binding(P["ParamBodyAngleX"], KEYS["ParamBodyAngleX"]),
                        Binding(P["ParamBreath"], KEYS["ParamBreath"])]
            frames = []
            for bx, breath in _combos([KEYS["ParamBodyAngleX"], KEYS["ParamBreath"]]):
                frames.append([body_point(vx, vy, bx, breath) for vx, vy in verts])
            kwargs |= {"bindings": bindings, "keyforms": frames,
                       "keyform_opacities": [1.0] * len(frames)}
        meshes[name] = Mesh(MESH_ID.get(name, name), verts, uvs, tris, **kwargs)
        order.append(name)

    model = Model(canvas=CANVAS, parts=["PartCap", "PartCorp"],
                  params=[tuple(p) for p in PARAMS],
                  meshes=[meshes[n] for n in order])
    model.meshes[DRAW.index("eye_L")].part = 0
    return model, atlas


def _name_of(index: int) -> str:
    return PARAMS[index][0]


def _combos(axes):
    """Produs cartezian cu PRIMA axă variind cel mai repede (convenția .moc3)."""
    out = [[]]
    for axis in axes:
        out = [row + [value] for value in axis for row in out]
    return out


def moc3_keyforms(model) -> int:
    total = 0
    for mesh in model.meshes:
        n = len(mesh.keyforms) if mesh.bindings else 1
        total += n
    return total


def main() -> int:
    info = write_bundle(RIG)
    print(f"scris rig/izentric.moc3 ({info['moc3_bytes']} octeti), {info['meshes']} mesh-uri, "
          f"{info['params']} parametri, {info['keyforms']} keyform-uri, atlas {ATLAS}px")
    return 0




EXPRESSIONS = [("Râs", "laugh", "ParamExprLaugh"), ("Îndrăgostit", "love", "ParamExprLove"),
               ("Trist", "sad", "ParamExprSad"), ("Șocat", "shocked", "ParamExprShocked"),
               ("Suspicios", "sus", "ParamExprSus")]

# Comutatoare (accesorii). În VTS nu există hotkey „schimbă parametrul", deci mecanismul
# oficial e expresia-toggle: hotkey de tip ToggleExpression pornește/oprește expresia,
# iar la oprire parametrul revine la valoarea implicită (coarnele apar la loc).
# Sursa: enum HotkeyAction (ToggleExpression=2) + wiki „Expressions".
TOGGLES = [("Coarne ascunse", "hornsoff", {"ParamHornsVis": 0.0})]


def physics_json() -> dict:
    """Două setări de fizică, pe structura din modelul referință (ellot)."""
    settings = [
        {"Id": "PhysicsSetting1", "Name": "Păr",
         "Input": [{"Source": {"Target": "Parameter", "Id": "ParamAngleX"}, "Weight": 100,
                    "Type": "X", "Reflect": False},
                   {"Source": {"Target": "Parameter", "Id": "ParamAngleZ"}, "Weight": 60,
                    "Type": "Angle", "Reflect": False}],
         "Output": [{"Destination": {"Target": "Parameter", "Id": "ParamHairSwayX"},
                     "VertexIndex": 1, "Scale": 6, "Weight": 100, "Type": "Angle",
                     "Reflect": False}],
         "Vertices": [_v(0, 0, 1, 1, 1, 0), _v(0, 10, 0.6, 1, 0.6, 10)],
         "Normalization": _norm(10)},
        {"Id": "PhysicsSetting2", "Name": "Corp",
         "Input": [{"Source": {"Target": "Parameter", "Id": "ParamAngleZ"}, "Weight": 100,
                    "Type": "Angle", "Reflect": False}],
         "Output": [{"Destination": {"Target": "Parameter", "Id": "ParamBodyAngleZ"},
                     "VertexIndex": 1, "Scale": 12, "Weight": 100, "Type": "Angle",
                     "Reflect": False}],
         "Vertices": [_v(0, 0, 1, 1, 1, 0), _v(0, 12, 0.7, 1, 0.7, 12)],
         "Normalization": _norm(10)},
    ]
    return {
        "Version": 3,
        "Meta": {
            "PhysicsSettingCount": len(settings),
            "TotalInputCount": sum(len(s["Input"]) for s in settings),
            "TotalOutputCount": sum(len(s["Output"]) for s in settings),
            "VertexCount": sum(len(s["Vertices"]) for s in settings),
            "Fps": 60,
            "EffectiveForces": {"Gravity": {"X": 0, "Y": -1}, "Wind": {"X": 0, "Y": 0}},
            "PhysicsDictionary": [{"Id": s["Id"], "Name": s["Name"]} for s in settings],
        },
        "PhysicsSettings": settings,
    }


def _v(x, y, mobility, delay, accel, radius):
    return {"Position": {"X": x, "Y": y}, "Mobility": mobility, "Delay": delay,
            "Acceleration": accel, "Radius": radius}


def _norm(limit):
    return {"Position": {"Minimum": -limit, "Default": 0, "Maximum": limit},
            "Angle": {"Minimum": -limit, "Default": 0, "Maximum": limit}}


def model3_json() -> dict:
    return {
        "Version": 3,
        "FileReferences": {
            "Moc": "izentric.moc3",
            "Textures": ["texture_00.png"],
            "Physics": "izentric.physics3.json",
            "DisplayInfo": "izentric.cdi3.json",
            "Expressions": [{"Name": name, "File": f"izentric.{slug}.exp3.json"}
                            for name, slug, _p in EXPRESSIONS]
                           + [{"Name": name, "File": f"izentric.{slug}.exp3.json"}
                              for name, slug, _v in TOGGLES],
        },
        "Groups": [
            {"Target": "Parameter", "Name": "LipSync", "Ids": ["ParamMouthOpenY"]},
            {"Target": "Parameter", "Name": "EyeBlink", "Ids": ["ParamEyeLOpen", "ParamEyeROpen"]},
        ],
        "HitAreas": [{"Id": "HitAreaHead", "Name": "Head"}, {"Id": "HitAreaBody", "Name": "Body"}],
    }


def cdi3_json() -> dict:
    groups = [("ParamGroupFace", "Față", ["ParamAngleX", "ParamAngleY", "ParamAngleZ"]),
              ("ParamGroupEyes", "Ochi", ["ParamEyeLOpen", "ParamEyeROpen", "ParamEyeBallX",
                                          "ParamEyeBallY"]),
              ("ParamGroupMouth", "Gură", ["ParamMouthOpenY"]),
              ("ParamGroupBody", "Corp", ["ParamBodyAngleX", "ParamBodyAngleZ", "ParamBreath"]),
              ("ParamGroupHair", "Păr", ["ParamHairSwayX"]),
              ("ParamGroupAccessories", "Accesorii", ["ParamHornsVis"]),
              ("ParamGroupExpressions", "Expresii", [p for _n, _s, p in EXPRESSIONS])]
    return {
        "Version": 3,
        "Parameters": [{"Id": name, "GroupId": next(g for g, _l, ids in groups if name in ids),
                        "Name": name} for name, *_r in PARAMS],
        "ParameterGroups": [{"Id": g, "GroupId": "", "Name": label} for g, label, _ids in groups],
        "Parts": [{"Id": "PartCap", "Name": "Cap"}, {"Id": "PartCorp", "Name": "Corp"}],
    }


# Setările pe care VTS le ține pentru fiecare model în `<model>.vtube.json` (structura
# copiată din cele două modele de referință: ParameterSettings / Hotkeys / ArtMeshDetails /
# ItemSettings / GeneralSettings / PhysicsSettings).
TRACKING = [
    ("Face Left/Right Rotation", "FaceAngleX", "ParamAngleX", -40, 40, -30, 30, 15),
    ("Face Up/Down Rotation", "FaceAngleY", "ParamAngleY", -30, 30, -30, 30, 0),
    ("Face Lean Rotation", "FaceAngleZ", "ParamAngleZ", -35, 35, -30, 30, 30),
    ("Body Rotation X", "FaceAngleX", "ParamBodyAngleX", -40, 40, -10, 10, 20),
    ("Body Rotation Z", "FaceAngleZ", "ParamBodyAngleZ", -30, 30, -10, 10, 20),
    ("Eye Open Left", "EyeOpenLeft", "ParamEyeLOpen", 0, 1, 0, 1, 10),
    ("Eye Open Right", "EyeOpenRight", "ParamEyeROpen", 0, 1, 0, 1, 10),
    ("Eye X", "EyeRightX", "ParamEyeBallX", -1, 1, -1, 1, 8),
    ("Eye Y", "EyeRightY", "ParamEyeBallY", -1, 1, -1, 1, 8),
    ("Mouth Open", "MouthOpen", "ParamMouthOpenY", 0.03, 0.7, 0, 1, 0),
    ("Auto Breath", "", "ParamBreath", 0, 1, 0, 1, 0),
]


def vtube_json() -> dict:
    """Fișierul de setări VTS (îl rescrie VTS la prima salvare)."""
    model_id = hashlib.md5(b"izentric-vtuber").hexdigest()
    params = [{"Name": name, "Input": inp, "OutputLive2D": out,
               "InputRangeLower": lo, "InputRangeUpper": hi,
               "OutputRangeLower": olo, "OutputRangeUpper": ohi,
               "Smoothing": smooth, "UseBlinking": False,
               "UseBreathing": out == "ParamBreath"}
              for name, inp, out, lo, hi, olo, ohi, smooth in TRACKING]
    params += [{"Name": p, "Input": "", "OutputLive2D": p,
                "InputRangeLower": 0, "InputRangeUpper": 1,
                "OutputRangeLower": 0, "OutputRangeUpper": 1,
                "Smoothing": 20, "UseBlinking": False, "UseBreathing": False}
               for _n, _s, p in EXPRESSIONS]
    hotkeys = [{"Name": name, "Action": "ToggleExpression", "File": f"izentric.{slug}.exp3.json",
                "Trigger": {}}
               for name, slug, _p in EXPRESSIONS]
    hotkeys += [{"Name": name, "Action": "ToggleExpression", "File": f"izentric.{slug}.exp3.json",
                 "Trigger": {}} for name, slug, _v in TOGGLES]
    hotkeys.append({"Name": "Șterge toate expresiile", "Action": "RemoveAllExpressions",
                    "File": "", "Trigger": {}})
    return {
        "Version": 1,
        "Name": "iZentric",
        "ModelID": model_id,
        "FileReferences": {"Icon": "", "Model": "izentric.model3.json",
                           "IdleAnimation": "", "IdleAnimationWhenTrackingLost": ""},
        "ParameterSettings": params,
        "Hotkeys": hotkeys,
        "ArtMeshDetails": {"ArtMeshesExcludedFromPinning": [],
                           "ArtMeshesThatDeleteItemsOnDrop": [],
                           "ArtMeshSceneLightingMultipliers": [],
                           "ArtMeshMultiplyAndScreenColors": []},
        "ItemSettings": {"OnlyMoveWhenPinned": False, "AllowNormalHotkeyTriggers": True,
                         "Multiplier_HeadAngleX": 1.0, "Multiplier_HeadAngleY": 1.0,
                         "Multiplier_HeadAngleZ": 1.0, "Shift_HeadAngleX": 0.0,
                         "Shift_HeadAngleY": 0.0, "Smoothing_HeadAngleX": 15.0,
                         "Smoothing_HeadAngleY": 15.0, "Smoothing_HeadAngleZ": 15.0},
        "GeneralSettings": {"TimeUntilTrackingLostIdleAnimation": 0.0,
                            "WorkshopSharingForbidden": True,
                            "EnableExpressionSaving": False},
        "PhysicsSettings": {"Use": True, "UseLegacyPhysics": False, "Live2DPhysicsFPS": 3,
                            "PhysicsStrength": 50, "WindStrength": 0,
                            "DraggingPhysicsStrength": 49},
    }


def write_bundle(outdir: Path = RIG) -> dict:
    model, atlas = build()
    moc_bytes = moc3.build(model)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "izentric.moc3").write_bytes(moc_bytes)
    atlas.save(outdir / "texture_00.png")
    (outdir / "izentric.model3.json").write_text(
        json.dumps(model3_json(), indent=2, ensure_ascii=False), encoding="utf-8")
    (outdir / "izentric.physics3.json").write_text(
        json.dumps(physics_json(), indent=2, ensure_ascii=False), encoding="utf-8")
    (outdir / "izentric.cdi3.json").write_text(
        json.dumps(cdi3_json(), indent=2, ensure_ascii=False), encoding="utf-8")
    (outdir / "izentric.vtube.json").write_text(
        json.dumps(vtube_json(), indent=2, ensure_ascii=False), encoding="utf-8")
    for name, slug, values in TOGGLES:
        expr = {"Type": "Live2D Expression",
                "Parameters": [{"Id": pid, "Value": float(v), "Blend": "Overwrite"}
                               for pid, v in values.items()],
                "FadeInTime": 0.15, "FadeOutTime": 0.15}
        (outdir / f"izentric.{slug}.exp3.json").write_text(
            json.dumps(expr, indent=2, ensure_ascii=False), encoding="utf-8")
    for name, slug, param in EXPRESSIONS:
        expr = {"Type": "Live2D Expression",
                "Parameters": [{"Id": p, "Value": 1.0 if p == param else 0.0, "Blend": "Overwrite"}
                               for _n, _s, p in EXPRESSIONS],
                "FadeInTime": 0.2, "FadeOutTime": 0.2}
        (outdir / f"izentric.{slug}.exp3.json").write_text(
            json.dumps(expr, indent=2, ensure_ascii=False), encoding="utf-8")
    # pachet gata de pus în VTS: exact fișierele pe care le citește aplicația
    import zipfile

    members = ["izentric.model3.json", "izentric.moc3", "texture_00.png",
               "izentric.physics3.json", "izentric.cdi3.json", "izentric.vtube.json"]
    members += [f"izentric.{slug}.exp3.json" for _n, slug, _p in EXPRESSIONS]
    members += [f"izentric.{slug}.exp3.json" for _n, slug, _v in TOGGLES]
    with zipfile.ZipFile(outdir / "izentric-vts.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for member in members:
            archive.write(outdir / member, member)
    return {"moc3_bytes": len(moc_bytes), "meshes": len(model.meshes),
            "params": len(model.params), "keyforms": moc3_keyforms(model)}


if __name__ == "__main__":
    raise SystemExit(main())
