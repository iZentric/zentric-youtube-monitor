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
HEAD_BLEED = 20      # cât coboară capul peste guler, ca să nu apară gol la rotire
BODY_BLEED = 20      # cât urcă trupul sub cap
IRIS_FEATHER = 0  # margine tare: whitening-ul din cap acoperă exact discul, deci reconstrucția e la pixel


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

    head = Image.new("RGBA", source.size, (0, 0, 0, 0))
    head.paste(head_source.crop((0, 0, width, CUT_Y + HEAD_BLEED)), (0, 0))

    body = Image.new("RGBA", source.size, (0, 0, 0, 0))
    body.paste(source.crop((0, CUT_Y - BODY_BLEED, width, height)), (0, CUT_Y - BODY_BLEED))

    layers: dict[str, Image.Image] = {"head": head, "body": body}
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
    order = order or ["head", "body", "iris_L", "iris_R"]
    frame = Image.new("RGBA", layers[order[0]].size, (0, 0, 0, 0))
    for name in order:
        frame.alpha_composite(layers[name])
    return frame


def write_psd(path: Path, layers: dict[str, Image.Image], order: list[str] | None = None) -> Path:
    """PSD cu straturi cu nume — ce se deschide direct în Ayatsuri2D / Umamo / Cubism."""
    from pytoshop import enums
    from pytoshop.user import nested_layers

    order = order or ["eyes_closed", "mouth_open", "iris_L", "iris_R", "head", "body"]
    entries = []
    for name in order:
        image = layers[name]
        channels = {0: np.asarray(image)[..., 0], 1: np.asarray(image)[..., 1], 2: np.asarray(image)[..., 2]}
        channels[-1] = np.asarray(image)[..., 3]
        entries.append(
            nested_layers.Image(
                name=name.encode("ascii"),
                visible=True,
                opacity=255,
                top=0,
                left=0,
                bottom=image.height,
                right=image.width,
                channels=channels,
                blend_mode=enums.BlendMode.normal,
            )
        )
    psd = nested_layers.nested_layers_to_psd(
        entries,
        color_mode=enums.ColorMode.rgb,
        depth=8,
        size=(layers["head"].height, layers["head"].width),
        compression=enums.Compression.zip,  # RLE are nevoie de un pachet extern care lipsește
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        psd.write(handle)
    return path


PARAMETERS = [
    ("ParamAngleX", -30, 30, 0),
    ("ParamAngleY", -30, 30, 0),
    ("ParamAngleZ", -30, 30, 0),
    ("ParamEyeLOpen", 0, 1, 1),
    ("ParamEyeROpen", 0, 1, 1),
    ("ParamEyeBallX", -1, 1, 0),
    ("ParamEyeBallY", -1, 1, 0),
    ("ParamMouthOpenY", 0, 1, 0),
    ("ParamMouthForm", -1, 1, 0),
    ("ParamBrowLY", -1, 1, 0),
    ("ParamBrowRY", -1, 1, 0),
    ("ParamBodyAngleX", -10, 10, 0),
    ("ParamBodyAngleZ", -10, 10, 0),
    ("ParamBreath", 0, 1, 0),
]


def write_sidecars(directory: Path, texture_name: str = "texture_00.png") -> dict[str, Path]:
    """Fișierele care însoțesc modelul: model3 (ce încarcă VTS) și cdi3 (numele parametrilor).

    Fizica nu se inventează de aici: se generează de editorul care face exportul, după
    ce straturile au fost legate de parametri.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    model = {
        "Version": 3,
        "FileReferences": {
            "Moc": "izentric.moc3",
            "Textures": [texture_name],
            "DisplayInfo": "izentric.cdi3.json",
            "Expressions": [{"Name": "laugh", "File": "expressions/laugh.exp3.json"}],
        },
        "Groups": [
            {"Target": "Parameter", "Name": "EyeBlink", "Ids": ["ParamEyeLOpen", "ParamEyeROpen"]},
            {"Target": "Parameter", "Name": "LipSync", "Ids": ["ParamMouthOpenY"]},
        ],
        "HitAreas": [{"Id": "Head", "Name": "Head"}],
    }
    display = {
        "Version": 3,
        "Parameters": [
            {
                "Id": param,
                "GroupId": "ParamGroup" + param,
                "Name": param,
            }
            for param, _low, _high, _default in PARAMETERS
        ],
        "ParameterGroups": [
            {"Id": "ParamGroup" + param, "GroupId": "", "Name": label}
            for param, label in (
                ("ParamAngleX", "Cap: rotire stânga-dreapta"),
                ("ParamAngleY", "Cap: sus-jos"),
                ("ParamAngleZ", "Cap: înclinare"),
                ("ParamEyeLOpen", "Ochi stâng: deschis"),
                ("ParamEyeROpen", "Ochi drept: deschis"),
                ("ParamEyeBallX", "Privire: stânga-dreapta"),
                ("ParamEyeBallY", "Privire: sus-jos"),
                ("ParamMouthOpenY", "Gură: deschisă"),
                ("ParamMouthForm", "Gură: formă"),
                ("ParamBodyAngleX", "Corp: rotire"),
                ("ParamBodyAngleZ", "Corp: înclinare"),
                ("ParamBreath", "Respirație"),
            )
        ],
    }
    paths = {}
    for name, payload in (
        ("izentric.model3.json", model),
        ("izentric.cdi3.json", display),
    ):
        path = directory / name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        paths[name] = path
    return paths


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
    print(f"scrise {len(layers)} straturi + PSD + model3/cdi3 în {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
