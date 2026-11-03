"""Taie pozele tale în straturi pentru un model Live2D (PSD gata de rigat).

Pozele primite sunt aplatizate. Modulul reface din ele straturile de care are nevoie un
editor Live2D (Ayatsuri2D, Umamo, Cubism) ca să miște capul, ochii și gura separat:

    body   — hanoracul și umerii
    head   — capul, fără iris (albul ochiului rămâne în cap)
    iris_L / iris_R — irisul cu pupilă și reflexe, mutabil pe sub pleoapă
    eyes_closed — pleoapele închise (din `blink`)
    mouth_open  — gura deschisă (din `talking`)
    mouth_mid   — gura pe jumătate (derivată)

Reconstrucția e verificată: `head` + `iris_L` + `iris_R` trebuie să dea `idle.png` la pixel.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).parent
ASSETS = HERE / "assets"
OUT = HERE / "rig"

CUT_Y = 655          # linia gulerului, măsurată pe idle.png
HEAD_BLEED = 60      # cât coboară gâtul sub linia gulerului (gâtul se termină la ~y 700)
BODY_BLEED = 20      # cât urcă trupul sub cap
IRIS_FEATHER = 0  # margine tare: whitening-ul din cap acoperă exact discul, deci reconstrucția e la pixel


def skin_mask(image: Image.Image) -> np.ndarray:
    """Pielea personajului (tenul): R-G ≈ 64, G-B ≈ 32. Doar gâtul pică sub linia gulerului."""
    rgb = np.asarray(image.convert("RGBA")).astype(int)
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (np.abs((red - green) - 64) < 32) & (np.abs((green - blue) - 32) < 32) & (red > 170) & (rgb[..., 3] > 200)


def _load(name: str, assets: Path = ASSETS) -> Image.Image:
    return Image.open(Path(assets) / name).convert("RGBA")


def _components(mask: np.ndarray, min_area: int = 200) -> np.ndarray:
    remaining = mask.copy()
    kept = np.zeros_like(mask)
    height, width = mask.shape
    for y0, x0 in zip(*np.nonzero(remaining)):
        if not remaining[y0, x0]:
            continue
        stack = [(y0, x0)]
        remaining[y0, x0] = False
        points = []
        while stack:
            y, x = stack.pop()
            points.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width and remaining[ny, nx]:
                        remaining[ny, nx] = False
                        stack.append((ny, nx))
        if len(points) >= min_area:
            for y, x in points:
                kept[y, x] = True
    return kept


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """Umple găurile (pupila, reflexele) dintr-un blob, ca irisul să fie un disc plin."""
    height, width = mask.shape
    outside = np.zeros_like(mask)
    stack = [(y, x) for x in range(width) for y in (0, height - 1) if not mask[y, x]]
    stack += [(y, x) for y in range(height) for x in (0, width - 1) if not mask[y, x]]
    for y, x in stack:
        outside[y, x] = True
    while stack:
        y, x = stack.pop()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < height and 0 <= nx < width and not mask[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                stack.append((ny, nx))
    return ~outside


IRIS_CIRCLES = {"L": (410, 427, 52), "R": (607, 424, 52)}  # măsurate pe idle.png; se pot da cu --iris


def iris_masks(size: tuple[int, int], circles: dict[str, tuple[int, int, int]] | None = None):
    """Măști circulare pentru irise.

    Irisurile sunt rotunde în desenul tău, deci un disc e suficient. Cercul se dă manual
    (centru + rază) pentru că o detecție pe culoare prinde și genele și umbrele pielii.
    """
    circles = circles or IRIS_CIRCLES
    width, height = size
    grids = {}
    ys, xs = np.mgrid[0:height, 0:width]
    for side in ("L", "R"):
        cx, cy, radius = circles[side]
        grids[side] = (xs - cx) ** 2 + (ys - cy) ** 2 <= radius**2
    return grids["L"], grids["R"]


EYE_MASK_SCALE = (1.55, 1.45)  # cât de mare e deschiderea ochiului față de iris (măsurat vizual)


def eye_mask_masks(size, circles=None):
    """Elipse aproximative ale deschiderii ochilor — ținta de clipping pentru irise."""
    circles = circles or IRIS_CIRCLES
    width, height = size
    ys, xs = np.mgrid[0:height, 0:width]
    out = {}
    for side in ("L", "R"):
        cx, cy, radius = circles[side]
        rx, ry = radius * EYE_MASK_SCALE[0], radius * EYE_MASK_SCALE[1]
        out[side] = ((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2 <= 1.0
    return out


def build_layers(
    source: Image.Image | None = None,
    assets: Path = ASSETS,
    circles: dict[str, tuple[int, int, int]] | None = None,
) -> dict[str, Image.Image]:
    """Straturile finale, toate pe același canvas 1024×1024."""
    source = source or _load("idle.png", assets)
    width, height = source.size
    pixels = np.asarray(source).astype(np.uint8)

    left, right = iris_masks(source.size, circles)
    iris_zone = left | right

    # capul: irisul scos și înlocuit cu albul ochiului, ca irisul mutat să nu lase urmă
    if iris_zone.any():
        white = np.array([248, 250, 252], dtype=np.uint8)
        no_iris = pixels.copy()
        no_iris[iris_zone, :3] = white
    else:
        no_iris = pixels.copy()
    head_source = Image.fromarray(no_iris, "RGBA")

    # capul: tot ce e deasupra gulerului + gâtul (doar pielea) din banda de sub el.
    # Gulerul rămâne la trup, deci la rotire capul ia gâtul cu el și gulerul stă pe loc.
    skin = skin_mask(source)
    head_pixels = np.zeros_like(pixels)
    head_pixels[:CUT_Y] = pixels[:CUT_Y]
    band = slice(CUT_Y, min(height, CUT_Y + HEAD_BLEED))
    # gâtul se lățește cu 6 px în banda de sub guler: gulerul îl acoperă, dar la rotire
    # nu mai rămâne nici un gol între gât și guler
    wider = Image.fromarray((skin[band] * 255).astype(np.uint8), "L").filter(ImageFilter.MaxFilter(13))
    keep = np.asarray(wider) > 40
    head_pixels[band] = np.where(keep[..., None], pixels[band], 0)
    head = Image.fromarray(head_pixels, "RGBA")

    # trupul: tot ce e sub guler, fără piele — altfel gâtul ar sta pe loc când capul se rotește
    body_pixels = np.zeros_like(pixels)
    start = CUT_Y - BODY_BLEED
    body_pixels[start:] = np.where((~skin[start:])[..., None], pixels[start:], 0)
    body = Image.fromarray(body_pixels, "RGBA")

    eye_masks = eye_mask_masks(source.size, circles)
    layers: dict[str, Image.Image] = {"head": head, "body": body}
    for side, mask in eye_masks.items():
        layer = np.zeros_like(pixels)
        layer[mask] = [255, 255, 255, 255]
        layers[f"eye_mask_{side}"] = Image.fromarray(layer, "RGBA")
    for name, mask in (("iris_L", left), ("iris_R", right)):
        layer = np.zeros_like(pixels)
        layer[mask] = pixels[mask]
        layer[..., 3] = np.where(mask, 255, 0).astype(np.uint8)
        image = Image.fromarray(layer, "RGBA")
        if IRIS_FEATHER:
            alpha = image.getchannel("A").filter(ImageFilter.GaussianBlur(IRIS_FEATHER))
            image.putalpha(alpha)
        layers[name] = image

    # pleoapele închise: diferența dintre blink și idle
    from puppet import difference_mask

    blink = _load("blink.png", assets)
    talking = _load("talking.png", assets)
    layers["eyes_closed"] = _patch(blink, difference_mask(source, blink))
    layers["mouth_open"] = _patch(talking, difference_mask(source, talking))
    return layers


def _patch(state: Image.Image, mask: Image.Image) -> Image.Image:
    """Doar zona care diferă, pe canvas complet (restul transparent)."""
    layer = Image.new("RGBA", state.size, (0, 0, 0, 0))
    layer.paste(state, (0, 0), mask)
    return layer


def composite(layers: dict[str, Image.Image], order: list[str] | None = None) -> Image.Image:
    """Reconstruiește cadrul din straturi, în ordinea dată."""
    order = order or COMPOSITE_ORDER
    frame = Image.new("RGBA", layers[order[0]].size, (0, 0, 0, 0))
    for name in order:
        frame.alpha_composite(layers[name])
    return frame


# gulerul (trup) stă DEASUPRA gâtului, deci cusătura nu se vede când capul se rotește
DRAW_ORDER = ["eyes_closed", "mouth_open", "iris_L", "iris_R", "eye_mask_L", "eye_mask_R", "body", "head"]
COMPOSITE_ORDER = ["body", "head", "iris_L", "iris_R"]

GROUPS = [
    ("FACE", True, ["eyes_closed", "mouth_open", "iris_L", "iris_R"]),
    ("MASKS", False, ["eye_mask_L", "eye_mask_R"]),
    ("BODY", True, ["body"]),
    ("HEAD", True, ["head"]),
]
HIDDEN_BY_DEFAULT = {"eyes_closed", "mouth_open"}
CLIPPING = {"iris_L": "eye_mask_L", "iris_R": "eye_mask_R"}


def write_psd(path: Path, layers: dict[str, Image.Image]) -> Path:
    """PSD grupat, ca un rigger să se orienteze din prima: FACE / MASKS / HEAD / BODY."""
    from pytoshop import enums
    from pytoshop.user import nested_layers

    def entry(name: str):
        image = layers[name]
        array = np.asarray(image)
        return nested_layers.Image(
            name=name,
            visible=name not in HIDDEN_BY_DEFAULT,
            opacity=255,
            top=0,
            left=0,
            bottom=image.height,
            right=image.width,
            channels={0: array[..., 0], 1: array[..., 1], 2: array[..., 2], -1: array[..., 3]},
            blend_mode=enums.BlendMode.normal,
        )

    tree = []
    for group_name, visible, members in GROUPS:
        tree.append(
            nested_layers.Group(
                name=group_name,
                visible=visible,
                layers=[entry(member) for member in members],
                closed=False,
            )
        )
    height, width = layers["head"].height, layers["head"].width
    psd = nested_layers.nested_layers_to_psd(
        tree,
        color_mode=enums.ColorMode.rgb,
        depth=8,
        size=(height, width),
        compression=enums.Compression.zip,  # RLE ar cere pachetul `packbits`, care nu e instalat
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        psd.write(handle)
    return path


# ID-urile și grupele standard sunt cele din modelul oficial Live2D (Mao.cdi3.json).
PARAMETERS = [
    ("ParamAngleX", "ParamGroupFace", "Unghi cap X", -30, 30, 0),
    ("ParamAngleY", "ParamGroupFace", "Unghi cap Y", -30, 30, 0),
    ("ParamAngleZ", "ParamGroupFace", "Unghi cap Z", -30, 30, 0),
    ("ParamEyeLOpen", "ParamGroupEyes", "Ochi stâng deschis", 0, 1, 1),
    ("ParamEyeROpen", "ParamGroupEyes", "Ochi drept deschis", 0, 1, 1),
    ("ParamEyeBallX", "ParamGroupEyeballs", "Privire X", -1, 1, 0),
    ("ParamEyeBallY", "ParamGroupEyeballs", "Privire Y", -1, 1, 0),
    ("ParamBrowLY", "ParamGroupBrows", "Sprânceană stânga sus", -1, 1, 0),
    ("ParamBrowRY", "ParamGroupBrows", "Sprânceană dreapta sus", -1, 1, 0),
    ("ParamMouthOpenY", "ParamGroupMouth", "Gură deschisă", 0, 1, 0),
    ("ParamMouthForm", "ParamGroupMouth", "Formă gură", -1, 1, 0),
    ("ParamBodyAngleX", "ParamGroupBody", "Unghi corp X", -10, 10, 0),
    ("ParamBodyAngleZ", "ParamGroupBody", "Unghi corp Z", -10, 10, 0),
    ("ParamBreath", "ParamGroupBody", "Respirație", 0, 1, 0),
    ("ParamHairFront", "ParamGroupSway", "Șuvițe față", -1, 1, 0),
    ("ParamString", "ParamGroupSway", "Șnururi glugă", -1, 1, 0),
]

PARAMETER_GROUPS = [
    ("ParamGroupFace", "Față"),
    ("ParamGroupEyes", "Ochii deschiși închiși"),
    ("ParamGroupEyeballs", "Glob ocular"),
    ("ParamGroupBrows", "Sprâncene"),
    ("ParamGroupMouth", "Gură"),
    ("ParamGroupBody", "Corp"),
    ("ParamGroupSway", "Fizică"),
]


def model3(texture: str = "texture_00.png") -> dict:
    return {
        "Version": 3,
        "FileReferences": {
            "Moc": "izentric.moc3",
            "Textures": [texture],
            "DisplayInfo": "izentric.cdi3.json",
        },
        "Groups": [
            {"Target": "Parameter", "Name": "LipSync", "Ids": ["ParamMouthOpenY"]},
            {"Target": "Parameter", "Name": "EyeBlink", "Ids": ["ParamEyeLOpen", "ParamEyeROpen"]},
        ],
        "HitAreas": [
            {"Id": "HitAreaHead", "Name": "Head"},
            {"Id": "HitAreaBody", "Name": "Body"},
        ],
    }


def cdi3() -> dict:
    return {
        "Version": 3,
        "Parameters": [
            {"Id": param, "GroupId": group, "Name": label} for param, group, label, _lo, _hi, _default in PARAMETERS
        ],
        "ParameterGroups": [{"Id": group, "GroupId": "", "Name": label} for group, label in PARAMETER_GROUPS],
        "Parts": [],
    }


def rig_spec() -> dict:
    """Ce are de făcut rigger-ul, cu valori concrete în pixeli pe canvasul de 1024."""
    return {
        "canvas": {"width": 1024, "height": 1024, "pivot_neck": [512, 655]},
        "standard": "Live2D Cubism model3 / moc3 5.0",
        "draw_order": DRAW_ORDER,
        "clipping": CLIPPING,
        "deformers": [
            {"id": "D_Root", "type": "root", "children": ["D_HeadRot", "D_Body"]},
            {
                "id": "D_Body",
                "type": "warp",
                "layers": ["body"],
                "pivot": [512, 900],
                "parameters": ["ParamBodyAngleX", "ParamBodyAngleZ", "ParamBreath"],
            },
            {
                "id": "D_HeadRot",
                "type": "rotation",
                "parent": "D_Root",
                "layers": ["head"],
                "pivot": [512, 655],
                "parameters": ["ParamAngleZ"],
            },
            {
                "id": "D_HeadWarp",
                "type": "warp",
                "parent": "D_HeadRot",
                "layers": ["head", "iris_L", "iris_R", "eyes_closed", "mouth_open"],
                "pivot": [512, 430],
                "parameters": ["ParamAngleX", "ParamAngleY"],
            },
        ],
        "keyforms": {
            "ParamAngleX": [
                {"value": -30, "deformer": "D_HeadWarp", "translate": [-14, 0]},
                {"value": 0, "deformer": "D_HeadWarp", "translate": [0, 0]},
                {"value": 30, "deformer": "D_HeadWarp", "translate": [14, 0]},
            ],
            "ParamAngleY": [
                {"value": -30, "deformer": "D_HeadWarp", "translate": [0, 10]},
                {"value": 0, "deformer": "D_HeadWarp", "translate": [0, 0]},
                {"value": 30, "deformer": "D_HeadWarp", "translate": [0, -10]},
            ],
            "ParamAngleZ": [
                {"value": -30, "deformer": "D_HeadRot", "rotate": -8},
                {"value": 0, "deformer": "D_HeadRot", "rotate": 0},
                {"value": 30, "deformer": "D_HeadRot", "rotate": 8},
            ],
            "ParamEyeLOpen": [
                {"value": 0, "layer": "eyes_closed", "opacity": 100},
                {"value": 1, "layer": "eyes_closed", "opacity": 0},
            ],
            "ParamEyeROpen": [
                {"value": 0, "layer": "eyes_closed", "opacity": 100},
                {"value": 1, "layer": "eyes_closed", "opacity": 0},
            ],
            "ParamEyeBallX": [
                {"value": -1, "layers": ["iris_L", "iris_R"], "translate": [-11, 0]},
                {"value": 0, "layers": ["iris_L", "iris_R"], "translate": [0, 0]},
                {"value": 1, "layers": ["iris_L", "iris_R"], "translate": [11, 0]},
            ],
            "ParamEyeBallY": [
                {"value": -1, "layers": ["iris_L", "iris_R"], "translate": [0, -9]},
                {"value": 0, "layers": ["iris_L", "iris_R"], "translate": [0, 0]},
                {"value": 1, "layers": ["iris_L", "iris_R"], "translate": [0, 9]},
            ],
            "ParamMouthOpenY": [
                {"value": 0, "layer": "mouth_open", "opacity": 0},
                {"value": 1, "layer": "mouth_open", "opacity": 100},
            ],
            "ParamBodyAngleX": [
                {"value": -10, "deformer": "D_Body", "translate": [-6, 0]},
                {"value": 0, "deformer": "D_Body", "translate": [0, 0]},
                {"value": 10, "deformer": "D_Body", "translate": [6, 0]},
            ],
            "ParamBreath": [
                {"value": 0, "deformer": "D_Body", "translate": [0, 0]},
                {"value": 1, "deformer": "D_Body", "translate": [0, -3]},
            ],
        },
        "notes": [
            "eyes_closed și mouth_open se pot lega și pe opacitate (mai simplu) sau pe clipping (mai curat).",
            "iris_L / iris_R au nevoie de clipping pe eye_mask_L / eye_mask_R, altfel ies din ochi.",
            "Sprâncenele sunt desenate în cap: ParamBrowLY/RY există în cdi3, dar nu au ce mișca până nu sunt pe strat separat.",
        ],
    }


def write_sidecars(directory: Path, texture: str = "texture_00.png") -> dict[str, Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, payload in (
        ("izentric.model3.json", model3(texture)),
        ("izentric.cdi3.json", cdi3()),
        ("izentric.rigspec.json", rig_spec()),
    ):
        path = directory / name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        written[name] = path
    return written


PACK_FILES = ("izentric.psd", "izentric.rigspec.json", "izentric.model3.json", "izentric.cdi3.json", "GATA-DE-RIGAT.txt")


def write_pack(directory: Path = OUT, name: str = "izentric-pack.zip") -> Path:
    """Un singur fișier de descărcat: PSD + specificație + JSON-uri + ghidul de rigat."""
    import zipfile

    directory = Path(directory)
    target = directory / name
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for member in PACK_FILES:
            path = directory / member
            if path.exists():
                archive.write(path, member)
    return target


def parse_iris_arguments(values: list[str]) -> dict[str, tuple[int, int, int]]:
    """`--iris L:410,427,52 --iris R:607,424,52`"""
    circles = dict(IRIS_CIRCLES)
    for value in values:
        side, numbers = value.split(":")
        cx, cy, radius = (int(part) for part in numbers.split(","))
        circles[side.upper()] = (cx, cy, radius)
    return circles


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    circles = {}
    if "--iris" in argv:
        index = argv.index("--iris")
        collected = []
        while index + 1 < len(argv) and ":" in argv[index + 1]:
            collected.append(argv.pop(index + 1))
        argv.pop(index)
        circles = parse_iris_arguments(collected)
    OUT.mkdir(parents=True, exist_ok=True)
    layers = build_layers(circles=circles or None)
    for name, image in layers.items():
        image.save(OUT / f"{name}.png")
    write_psd(OUT / "izentric.psd", layers)
    write_sidecars(OUT)
    write_pack(OUT)
    print(f"scrise {len(layers)} straturi + PSD + model3/cdi3/rigspec + izentric-pack.zip în {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
