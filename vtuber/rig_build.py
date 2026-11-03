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
HEAD_BLEED = 60     # cât coboară gâtul sub linia gulerului (gâtul se termină la ~y 700)
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


def _blob_at(mask: np.ndarray, seed: tuple[int, int]) -> np.ndarray:
    """Componenta din `mask` care conține punctul `seed` (BFS, fără dependențe)."""
    height, width = mask.shape
    out = np.zeros_like(mask)
    stack = [seed]
    if not mask[seed[1], seed[0]]:
        return out
    out[seed[1], seed[0]] = True
    while stack:
        x, y = stack.pop()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height and mask[ny, nx] and not out[ny, nx]:
                out[ny, nx] = True
                stack.append((nx, ny))
    return out


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    """Lărgește o mască cu `radius` pixeli (MaxFilter cere rază impară)."""
    size = 2 * radius + 1
    grown = Image.fromarray(mask.astype(np.uint8) * 255, "L").filter(ImageFilter.MaxFilter(size))
    return np.asarray(grown) > 0


def iris_blob(pixels: np.ndarray, circle: tuple[int, int, int]) -> np.ndarray:
    """Forma irisului desenat, nu un cerc ghicit.

    Irisul e singura zonă *colorată* din ochi (albastru închis / roșu închis), în timp ce
    genele și conturul sunt gri neutru. De aceea se caută saturația, nu întunericul —
    altfel pleoapa intră în formă și se mănâncă umbra de sub ea.
    """
    cx, cy, radius = circle
    height, width = pixels.shape[:2]
    ys, xs = np.mgrid[0:height, 0:width]
    near = (xs - cx) ** 2 + (ys - cy) ** 2 <= (radius * 1.45) ** 2
    rgb = pixels[..., :3].astype(np.int16)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    luminance = rgb.astype(np.float32).mean(axis=2)
    # pielea e și ea saturată (portocaliu), deci se scoate explicit; irisul e și închis
    skin = skin_mask(Image.fromarray(pixels[..., :3], "RGB"))
    colored = near & (sat > 22) & (luminance < 190) & ~skin
    blob = _blob_at(colored, (cx, cy))
    if blob.sum() < 400:
        return ((xs - cx) ** 2 + (ys - cy) ** 2 <= radius**2)
    return blob


def iris_mask_with_outline(pixels: np.ndarray, blob: np.ndarray, grow: int = 3) -> np.ndarray:
    """Irisul plus conturul lui întunecat.

    Blobul colorat nu prinde și conturul negru din jur; dacă l-am lăsa în cap, la mutare
    dispare conturul și apare un halou alb. Se adaugă deci inelul închis, neutru, lipit
    de iris — fără să intre și albul ochiului.
    """
    rgb = pixels[..., :3].astype(np.int16)
    luminance = rgb.astype(np.float32).mean(axis=2)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    dark_neutral = (luminance < 130) & (sat < 35)
    ring = _dilate(blob, grow) & dark_neutral
    mask = blob | ring
    # închidere morfologică mare: conturul desenat e anti-aliat, deci iese punctat;
    # altfel rămâne o linie punctată vizibilă când irisul se mișcă
    step = Image.fromarray(mask.astype(np.uint8) * 255, "L")
    step = step.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7))
    closed = np.asarray(step) > 0
    # găurile din interior (reflexe, puncte deschise) se umplu
    from PIL import ImageDraw

    filled = Image.fromarray((closed).astype(np.uint8) * 255, "L").copy()
    ImageDraw.floodfill(filled, (0, 0), 128)
    holes = np.asarray(filled) == 0
    return closed | holes


