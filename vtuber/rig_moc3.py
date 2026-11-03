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


def split_horns(layers: dict[str, Image.Image]) -> dict[str, Image.Image]:
    """Scoate coarnele într-un strat propriu și umple părul rămas dedesubt.

    Umplerea ia doar pixelii de păr vecini (stânga/dreapta, altfel din rândul de jos),
    pe fiecare segment continuu al coarnelor — nu peste tot rândul.
    """
    import numpy as np

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

    def redish(px):
        """Culoare din familia coarnelor — nu are voie să servească drept sursă de umplere."""
        return px[0] > 45 and px[0] > px[1] * 1.5 and px[0] > px[2] * 1.5

    base = head.copy()
    height, width = horn.shape
    for y in range(height - 1, -1, -1):
        row = horn[y]
        if not row.any():
            continue
        cols = row.nonzero()[0]
        runs, start_x = [], cols[0]
        for prev, cur in zip(cols, cols[1:]):
            if cur != prev + 1:
                runs.append((start_x, prev))
                start_x = cur
        runs.append((start_x, cols[-1]))
        for x0, x1 in runs:
            left = next((base[y, x] for x in range(x0 - 1, max(-1, x0 - 60), -1)
                         if base[y, x, 3] > 100 and not redish(base[y, x])), None)
            right = next((base[y, x] for x in range(x1 + 1, min(width, x1 + 60))
                          if base[y, x, 3] > 100 and not redish(base[y, x])), None)
            below = base[min(height - 1, y + 1)]
            if left is None and right is None:
                left = right = below[(x0 + x1) // 2]
            left = left if left is not None else right
            right = right if right is not None else left
            span = x1 - x0 + 1
            for i, x in enumerate(range(x0, x1 + 1)):
                if below[x, 3] > 100 and not redish(below[x]):   # părul se continuă în sus
                    base[y, x] = below[x]
                    continue
                t = 0.5 if span == 1 else i / (span - 1)
                base[y, x] = (left * (1 - t) + right * t).astype(np.int16)
                base[y, x, 3] = max(left[3], right[3])
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
