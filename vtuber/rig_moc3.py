"""Construiește modelul Live2D complet din straturile din `rig/` și scrie pachetul VTS.

Geometria folosește exact transformările din `rig_preview.py` (aceleași valori din
`rigspec`), dar aplicate pe vertecși — adică ce ajunge în `.moc3`.

Ieșire: `rig/izentric.moc3`, texturile, `model3/cdi3/physics3/exp3`, `vtube.json`.
"""

from __future__ import annotations

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
    ("ParamHairSwayX", -1, 1, 0),
    ("ParamExprLaugh", 0, 1, 0), ("ParamExprLove", 0, 1, 0), ("ParamExprSad", 0, 1, 0),
    ("ParamExprShocked", 0, 1, 0), ("ParamExprSus", 0, 1, 0),
]
P = {name: i for i, (name, *_rest) in enumerate(PARAMS)}

# ordinea de desenare: de la spate spre față
DRAW = ["backing", "body", "head", "eye_L", "eye_R",
        "expr_laugh", "expr_love", "expr_sad", "expr_shocked", "expr_sus",
        "mouth_open", "eyes_closed"]
# numele din .moc3: zonele de click trebuie să aibă exact ID-ul din HitAreas
MESH_ID = {"head": "HitAreaHead", "body": "HitAreaBody"}
GRID = {"head": 10, "body": 8, "eye_L": 6, "eye_R": 6, "eye_mask_L": 4, "eye_mask_R": 4,
        "eyes_closed": 7, "mouth_open": 5, "backing": 4,
        "expr_laugh": 7, "expr_love": 7, "expr_sad": 7, "expr_shocked": 7, "expr_sus": 7}

# câte chei are fiecare parametru care conduce keyform-uri
KEYS = {
    "ParamAngleX": [-30.0, 0.0, 30.0], "ParamAngleY": [-30.0, 0.0, 30.0],
    "ParamAngleZ": [-30.0, 0.0, 30.0], "ParamBodyAngleX": [-10.0, 0.0, 10.0],
    "ParamEyeBallX": [-1.0, 0.0, 1.0], "ParamEyeBallY": [-1.0, 0.0, 1.0],
    "ParamHairSwayX": [-1.0, 0.0, 1.0], "ParamBreath": [0.0, 1.0],
    "ParamEyeLOpen": [1.0, 0.0], "ParamEyeROpen": [1.0, 0.0],
    "ParamMouthOpenY": [0.0, 1.0],
    "ParamExprLaugh": [0.0, 1.0], "ParamExprLove": [0.0, 1.0], "ParamExprSad": [0.0, 1.0],
    "ParamExprShocked": [0.0, 1.0], "ParamExprSus": [0.0, 1.0],
}

HEAD_LAYERS = {"head", "eye_L", "eye_R", "eye_mask_L", "eye_mask_R", "eyes_closed", "mouth_open",
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


def pack(layers: dict[str, Image.Image]):
    """Așază fiecare strat decupat în atlas (rafturi), întoarce imaginea și regiunile."""
    atlas = Image.new("RGBA", (ATLAS, ATLAS), (0, 0, 0, 0))
    regions, x, y, shelf = {}, 0, 0, 0
    for name in DRAW:
        layer = layers[name]
        box = layer.getchannel("A").getbbox()
        if box is None:
            raise ValueError(f"strat gol: {name}")
        tile = layer.crop(box)
        w, h = tile.size
        if x + w > ATLAS:
            x, y, shelf = 0, y + shelf, 0
        atlas.paste(tile, (x, y))
        regions[name] = (box[0], box[1], w, h, x, y, w, h)
        x += w
        shelf = max(shelf, h)
    return atlas, regions


def build(first_level: bool = False):
    layers = load_layers(RIG)
    atlas, regions = pack(layers)
    meshes, order = {}, []
    for name in DRAW:
        cols = rows = GRID[name]
        verts, uvs, tris = _grid(regions[name], cols, rows)
        kwargs = {"part": 0, "texture": 0}
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
            opacity_param = {"eyes_closed": "ParamEyeLOpen", "mouth_open": "ParamMouthOpenY"}.get(name)
            if name in EXPRESSION_LAYERS:
                opacity_param = "ParamExpr" + name.split("_")[1].capitalize()
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
                            for name, slug, _p in EXPRESSIONS],
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
              ("ParamGroupExpressions", "Expresii", [p for _n, _s, p in EXPRESSIONS])]
    return {
        "Version": 3,
        "Parameters": [{"Id": name, "GroupId": next(g for g, _l, ids in groups if name in ids),
                        "Name": name} for name, *_r in PARAMS],
        "ParameterGroups": [{"Id": g, "GroupId": "", "Name": label} for g, label, _ids in groups],
        "Parts": [{"Id": "PartCap", "Name": "Cap"}, {"Id": "PartCorp", "Name": "Corp"}],
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
    for name, slug, param in EXPRESSIONS:
        expr = {"Type": "Live2D Expression",
                "Parameters": [{"Id": p, "Value": 1.0 if p == param else 0.0, "Blend": "Overwrite"}
                               for _n, _s, p in EXPRESSIONS],
                "FadeInTime": 0.2, "FadeOutTime": 0.2}
        (outdir / f"izentric.{slug}.exp3.json").write_text(
            json.dumps(expr, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"moc3_bytes": len(moc_bytes), "meshes": len(model.meshes),
            "params": len(model.params), "keyforms": moc3_keyforms(model)}


if __name__ == "__main__":
    raise SystemExit(main())