def eye_white(pixels: np.ndarray, blob: np.ndarray, grow: int = 3, iterations: int = 2000) -> np.ndarray:
    """Albul ochiului, reconstruit prin difuzie în locul irisului.

    Nu se vopsește un disc cu o culoare medie (ieșea un cerc vizibil, se vedea urât).
    Se rezolvă o umplere armonică: fiecare pixel din zonă devine media vecinilor, iar
    marginea rămâne exact culoarea desenului. Rezultatul continuă natural umbra de sub
    pleoapă și albul din colțuri, fără cusătură — pentru că atinge marginea cu aceeași
    culoare pe care o are desenul acolo.
    """
    from PIL import Image as PILImage

    region = np.asarray(PILImage.fromarray(blob.astype(np.uint8) * 255, "L")
                        .filter(ImageFilter.MaxFilter(2 * grow + 1))) > 0
    ys, xs = np.nonzero(region)
    y0, y1 = max(0, ys.min() - 2), min(pixels.shape[0], ys.max() + 3)
    x0, x1 = max(0, xs.min() - 2), min(pixels.shape[1], xs.max() + 3)
    area = pixels[y0:y1, x0:x1, :3].astype(np.float32)
    fill = region[y0:y1, x0:x1]
    work = area.copy()
    for _ in range(iterations):
        up = np.roll(work, 1, axis=0)
        down = np.roll(work, -1, axis=0)
        left = np.roll(work, 1, axis=1)
        right = np.roll(work, -1, axis=1)
        work = np.where(fill[..., None], (up + down + left + right) * 0.25, area)
    # În interior se pune EXCLUSIV difuzia (altfel rămâne 50% din conturul irisului și
    # apare o linie punctată), iar estomparea se face doar în afara zonei, pe 2 px.
    blur = np.asarray(PILImage.fromarray(fill.astype(np.uint8) * 255, "L")
                      .filter(ImageFilter.GaussianBlur(2.5))).astype(np.float32) / 255.0
    # netezire în interiorul zonei: difuzia pe o margine zimțată lasă dungi verticale
    smoothed = np.asarray(PILImage.fromarray(np.clip(work, 0, 255).astype(np.uint8), "RGB")
                          .filter(ImageFilter.GaussianBlur(1.2))).astype(np.float32)
    work = np.where(fill[..., None], smoothed, work)
    weight = np.where(fill, 1.0, 0.0)[..., None]   # interior = difuzie curată, fără amestec
    blended = area * (1 - weight) + np.clip(work, 0, 255) * weight
    out = pixels.copy()
    out[y0:y1, x0:x1, :3] = np.clip(blended, 0, 255).astype(np.uint8)
    return out


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
    # Gâtul se lățește și coboară adânc sub guler, vopsit în culoarea pielii. Gulerul
    # (stratul de trup, desenat deasupra) îl acoperă, deci nu se vede; dar la rotație
    # maximă gâtul umple toată deschizătura și nu mai rămâne nici un pixel de fundal.
    # Gâtul: doar pielea desenată, luată așa cum e, lărgită cu 6 px ca să nu rămână firicele
    # de gol lângă guler. NU se inventează culoare: orice pixeli desenați de mână aici ar
    # ieși la iveală prin deschizătura husei și s-ar vedea ca o pată.
    # Gâtul = EXACT pielea desenată. Fără lățire: lărgirea copia și umbra de lângă gât,
    # iar umbra aceea se plimba cu capul și apărea ca o dungă închisă pe husă.
    skin_here = skin[band]
    keep = skin_here.copy()
    band_art = pixels[band]
    head_pixels[band] = np.where(keep[..., None], band_art, 0)
    head = Image.fromarray(head_pixels, "RGBA")

    # trupul: tot ce e sub guler, fără piele — altfel gâtul ar sta pe loc când capul se rotește
    body_pixels = np.zeros_like(pixels)
    start = CUT_Y - BODY_BLEED
    body_pixels[start:] = np.where((~skin[start:])[..., None], pixels[start:], 0)
    body = Image.fromarray(body_pixels, "RGBA")

    eye_masks = eye_mask_masks(source.size, circles)
    layers: dict[str, Image.Image] = {"head": head, "body": body}
    backing = backplate(body, head, source)
    if backing is not None:
        layers["backing"] = backing
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
    # Pleoapele și gura: se DECUPEAZĂ zona lor (nu „diferența" estompată), ca la opacitate
    # maximă să acopere complet. Cu marginea estompată rămânea urma ochiului deschis dedesubt
    # („ochi sub ochi") și se vedea șters.
    # zona pleoapelor = exact ce se schimbă între deschis și închis (pleoapa + genele),
    # nu o elipsă: elipsa lăsa conturul ochiului deschis pe dinafară
    eye_zone = _dilate(np.asarray(difference_mask(source, blink)) > 40, 7)
    mouth_zone = _dilate(np.asarray(difference_mask(source, talking)) > 40, 7)
    layers["eyes_closed"] = _patch(blink, eye_zone)
    layers["mouth_open"] = _patch(talking, mouth_zone)
    return layers


def skin_tone(pixels: np.ndarray, skin: np.ndarray, cut: int) -> np.ndarray:
    """Culoarea medie a pielii din jurul gulerului, folosită la prelungirea gâtului."""
    window = skin[max(0, cut - 60):cut + 20]
    colors = pixels[max(0, cut - 60):cut + 20][window][:, :3]
    if len(colors) == 0:
        return np.array([235, 190, 170], dtype=np.float32)
    return colors.reshape(-1, 3).mean(axis=0)


