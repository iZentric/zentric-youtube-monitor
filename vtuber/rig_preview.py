"""Previzualizare animată a rigului — exact valorile din `rig/izentric.rigspec.json`.

Nu e o poză nouă și nu e un personaj inventat: se iau straturile din `rig/` (cap, corp,
irisuri, pleoape, gură) și se mișcă după aceleași reguli care ajung în fișierul de rig:
  ParamAngleZ ±30° → ±8° rotație a capului în jurul gâtului (512, 655)
  ParamAngleX ±30° → ±14 px pe orizontală
  ParamAngleY ±30° → ∓10 px pe verticală
  ParamEyeBallX/Y ±1 → ±11 / ±9 px, tăiate de măștile ochilor
  ParamEyeL/ROpen 0→1 → pleoapele apar cu opacitate
  ParamMouthOpenY 0→1 → gura apare cu opacitate

Scopul e verificarea: cadrul de repaus trebuie să iasă identic cu `idle.png`, iar cel cu
ochii închiși identic cu `blink.png`. Dacă iese, rigul chiar face ce promite fișierul.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
RIG = HERE / "rig"
ASSETS = HERE / "assets"

LAYER_FILES = ("backing", "head", "body", "iris_L", "iris_R", "eye_L", "eye_R", "eyes_closed",
               "mouth_open", "eye_mask_L", "eye_mask_R",
               "expr_laugh", "expr_love", "expr_sad", "expr_shocked", "expr_sus")
EXPRESSION_LAYERS = ("expr_laugh", "expr_love", "expr_sad", "expr_shocked", "expr_sus")

# valorile din rigspec
PIVOT = (512, 655)
ROTATION_CENTER = (512, 700)   # cât mai jos în gât, ca gulerul să nu se miște
WARP_ANCHOR = 655      # la guler deplasarea e zero (capul se deformează, nu alunecă întreg)
WARP_TOP = 37          # vârful capului: aici deplasarea e maximă
HEAD_PX_PER_DEGREE_X = 14 / 30
HEAD_PX_PER_DEGREE_Y = 10 / 30
HEAD_DEGREES_PER_DEGREE_Z = 8 / 30
IRIS_PX_X = 4.0
IRIS_PX_Y = 4.0


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def load_layers(directory: Path = RIG) -> dict[str, Image.Image]:
    layers = {}
    for name in LAYER_FILES:
        path = directory / f"{name}.png"      # irisul există doar în varianta cu iris separat
        if path.exists():
            layers[name] = Image.open(path).convert("RGBA")
    return layers


def _shift(image: Image.Image, dx: float, dy: float) -> Image.Image:
    """Mută un strat fără să taie din el (păstrează aceeași pânză)."""
    if abs(dx) < 0.01 and abs(dy) < 0.01:
        return image
    canvas = Image.new("RGBA", image.size, (0, 0, 0, 0))
    canvas.alpha_composite(image, (round(dx), round(dy)))
    return canvas


def _warp_head(image: Image.Image, dx: float, dy: float) -> Image.Image:
    """Deplasare care scade la zero spre guler — ca un warp, nu ca o alunecare rigidă.

    Dacă tot capul s-ar muta cu 14 px, gâtul ar ieși din guler și s-ar vedea gol (sau un
    petec inventat). Așa, baza gâtului rămâne pe loc și nu se descoperă nimic.
    """
    import numpy as np

    if abs(dx) < 0.01 and abs(dy) < 0.01:
        return image
    pixels = np.asarray(image).astype(np.float32)
    height, width = pixels.shape[:2]
    rows = np.arange(height)
    ramp = np.clip((WARP_ANCHOR - rows) / max(1, WARP_ANCHOR - WARP_TOP), 0.0, 1.0)
    out = np.zeros_like(pixels)
    for y in range(height):
        source_y = y - dy * ramp[y]
        y0 = int(np.floor(source_y))
        fy = source_y - y0
        top = pixels[min(max(y0, 0), height - 1)]
        bottom = pixels[min(max(y0 + 1, 0), height - 1)]
        row = top * (1 - fy) + bottom * fy
        shift = dx * ramp[y]
        xs = np.arange(width) - shift
        x0 = np.floor(xs).astype(int)
        fx = (xs - x0)[:, None]
        left = row[np.clip(x0, 0, width - 1)]
        right = row[np.clip(x0 + 1, 0, width - 1)]
        out[y] = left * (1 - fx) + right * fx
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def _shear(image: Image.Image, amount: float, start: int = 800) -> Image.Image:
    """Împinge corpul lateral, din ce în ce mai mult spre talie — ca un warp, nu ca o rotire.

    Sub `start` (800) nu se mișcă nimic: gulerul și deschizătura husei rămân pe loc, deci
    nu se poate deschide nici un gol de 1 px între gât și guler.
    """
    import numpy as np

    if abs(amount) < 0.01:
        return image
    pixels = np.asarray(image)
    height, width = pixels.shape[:2]
    out = np.zeros_like(pixels)
    for y in range(height):
        ratio = max(0.0, (y - start) / (height - start)) ** 1.5 if y > start else 0.0
        dx = int(round(amount * ratio))
        if dx == 0:
            out[y] = pixels[y]
        elif dx > 0:
            out[y, dx:] = pixels[y, : width - dx]
        else:
            out[y, : width + dx] = pixels[y, -dx:]
    return Image.fromarray(out)


def _clip(layer: Image.Image, mask: Image.Image) -> Image.Image:
    """Taie un strat după o mască (înlocuiește clipping-ul din PSD)."""
    clipped = layer.copy()
    alpha = clipped.getchannel("A")
    clipped.putalpha(Image.composite(alpha, Image.new("L", clipped.size, 0), mask.getchannel("A")))
    return clipped


def _face_stack(layers: dict[str, Image.Image], eyeball_x: float, eyeball_y: float,
                eye_open: float, mouth: float,
                expressions: dict[str, float] | None = None) -> Image.Image:
    stack = layers["head"].copy()

    # Globul ocular alunecă întreg (alb + iris + reflexe) pe sub gene; masca deschiderii îl
    # ține în ochi. Așa nu rămâne nimic din desenul de dedesubt când privirea se mută.
    for side in ("L", "R"):
        eyeball = _shift(layers[f"eye_{side}"], eyeball_x * IRIS_PX_X, eyeball_y * IRIS_PX_Y)
        stack.alpha_composite(_clip(eyeball, layers[f"eye_mask_{side}"]))

    # expresiile stau DEASUPRA globilor (le acoperă ochii desenați) și SUB pleoape
    for name in EXPRESSION_LAYERS:
        amount = (expressions or {}).get(name.removeprefix("expr_"), 0.0)
        if amount <= 0:
            continue
        expression = layers[name].copy()
        expression.putalpha(expression.getchannel("A").point(lambda v: round(v * amount)))
        stack.alpha_composite(expression)

    closed = smoothstep((0.6 - eye_open) / 0.4)
    if closed > 0:
        eyelids = layers["eyes_closed"].copy()
        eyelids.putalpha(eyelids.getchannel("A").point(lambda v: round(v * closed)))
        stack.alpha_composite(eyelids)

    opened = smoothstep(mouth)
    if opened > 0:
        mouth_layer = layers["mouth_open"].copy()
        mouth_layer.putalpha(mouth_layer.getchannel("A").point(lambda v: round(v * opened)))
        stack.alpha_composite(mouth_layer)

    return stack


def render(layers: dict[str, Image.Image], angle_x: float = 0.0, angle_y: float = 0.0,
           angle_z: float = 0.0, eyeball_x: float = 0.0, eyeball_y: float = 0.0,
           eye_open: float = 1.0, mouth: float = 0.0,
           expressions: dict[str, float] | None = None) -> Image.Image:
    """Un cadru: fața se mișcă rigid (rotire + alunecare), corpul stă pe loc."""
    face = _face_stack(layers, eyeball_x, eyeball_y, eye_open, mouth, expressions)

    degrees = angle_z * HEAD_DEGREES_PER_DEGREE_Z
    moved = face.rotate(-degrees, resample=Image.BICUBIC, center=ROTATION_CENTER)
    moved = _warp_head(moved, angle_x * HEAD_PX_PER_DEGREE_X, angle_y * HEAD_PX_PER_DEGREE_Y)

    body = _shear(layers["body"], angle_x * 0.55)   # warp de corp: 0 la guler, maxim jos

    frame = layers["backing"].copy()     # spatele gulerului: ce se vede prin deschizătură
    frame.alpha_composite(moved)
    frame.alpha_composite(body)          # corpul stă deasupra: gulerul acoperă cusătura
    return frame


def _blink(now: float) -> float:
    """Două clipiri scurte pe buclă, ca să se vadă că pleoapele sunt legate."""
    for start in (0.30, 0.72):
        phase = (now - start) / 0.10
        if 0.0 <= phase <= 1.0:
            return 1.0 - abs(phase * 2 - 1)
    return 0.0


def animation(layers: dict[str, Image.Image], frames: int = 90, fps: int = 15) -> list[Image.Image]:
    """Buclă de 6 secunde: capul se uită stânga–dreapta, clipește, vorbește."""
    import math

    out = []
    for index in range(frames):
        now = (index / frames) % 1.0
        angle_x = 22 * math.sin(2 * math.pi * now)
        angle_y = 7 * math.sin(4 * math.pi * now + 0.8)
        angle_z = 5 * math.sin(2 * math.pi * now + 1.9)
        talking = 0.5 + 0.5 * math.sin(2 * math.pi * 3.2 * now)
        mouth = smoothstep((talking - 0.25) / 0.5) * 0.9
        out.append(render(layers, angle_x, angle_y, angle_z,
                          eyeball_x=angle_x / 30, eyeball_y=-angle_y / 30,
                          eye_open=1.0 - _blink(now), mouth=mouth))
    return out


def write_gif(path: Path = RIG / "preview.gif", size: int = 480) -> Path:
    layers = load_layers()
    frames = animation(layers)
    small = [frame.resize((size, size), Image.LANCZOS) for frame in frames]
    small[0].save(path, save_all=True, append_images=small[1:], duration=1000 // 15, loop=0, optimize=True)
    return path


def main() -> None:
    path = write_gif()
    print(f"scris {path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
