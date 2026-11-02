"""Păpușă pe straturi extrase din pozele tale: ochi și gură separate, plus legănare după cap.

Pozele primite sunt aplatizate, dar `idle`, `blink`, `talking` și `talking_blink` sunt
desenate pe aceeași bază: diferența dintre ele e doar zona ochilor, respectiv a gurii.
Modulul extrage cele două zone ca straturi (cu margini estompate) și le compune peste
baza `idle`, ca să miști doar gura și pleoapele, nu tot personajul.

Diferența față de comutarea de imagini întregi: la clipit și la vorbit nu se mai
schimbă tot cadrul, ci doar zona care trebuie — și gura poate sta deschisă cât timp
ochii clipesc, fără o imagine dedicată.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageFilter

HERE = Path(__file__).parent
ASSETS = HERE / "assets"
CONFIG = HERE / "states.izentric.json"

# stările desenate pe aceeași bază (singurele la care se pot aplica straturile)
LAYERED = ("idle.png", "blink.png", "talking.png", "talking_blink.png")


def _component_filter(mask, min_area: int = 400):
    """Ține doar petele mari; aruncă zgomotul de compresie din restul cadrului."""
    import numpy as np

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


def difference_mask(first: Image.Image, second: Image.Image, threshold: float = 40.0, feather: int = 7) -> Image.Image:
    """Masca zonei care diferă între două stări, cu margini estompate."""
    import numpy as np

    a = np.asarray(first.convert("RGBA")).astype(np.float32)
    b = np.asarray(second.convert("RGBA")).astype(np.float32)
    changed = np.abs(a - b).max(axis=2) > threshold
    if not changed.any():
        return Image.new("L", first.size, 0)
    # etichetarea se face la 1/4 din rezoluție: de 16 ori mai puțin de parcurs, aceleași pete
    small = Image.fromarray((changed * 255).astype(np.uint8), "L")
    small = small.resize((max(1, first.width // 4), max(1, first.height // 4)), Image.BOX)
    core_small = _component_filter(np.asarray(small) > 40, min_area=25)
    if core_small.any():
        core = np.asarray(Image.fromarray((core_small * 255).astype(np.uint8), "L").resize(first.size, Image.NEAREST)) > 40
    else:
        core = changed
    mask = Image.fromarray((core * 255).astype(np.uint8), "L")
    return mask.filter(ImageFilter.MaxFilter(feather)).filter(ImageFilter.GaussianBlur(feather))


class Puppet:
    """Stări + straturi + legănare. Fără fereastră și fără ceas real, deci se poate testa."""

    def __init__(self, assets_dir: Path = ASSETS, output_height: int = 720, motion: dict | None = None):
        self.dir = Path(assets_dir)
        motion = motion or {}
        self.punch_scale = float(motion.get("punchScale", 1.03))
        self.punch_seconds = float(motion.get("punchSeconds", 0.15))
        self.bob_amplitude = int(motion.get("bobPixels", 3))
        self.bob_period = float(motion.get("bobPeriodSeconds", 4.0))
        self.sway_degrees = float(motion.get("swayDegrees", 3.0))
        self.punch_states = set(motion.get("punchStates", []))

        self.base = Image.open(self.dir / "idle.png").convert("RGBA")
        self.eyes_closed = Image.open(self.dir / "blink.png").convert("RGBA")
        self.mouth_open = Image.open(self.dir / "talking.png").convert("RGBA")
        self.eye_mask = difference_mask(self.base, self.eyes_closed)
        self.mouth_mask = difference_mask(self.base, self.mouth_open)
        # totul se aduce la înălțimea de afișare o singură dată (altfel cadrul iese decupat)
        self.height = output_height
        self.base = self._fit(self.base)
        self.eyes_closed = self._fit(self.eyes_closed)
        self.mouth_open = self._fit(self.mouth_open)
        self.eye_mask = self.eye_mask.resize(self.base.size, Image.BILINEAR)
        self.mouth_mask = self.mouth_mask.resize(self.base.size, Image.BILINEAR)

        self._scaled: dict[str, Image.Image] = {}
        self.current = "idle.png"
        self._punch_start: float | None = None
        self._fade_start: float | None = None
        self._fade_from: str | None = None
        self.fade = float(motion.get("fadeSeconds", 0.09))

        self._mouth = 0.0
        self._eyes_closed = 0.0
        self._pose = (0.0, 0.0)
        self._mask_cache: dict[tuple[str, int], Image.Image] = {}
        self._split: Image.Image | None = None
        self._cache_key: tuple | None = None
        self._cache_image: Image.Image | None = None

    # ---------- intrări ----------

    def set_inputs(self, mic: float, face: dict, threshold: float = 0.05) -> None:
        """Voce + expresii → cât de deschisă e gura și cât de închiși sunt ochii."""
        jaw = float(face.get("jawOpen", 0.0))
        level = max(0.0, min(1.0, (mic - threshold * 0.6) / max(threshold * 3.0, 1e-6)))
        target_mouth = max(level, jaw)
        blink = (float(face.get("eyeBlinkLeft", 0.0)) + float(face.get("eyeBlinkRight", 0.0))) / 2
        self._mouth = self._smooth(self._mouth, target_mouth, attack=0.55, release=0.18)
        self._eyes_closed = self._smooth(self._eyes_closed, blink, attack=0.75, release=0.75)
        self._pose = (float(face.get("poseX", 0.0)), float(face.get("poseY", 0.0)))

    @staticmethod
    def _smooth(current: float, target: float, attack: float, release: float) -> float:
        rate = attack if target > current else release
        return current + (target - current) * rate

    def set_asset(self, asset: str, now: float) -> bool:
        if asset == self.current:
            return False
        self._fade_from = self.current if self.current in LAYERED else None
        self.current = asset
        self._fade_start = now if self._fade_from else None
        self._punch_start = now if Path(asset).stem in self.punch_states else None
        return True

    # ---------- randare ----------

    def _fit(self, image: Image.Image) -> Image.Image:
        if image.height == self.height:
            return image
        width = max(1, round(image.width * self.height / image.height))
        return image.resize((width, self.height), Image.LANCZOS)

    def image(self, asset: str) -> Image.Image:
        if asset not in self._scaled:
            source = Image.open(self.dir / asset).convert("RGBA")
            width = max(1, round(source.width * self.height / source.height))
            self._scaled[asset] = source.resize((width, self.height), Image.LANCZOS)
        return self._scaled[asset]

    @staticmethod
    def _bucket(value: float) -> int:
        return int(max(0.0, min(1.0, value)) * 10)

    def _mask(self, name: str, amount: float) -> Image.Image:
        """Masca e decupată pe 10 trepte și ținută minte — altfel `point` costă ~10 ms pe cadru."""
        bucket = self._bucket(amount)
        key = (name, bucket)
        if key not in self._mask_cache:
            source = self.eye_mask if name == "eyes" else self.mouth_mask
            self._mask_cache[key] = source.point(lambda value: (value * bucket) // 10)
        return self._mask_cache[key]

    def compose(self, mouth: float, eyes_closed: float, pose: tuple[float, float] = (0.0, 0.0)) -> Image.Image:
        """Cadrul: bază `idle` + gura deschisă + pleoapele închise (+ legănare)."""
        frame = self.base.copy()
        if mouth > 0.5:
            frame.paste(self.mouth_open, (0, 0), self._mask("mouth", (mouth - 0.5) / 0.1))
        if eyes_closed > 0.5:
            frame.paste(self.eyes_closed, (0, 0), self._mask("eyes", (eyes_closed - 0.5) / 0.25))
        return self._sway(frame, pose)

    def _sway(self, frame: Image.Image, pose: tuple[float, float]) -> Image.Image:
        """Capul se înclină după poziția feței în cameră; corpul rămâne pe loc.

        Se rotește doar banda capului (nu tot cadrul), apoi se lipește peste original
        cu o tranziție estompată la linia umerilor.
        """
        dx, dy = pose
        if abs(dx) < 0.01 and abs(dy) < 0.01:
            return frame
        head_height = int(frame.height * 0.70)
        head = frame.crop((0, 0, frame.width, head_height))
        angle = -max(-1.0, min(1.0, dx)) * self.sway_degrees
        rotated = head.rotate(angle, resample=Image.BILINEAR, center=(head.width / 2, head.height * 0.92))
        moved = Image.new("RGBA", head.size, (0, 0, 0, 0))
        moved.alpha_composite(rotated, (round(dx * frame.width * 0.02), round(dy * frame.height * 0.02)))
        if self._split is None:
            split = Image.new("L", frame.size, 0)
            split.paste(255, (0, 0, frame.width, int(frame.height * 0.62)))
            self._split = split.filter(ImageFilter.GaussianBlur(12))
        out = frame.copy()
        out.paste(moved, (0, 0), self._split.crop((0, 0, frame.width, head_height)))
        return out

    def frame(self, now: float) -> Image.Image:
        if self.current not in LAYERED:
            image = self.image(self.current)
            if self._punch_start is not None:
                progress = (now - self._punch_start) / self.punch_seconds if self.punch_seconds > 0 else 1.0
                if progress < 1.0:
                    return self._scaled_up(image, self.punch_scale - (self.punch_scale - 1.0) * progress)
                self._punch_start = None
            return image

        key = (self.current, self._bucket(self._mouth), self._bucket(self._eyes_closed), self._bucket(self._pose[0] + 1) / 2, self._bucket(self._pose[1] + 1) / 2)
        if key == self._cache_key and self._cache_image is not None:
            return self._cache_image
        self._cache_key = key
        composed = self.compose(self._mouth, self._eyes_closed, self._pose)
        if self._fade_from is not None and self._fade_start is not None:
            progress = (now - self._fade_start) / self.fade if self.fade > 0 else 1.0
            if progress < 1.0:
                previous = self.image(self._fade_from)
                current = composed.resize(previous.size, Image.LANCZOS)
                return Image.blend(previous, current, progress)
            self._fade_from = None
            self._fade_start = None
        self._cache_image = composed
        return composed

    def _scaled_up(self, image: Image.Image, factor: float) -> Image.Image:
        width, height = image.size
        scaled = image.resize((max(1, round(width * factor)), max(1, round(height * factor))), Image.LANCZOS)
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        canvas.alpha_composite(scaled, ((width - scaled.width) // 2, (height - scaled.height) // 2))
        return canvas

    def offset(self, now: float) -> int:
        if self.bob_amplitude <= 0 or self.bob_period <= 0:
            return 0
        import math

        return round(self.bob_amplitude * math.sin(2 * math.pi * now / self.bob_period))

    @property
    def animating(self) -> bool:
        return True


def load_config(path: Path = CONFIG) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