def backplate(body: Image.Image, head: Image.Image, source: Image.Image | None = None,
              top: int = CUT_Y - 60, iterations: int = 400) -> Image.Image | None:
    """Spatele gulerului: umple golul gâtului DIN TRUP, cu țesătura husei din jur.

    Gâtul e scos din stratul de trup (ca să se rotească cu capul), deci în trup rămâne un
    gol în formă de gât. Golul se acoperă cu țesătură, prin difuzie pornită din marginile
    de țesut: la repaus e acoperit de gât, iar când capul se mută, ce se descoperă arată ca
    interiorul gulerului — nu ca o pată.
    """
    from PIL import ImageDraw

    alpha_body = np.asarray(body.getchannel("A"))
    solid = Image.fromarray(((alpha_body > 24) * 255).astype(np.uint8), "L").copy()
    for corner in ((0, 0), (solid.width - 1, 0), (0, solid.height - 1), (solid.width - 1, solid.height - 1)):
        if solid.getpixel(corner) == 0:
            ImageDraw.floodfill(solid, corner, 128)
    hole = (np.asarray(solid) == 0)
    hole[:top] = False
    if not hole.any():
        return None

    art = np.asarray((source or head).convert("RGB")).astype(np.float32)
    fixed = alpha_body > 24
    ys, xs = np.nonzero(hole)
    y0, y1 = max(0, ys.min() - 2), min(hole.shape[0], ys.max() + 3)
    x0, x1 = max(0, xs.min() - 2), min(hole.shape[1], xs.max() + 3)
    area = art[y0:y1, x0:x1]
    fill = hole[y0:y1, x0:x1]
    keep = fixed[y0:y1, x0:x1]
    work = area.copy()
    for _ in range(iterations):
        up = np.roll(work, 1, axis=0)
        down = np.roll(work, -1, axis=0)
        left = np.roll(work, 1, axis=1)
        right = np.roll(work, -1, axis=1)
        blurred = (up + down + left + right) * 0.25
        work = np.where(keep[..., None], area, np.where(fill[..., None], blurred, area))

    out = np.zeros((hole.shape[0], hole.shape[1], 4), dtype=np.uint8)
    out[y0:y1, x0:x1, :3] = np.clip(work, 0, 255).astype(np.uint8)
    # umplutura intră 2 px și sub țesătură: trupul e desenat deasupra, deci acolo nu se
    # vede, dar dispare linia de 1 px de la marginea golului
    grown = np.asarray(Image.fromarray(hole.astype(np.uint8) * 255, "L")
                       .filter(ImageFilter.MaxFilter(5))) > 0
    soft = np.asarray(Image.fromarray(grown.astype(np.uint8) * 255, "L")
                      .filter(ImageFilter.GaussianBlur(1.2))).astype(np.float32) / 255.0
    out[y0:y1, x0:x1, :3] = np.where(grown[y0:y1, x0:x1, None],
                                     np.clip(work, 0, 255).astype(np.uint8),
                                     out[y0:y1, x0:x1, :3])
    out[..., 3] = (np.clip(soft, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _patch(state: Image.Image, mask) -> Image.Image:
    """Zona dată, pe canvas complet (restul transparent), cu margine de 1 px.

    Masca e binară (nu estompată pe 7 px): la opacitate maximă stratul trebuie să acopere
    complet ce e dedesubt, altfel rămâne o urmă din starea veche.
    """
    if not isinstance(mask, np.ndarray):
        mask = np.asarray(mask) > 40
    # marginea aproape tare: un blur de 1 px „trăgea" genele negre în afara petecului
    # și desena un inel gri în jurul ochiului închis
    hard = Image.fromarray((mask * 255).astype(np.uint8), "L")
    layer = Image.new("RGBA", state.size, (0, 0, 0, 0))
    layer.paste(state, (0, 0), hard)
    return layer


def composite(layers: dict[str, Image.Image], order: list[str] | None = None) -> Image.Image:
    """Reconstruiește cadrul din straturi, în ordinea dată."""
    order = order or COMPOSITE_ORDER
    frame = Image.new("RGBA", layers[order[0]].size, (0, 0, 0, 0))
    for name in order:
        frame.alpha_composite(layers[name])
    return frame


# Stiva se scrie de la fund în sus (Pytoshop o inversează la scriere), iar DRAW_ORDER se
# DERIVĂ din ea: așa nu pot diverge niciodată ordinea din PSD și cea în care se desenează.
# Gulerul (trup) stă DEASUPRA gâtului, deci cusătura nu se vede când capul se rotește.
GROUPS = [
    ("BACKING", True, ["backing"]),
    ("HEAD", True, ["head"]),
    ("BODY", True, ["body"]),
    ("MASKS", False, ["eye_mask_R", "eye_mask_L"]),
    ("FACE", True, ["iris_R", "iris_L", "mouth_open", "eyes_closed"]),
]
DRAW_ORDER = [name for _, _, members in reversed(GROUPS) for name in reversed(members)]
COMPOSITE_ORDER = ["backing", "head", "iris_L", "iris_R", "body"]
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
