"""Taie pozele tale în straturi pentru un model Live2D (PSD gata de rigat).

Pozele primite sunt aplatizate. Modulul reface din ele straturile de care are nevoie un
editor Live2D (Ayatsuri2D, Umamo, Cubism) ca să miște capul, ochii și gura separat:

    body   — hanoracul și umerii
    head   — capul, fără iris (albul ochiului rămâne în cap)
    eye_L / eye_R — globul ocular (albul + irisul + reflexele), mutabil pe sub gene
    eyes_closed — pleoapele închise (din `blink`)
    mouth_open  — gura deschisă (din `talking`)
    mouth_mid   — gura pe jumătate (derivată)

Reconstrucția e verificată: `head` + `eye_L` + `eye_R` trebuie să dea `idle.png` la pixel.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

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


def despill(pixels: np.ndarray) -> np.ndarray:
    """Scoate conturul verde de 1 px de pe siluetă (rămășiță de la decuparea pozelor).

    Pixelii verzi se înlocuiesc cu media vecinilor care nu sunt verzi, de aproape în
    aproape, până nu mai rămâne nici unul. Altfel conturul se vede pe marginea părului,
    mai ales când stratul e rotit (interpolarea îl amestecă în personaj).
    """
    out = pixels.astype(np.float32)
    rgb = out[..., :3]
    # prag mic: pe lângă conturul verde aprins au rămas și pixeli verde-închis în păr
    green = (rgb[..., 1] > rgb[..., 0] + 20) & (rgb[..., 1] > rgb[..., 2] + 20)
    green &= pixels[..., 3] > 0
    if not green.any():
        return pixels
    # sursă de culoare: doar vecini opaci (haltă de anti-aliasing e aproape transparentă)
    fixed = ~green & (pixels[..., 3] > 200)
    for _ in range(10):
        if not green.any():
            break
        total = np.zeros_like(rgb)
        count = np.zeros(green.shape, dtype=np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            shifted_mask = np.roll(np.roll(fixed, dy, axis=0), dx, axis=1)
            shifted_rgb = np.roll(np.roll(rgb, dy, axis=0), dx, axis=1)
            total += shifted_rgb * shifted_mask[..., None]
            count += shifted_mask
        ready = green & (count > 0)
        if not ready.any():
            break
        rgb[ready] = (total[ready] / count[ready][:, None])
        fixed |= ready
        green &= ~ready
    out[..., :3] = rgb
    return np.clip(out, 0, 255).astype(np.uint8)


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


# Expresiile: pozele tale de stare, legate pe câte un parametru propriu (0..1 -> opacitate).
# Din fiecare se ia DOAR fața (piele, ochi, gură) și decorațiunile plutitoare (inimi,
# scânteieri, lacrimi) — haina și părul rămân din poza de repaus, altfel s-ar schimba
# corpul când schimbi expresia.
EXPRESSIONS = {
    "laugh": ("laugh.png", "ParamExprLaugh", "Râs"),
    "love": ("love.png", "ParamExprLove", "Îndrăgostit"),
    "sad": ("sad.png", "ParamExprSad", "Trist"),
    "shocked": ("shocked.png", "ParamExprShocked", "Șocat"),
    "sus": ("sus.png", "ParamExprSus", "Suspicios"),
}

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


def _small_marks(mask: np.ndarray, max_area: int = 3000, min_fill: float = 0.30,
                 max_height: int = 120) -> np.ndarray:
    """Pete mici și compacte (stropi de sudoare, lacrimi, semne) — nu dâre de contur.

    Diferența dintre două poze are și linii subțiri pe siluetă (conturul e desenat puțin
    altfel); alea NU trebuie copiate, altfel apare o dâră pe păr. Un strop e mic, plin și
    scund, deci se recunoaște după umplutura din dreptunghi.
    """
    from collections import deque

    kept = np.zeros_like(mask)
    seen = np.zeros_like(mask)
    height, width = mask.shape
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        queue = deque([(y0, x0)])
        seen[y0, x0] = True
        points = []
        while queue:
            y, x = queue.popleft()
            points.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        queue.append((ny, nx))
        area = len(points)
        if area > max_area:
            continue
        ys = [point[0] for point in points]
        xs = [point[1] for point in points]
        box = (max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1)
        if area / box >= min_fill and (max(ys) - min(ys)) <= max_height:
            for y, x in points:
                kept[y, x] = True
    return kept


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


def _erode(mask: np.ndarray, radius: int) -> np.ndarray:
    """Micșorează o mască (inversul dilatației)."""
    if radius <= 0:
        return mask
    grown = _dilate(~mask, radius)
    return ~grown


def eye_interior(pixels: np.ndarray, zone: np.ndarray, ellipse: np.ndarray,
                brightness: float = 140.0) -> np.ndarray:
    """Forma deschiderii ochiului desenat: albul + irisul, până la gene.

    Nu e o elipsă ghicită: se ia ce e desenat luminos (albul ochiului, irisul, reflexele)
    din interiorul elipsei de siguranță, fără piele, și se ține doar bucata legată de iris.
    Genele rămân afară, deci conturul ochiului stă pe loc când globul se mișcă.
    """
    rgb = pixels[..., :3].astype(np.float32)
    luminance = rgb.mean(axis=2)
    skin = skin_mask(Image.fromarray(pixels[..., :3], "RGB"))
    # genele și umbra închisă neutră (cenușie) rămân PE LOC, în cap: se mișcă doar
    # albul ochiului și irisul colorat. Altfel umbra de sub pleoapă alunecă și apare
    # ca un cârlig negru în capătul de jos al ochiului.
    rgb_i = pixels[..., :3].astype(np.int16)
    sat = rgb_i.max(axis=2) - rgb_i.min(axis=2)
    dark_neutral = (luminance < 150) & (sat < 35) & ~zone
    # alb curat (fără umbra albăstruie de sub iris): umbra rămâne pe loc, lipită de geană,
    # și nu se plimbă prin ochi când se mută globul
    sat_i = pixels[..., :3].astype(np.int16)
    sat_i = sat_i.max(axis=2) - sat_i.min(axis=2)
    white = (luminance > 225) & ~skin   # doar albul curat; umbra albăstruie rămâne pe loc
    content = ellipse & ~dark_neutral & (zone | white)
    ys, xs = np.nonzero(zone)
    if not len(ys):
        return zone
    blob = _blob_at(content, (int(np.median(xs)), int(np.median(ys))))
    if blob.sum() < 400:
        return zone
    filled = Image.fromarray((blob).astype(np.uint8) * 255, "L").copy()
    ImageDraw.floodfill(filled, (0, 0), 128)
    holes = np.asarray(filled) == 0
    return blob | holes


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
    pixels = despill(np.asarray(source).astype(np.uint8))

    circles = circles or IRIS_CIRCLES
    # Globul ocular: un singur strat cu TOT ochiul desenat (albul + irisul + reflexele),
    # decupat de masca deschiderii. La repaus se așază exact peste desen; la mișcare alunecă
    # în întregime pe sub gene, deci în urmă nu rămâne nici un iris și nici o pată umplută.
    # (Varianta cu iris decupat + alb inventat în cap lăsa un iris-fantomă care se mișca.)
    blobs = {side: iris_blob(pixels, circles[side]) for side in ("L", "R")}
    zones = {side: iris_mask_with_outline(pixels, blobs[side], 3) for side in ("L", "R")}
    ellipses = eye_mask_masks(source.size, circles)
    interiors = {side: eye_interior(pixels, zones[side], ellipses[side]) for side in ("L", "R")}

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

    bright = (pixels[..., :3].astype(np.float32).mean(axis=2) > 200) & ~(zones["L"] | zones["R"])
    sclera = np.median(pixels[..., :3][bright].reshape(-1, 3), axis=0)
    layers: dict[str, Image.Image] = {"head": head, "body": body}
    eye_fill: dict[str, np.ndarray] = {}      # zona din cap înlocuită cu scleră
    backing = backplate(body, head, source)
    if backing is not None:
        layers["backing"] = backing
    for side in ("L", "R"):
        interior = interiors[side]
        # Globul trebuie să conțină TOT irisul desenat (altfel rămâne o verigă de iris în
        # `head` și se vede ca „ochi sub ochi" când se mișcă globul) și să nu acopere piele.
        blob = iris_blob(pixels, circles[side])
        interior = (interior | blob) & ~skin_mask(Image.fromarray(pixels[..., :3], "RGB"))
        # Masca de clipping = exact globul. Înainte se „retrăgea" bordura ca marginea să cadă
        # în alb; inelul de alb nu mai există, deci nu mai e nimic de retras.
        core = interior
        layer = np.zeros_like(pixels)
        layer[core] = [255, 255, 255, 255]
        mask_image = Image.fromarray(layer, "RGBA")
        # mască tare: globul are propria margine; o estompare a măștii lăsa capul
        # (reconstruit) să se vadă pe 1 px pe conturul ochiului
        mask_image.putalpha(Image.fromarray((core * 255).astype(np.uint8), "L"))
        layers[f"eye_mask_{side}"] = mask_image
        # Globul ocular: desenul ochiului, exact deschiderea desenată.
        eyeball = np.zeros_like(pixels)
        eyeball[interior] = pixels[interior]
        eyeball[interior, 3] = 255
        layers[f"eye_{side}"] = Image.fromarray(eyeball, "RGBA")
        eye_fill[side] = interior

        # Sub glob, în `head`, irisul desenat NU are ce căuta: când globul alunecă (±11 px)
        # rămânea pe loc un iris-fantomă — exact „ochi sub ochi". Se înlocuiește cu scleră
        # reconstruită prin difuzie (aceeași funcție ca la albul din jurul irisului), deci
        # ce se descoperă la mișcare e alb cu umbra desenului, nu un iris.
        # Irisul se înlocuiește cu albul local al ochiului (mediana sclerai din deschidere),
        # nu cu o difuzie: difuzia lăsa o pată gri-albăstruie, adică un iris-fantomă difuz.
        lum_i = pixels[..., :3].astype(np.float32).mean(axis=2)
        sat_i = pixels[..., :3].astype(np.int16)
        sat_i = sat_i.max(axis=2) - sat_i.min(axis=2)
        inside = interior
        white_only = inside & ~blob & (lum_i > 200) & (sat_i < 60)
        alb = (np.median(pixels[white_only][:, :3].reshape(-1, 3), axis=0)
               if white_only.sum() > 50 else np.array([250, 250, 252]))
        filled = head_pixels.copy()
        # +2 px: conturul anti-aliased al irisului rămânea ca o linie punctată roșie
        # ...dar niciodată în afara globului: altfel albul iese pe marginea ochiului la repaus
        filled[_dilate(inside & blob, 2) & inside] = np.append(alb, 255).astype(filled.dtype)
        head_pixels = filled
        layers["head"] = Image.fromarray(np.clip(head_pixels, 0, 255).astype(np.uint8), "RGBA")

    # pleoapele închise: diferența dintre blink și idle
    from puppet import difference_mask

    blink = Image.fromarray(despill(np.asarray(_load("blink.png", assets)).astype(np.uint8)), "RGBA")
    talking = Image.fromarray(despill(np.asarray(_load("talking.png", assets)).astype(np.uint8)), "RGBA")
    # Pleoapele și gura: se DECUPEAZĂ zona lor (nu „diferența" estompată), ca la opacitate
    # maximă să acopere complet. Cu marginea estompată rămânea urma ochiului deschis dedesubt
    # („ochi sub ochi") și se vedea șters.
    # zona pleoapelor = exact ce se schimbă între deschis și închis (pleoapa + genele),
    # nu o elipsă: elipsa lăsa conturul ochiului deschis pe dinafară
    # zona pleoapelor: doar în interiorul ochilor (diferența dintre poze mai apare și pe
    # siluetă, fiindcă fiecare desen are conturul puțin altfel — aia nu e pleoapă)
    eye_area = np.zeros(pixels.shape[:2], dtype=bool)
    for side in ("L", "R"):
        eye_area |= np.asarray(Image.fromarray(ellipses[side].astype(np.uint8) * 255, "L")
                               .filter(ImageFilter.MaxFilter(3))) > 0
    # zona pleoapelor: diferența reală + toată zona din cap care a fost înlocuită cu scleră
    # (altfel albul reconstruit de sub glob rămâne descoperit pe lângă ochiul închis = inel)
    # `eye_area` limitează doar diferența (zgomot pe siluetă); zona înlocuită cu scleră
    # din cap trebuie acoperită integral, altfel rămâne un inel de scleră pe lângă pleoapă
    eye_zone = ((np.asarray(difference_mask(source, blink)) > 30) & eye_area) \
        | eye_fill["L"] | eye_fill["R"]
    mouth_area = np.zeros(pixels.shape[:2], dtype=bool)
    mouth_area[430:640, 380:660] = True
    mouth_zone = (np.asarray(difference_mask(source, talking)) > 30) & mouth_area
    layers["eyes_closed"] = _patch(blink, eye_zone)
    layers["mouth_open"] = _patch(talking, mouth_zone)

    # Expresiile. Fața = piele + ochi + gură (dilatate); decorațiunile = bucățile desenate
    # care nu fac parte din personaj (inimi, scânteieri, lacrimi, stropi).
    ellipses = eye_mask_masks(source.size, circles)
    # doar piele + ochi + gură: dacă dilatarea intră în păr, se vede conturul părului din
    # poza expresiei ca o dâră peste părul din poza de repaus
    face_zone = _dilate(skin, 2) | ellipses["L"] | ellipses["R"] | _dilate(mouth_zone, 2)
    for name, (file, _param, _label) in EXPRESSIONS.items():
        state_pixels = despill(np.asarray(_load(file, assets)).astype(np.uint8))
        visible = state_pixels[..., 3] > 24
        body_parts = _components(visible, min_area=20000)     # personajul, dintr-o bucată
        decor = visible & ~body_parts                          # ce plutește în jur
        decor &= np.arange(pixels.shape[0])[:, None] < CUT_Y    # dar nu sub guler
        diff = np.abs(state_pixels[..., :3].astype(int) - pixels[..., :3].astype(int)).max(axis=2) > 40
        # nu atingem conturul personajului: silueta stă din poza de repaus, altfel rămâne
        # o linie de 1 px pe marginea fetei (desenul fiecărei stări are conturul puțin diferit)
        inside = _erode(pixels[..., 3] > 24, 3)
        # pe față: tot ce se schimbă; în afara feței: doar ce plutește (decor) și petele
        # mici compacte desenate peste păr (stropi de sudoare), niciodată conturul
        above_collar = np.arange(pixels.shape[0])[:, None] < CUT_Y
        marks = _small_marks(diff & ~face_zone & above_collar)
        zone = _dilate(diff, 7) & ((face_zone & inside) | decor | marks) & visible
        layer = np.zeros_like(state_pixels)
        layer[zone] = state_pixels[zone]
        layer[zone, 3] = 255
        layers[f"expr_{name}"] = Image.fromarray(layer, "RGBA")
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
    # miez tare (acoperă complet ce e dedesubt) + rampa de 5 px pe marginea exterioară:
    # fără rampă, conturul petecului se vede ca o margine de strat pe obraz
    core = _erode(mask, 2)
    ramp = Image.fromarray((core * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(1.2))
    ramp = ramp.point(lambda v: min(255, round(v * 1.6)))
    # ATENȚIE: `Image.paste(state, (0,0), ramp)` premultipliază culoarea (canalul de culoare
    # se înmulțește cu alfa), iar la compunere marginea iese neagră — se vede ca un contur
    # în jurul pleoapelor. `alpha_composite` face matematica corectă.
    source = state.copy()
    source.putalpha(ImageChops.multiply(state.getchannel("A"), ramp))
    layer = Image.new("RGBA", state.size, (0, 0, 0, 0))
    layer.alpha_composite(source)
    return layer


def composite(layers: dict[str, Image.Image], order: list[str] | None = None) -> Image.Image:
    """Reconstruiește cadrul din straturi, în ordinea dată, cu clipping ca în editor."""
    order = order or COMPOSITE_ORDER
    frame = Image.new("RGBA", layers[order[0]].size, (0, 0, 0, 0))
    for name in order:
        if name in HIDDEN_BY_DEFAULT:
            continue
        layer = layers[name]
        mask_name = CLIPPING.get(name)
        if mask_name:
            layer = layer.copy()
            alpha = layer.getchannel("A")
            mask = layers[mask_name].getchannel("A")
            layer.putalpha(ImageChops.multiply(alpha, mask))
        frame.alpha_composite(layer)
    return frame


# Stiva se scrie de la fund în sus (Pytoshop o inversează la scriere), iar DRAW_ORDER se
# DERIVĂ din ea: așa nu pot diverge niciodată ordinea din PSD și cea în care se desenează.
# Gulerul (trup) stă DEASUPRA gâtului, deci cusătura nu se vede când capul se rotește.
GROUPS = [
    ("BACKING", True, ["backing"]),
    ("HEAD", True, ["head"]),
    ("BODY", True, ["body"]),
    # FACE se scrie de sus în jos. Expresiile stau DEASUPRA globilor oculari (le acoperă
    # ochii lor) și SUB pleoape și gură: dacă clipești sau vorbești cât timp râzi, câștigă
    # pleoapa și gura. Masca stă lipită sub globul ei, ca clipping-ul din PSD să fie valid.
    ("FACE", True, ["eyes_closed", "mouth_open"]
     + [f"expr_{name}" for name in reversed(list(EXPRESSIONS))]
     + ["eye_mask_R", "eye_R", "eye_mask_L", "eye_L"]),
]
DRAW_ORDER = [name for _, _, members in reversed(GROUPS) for name in reversed(members)]
COMPOSITE_ORDER = (["backing", "head", "body", "eye_L", "eye_R"]
                   + [f"expr_{name}" for name in EXPRESSIONS]
                   + ["mouth_open", "eyes_closed"])
# Pornesc ascunse în PSD: pleoapele, gura, măștile și toate expresiile (fiecare devine
# vizibilă doar pe parametrul ei, în editor)
HIDDEN_BY_DEFAULT = ({"eyes_closed", "mouth_open", "eye_mask_L", "eye_mask_R"}
                     | {f"expr_{name}" for name in EXPRESSIONS})
CLIPPING = {"eye_L": "eye_mask_L", "eye_R": "eye_mask_R"}


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
    # clipping real în PSD („clip to layer below"), ca editorul să taie singur globul
    records = psd.layer_and_mask_info.layer_info.layer_records
    by_name = {record.name.strip("\x00"): record for record in records}
    for layer_name in CLIPPING:
        if layer_name in by_name:
            by_name[layer_name].clipping = True
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
] + [
    (param, "ParamGroupExpressions", label, 0, 1, 0)
    for _name, (_file, param, label) in EXPRESSIONS.items()
]

PARAMETER_GROUPS = [
    ("ParamGroupFace", "Față"),
    ("ParamGroupEyes", "Ochii deschiși închiși"),
    ("ParamGroupEyeballs", "Glob ocular"),
    ("ParamGroupBrows", "Sprâncene"),
    ("ParamGroupMouth", "Gură"),
    ("ParamGroupBody", "Corp"),
    ("ParamGroupSway", "Fizică"),
    ("ParamGroupExpressions", "Expresii"),
]


def model3(texture: str = "texture_00.png") -> dict:
    return {
        "Version": 3,
        "FileReferences": {
            "Moc": "izentric.moc3",
            "Textures": [texture],
            "DisplayInfo": "izentric.cdi3.json",
            "Expressions": [
                {"Name": label, "File": f"izentric.{name}.exp3.json"}
                for name, (_file, _param, label) in EXPRESSIONS.items()
            ],
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
                "layers": ["head", "eye_L", "eye_R", "eyes_closed", "mouth_open"]
                + [f"expr_{name}" for name in EXPRESSIONS],
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
                {"value": -1, "layers": ["eye_L", "eye_R"], "translate": [-3, 0]},
                {"value": 0, "layers": ["eye_L", "eye_R"], "translate": [0, 0]},
                {"value": 1, "layers": ["eye_L", "eye_R"], "translate": [3, 0]},
            ],
            "ParamEyeBallY": [
                {"value": -1, "layers": ["eye_L", "eye_R"], "translate": [0, -3]},
                {"value": 0, "layers": ["eye_L", "eye_R"], "translate": [0, 0]},
                {"value": 1, "layers": ["eye_L", "eye_R"], "translate": [0, 3]},
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
            **{
                param: [
                    {"value": 0, "layer": f"expr_{name}", "opacity": 0},
                    {"value": 1, "layer": f"expr_{name}", "opacity": 100},
                ]
                for name, (_file, param, _label) in EXPRESSIONS.items()
            },
        },
        "expressions": [
            {"name": name, "parameter": param, "label": label, "file": f"izentric.{name}.exp3.json"}
            for name, (_file, param, label) in EXPRESSIONS.items()
        ],
        "notes": [
            "eyes_closed și mouth_open se pot lega și pe opacitate (mai simplu) sau pe clipping (mai curat).",
            "eye_L / eye_R au nevoie de clipping pe eye_mask_L / eye_mask_R, altfel iese ochiul din gene.",
            "Sprâncenele sunt desenate în cap: ParamBrowLY/RY există în cdi3, dar nu au ce mișca până nu sunt pe strat separat.",
        ],
    }


def expression_file(target: str) -> dict:
    """Un fișier .exp3: pune expresia cerută pe 1 și pe toate celelalte pe 0.

    Formatul e cel din Cubism (Type + Parameters cu Id/Value/Blend + timpii de fade), la fel
    cum îl citește VTube Studio când le încarcă din model3.json.
    """
    return {
        "Type": "Live2D Expression",
        "Parameters": [
            {"Id": param, "Value": 1.0 if name == target else 0.0, "Blend": "Overwrite"}
            for name, (_file, param, _label) in EXPRESSIONS.items()
        ],
        "FadeInTime": 0.2,
        "FadeOutTime": 0.2,
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
    for name in EXPRESSIONS:
        payload = expression_file(name)
        path = directory / f"izentric.{name}.exp3.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        written[path.name] = path
    return written


PACK_FILES = (("izentric.psd", "izentric.rigspec.json", "izentric.model3.json", "izentric.cdi3.json",
               "GATA-DE-RIGAT.txt") + tuple(f"izentric.{name}.exp3.json" for name in EXPRESSIONS))


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
