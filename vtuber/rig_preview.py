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

LAYER_FILES = ("head", "body", "iris_L", "iris_R", "eyes_closed", "mouth_open", "eye_mask_L", "eye_mask_R")

# valorile din rigspec
PIVOT = (512, 655)
HEAD_PX_PER_DEGREE_X = 14 / 30
HEAD_PX_PER_DEGREE_Y = 10 / 30
HEAD_DEGREES_PER_DEGREE_Z = 8 / 30
IRIS_PX_X = 11.0
IRIS_PX_Y = 9.0


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def load_layers(directory: Path = RIG) -> dict[str, Image.Image]:
    layers = {}
    for name in LAYER_FILES:
        layers[name] = Image.open(directory / f"{name}.png").convert("RGBA")
    return layers


def _shift(image: Image.Image, dx: float, dy: float) -> Image.Image:
    """Mută un strat fără să taie din el (păstrează aceeași pânză)."""
    if abs(dx) < 0.01 and abs(dy) < 0.01:
        return image
    canvas = Image.new("RGBA", image.size, (0, 0, 0, 0))
    canvas.alpha_composite(image, (round(dx), round(dy)))
    return canvas


def _clip(layer: Image.Image, mask: Image.Image) -> Image.Image:
    """Taie un strat după o mască (înlocuiește clipping-ul din PSD)."""
    clipped = layer.copy()
    alpha = clipped.getchannel("A")
    clipped.putalpha(Image.composite(alpha, Image.new("L", clipped.size, 0), mask.getchannel("A")))
    return clipped


def _face_stack(layers: dict[str, Image.Image], eyeball_x: float, eyeball_y: float,
                eye_open: float, mouth: float) -> Image.Image:
    stack = layers["head"].copy()

    for side in ("L", "R"):
        iris = _shift(layers[f"iris_{side}"], eyeball_x * IRIS_PX_X, eyeball_y * IRIS_PX_Y)
        stack.alpha_composite(_clip(iris, layers[f"eye_mask_{side}"]))

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
           eye_open: float = 1.0, mouth: float = 0.0) -> Image.Image:
    """Un cadru: fața se mișcă rigid (rotire + alunecare), corpul stă pe loc."""
    face = _face_stack(layers, eyeball_x, eyeball_y, eye_open, mouth)

    degrees = angle_z * HEAD_DEGREES_PER_DEGREE_Z
    moved = face.rotate(-degrees, resample=Image.BICUBIC, center=PIVOT)
    moved = _shift(moved, angle_x * HEAD_PX_PER_DEGREE_X, angle_y * HEAD_PX_PER_DEGREE_Y)

    body = layers["body"]
    if abs(angle_x) > 0.01:
        body = body.rotate(-angle_x * 0.15, resample=Image.BICUBIC, center=(512, 1024))

    frame = moved.copy()
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
