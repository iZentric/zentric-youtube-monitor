"""Overlay cu personajul iZentric: 9 imagini conduse automat de voce și de față.

Motorul (Director) decide ce imagine se vede; Composer face trecerea între imagini
(fade scurt, „punch” la reacții, balans la respirație). Fereastra tkinter doar afișează.

Rulare:
    python vtuber/pngtuber.py --check          # validează pozele și configul
    python vtuber/pngtuber.py --mic            # voce (fără cameră)
    python vtuber/pngtuber.py --mic --face     # voce + expresii faciale
    python vtuber/pngtuber.py --mic --face --bg ff00ff --height 900

În OBS: Sursă > Captură fereastră > fereastra „iZentric” + filtru Chroma Key pe culoarea --bg.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
ASSETS = HERE / "assets"
CONFIG = HERE / "states.izentric.json"
POSITION = HERE / "overlay.json"

HOTKEYS = {"1": "laugh", "2": "love", "3": "sad", "4": "shocked", "5": "sus", "0": "idle"}


def load_config(path: Path = CONFIG) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def matches(when: dict, values: dict) -> bool:
    """Aceeași semantică ca în reactions.json: fiecare parametru între min și max."""
    for name, bounds in when.items():
        value = values.get(name)
        if value is None:
            return False
        if value < bounds.get("min", float("-inf")) or value > bounds.get("max", float("inf")):
            return False
    return True


class Director:
    """Alege imaginea curentă. Fără I/O și fără timp real, deci se poate testa."""

    def __init__(self, cfg: dict, rng: random.Random | None = None):
        self.cfg = cfg
        self.assets = cfg["assets"]
        self.rules = cfg.get("rules", [])
        talk = cfg.get("talk", {})
        self.talk_threshold = talk.get("threshold", 0.05)
        self.hangover = talk.get("hangoverSeconds", 0.22)
        blink = cfg.get("blink", {})
        self.blink_min = blink.get("minIntervalSeconds", 2.5)
        self.blink_max = blink.get("maxIntervalSeconds", 6.0)
        self.blink_duration = blink.get("durationSeconds", 0.13)
        self.rng = rng or random.Random()
        self._hold_until: dict[str, float] = {}
        self._cooldown_until: dict[str, float] = {}
        self._last_loud = float("-inf")
        self._next_blink: float | None = None
        self._blink_until = float("-inf")
        self._manual: str | None = None
        self._manual_until = float("-inf")
        self.talking = False

    def tap(self, state: str, now: float, hold_seconds: float = 1.5) -> None:
        """Declanșare manuală (hotkey)."""
        if state not in self.assets:
            raise KeyError(f"stare necunoscută: {state}")
        self._manual = state
        self._manual_until = now + hold_seconds

    def update(self, now: float, mic: float = 0.0, face: dict | None = None) -> str:
        """Întoarce numele fișierului de afișat în clipa `now`."""
        face = face or {}
        if mic >= self.talk_threshold:
            self._last_loud = now
        self.talking = now - self._last_loud <= self.hangover

        state: str | None = None
        if self._manual is not None and now < self._manual_until:
            state = self._manual
        else:
            self._manual = None
            candidates: list[tuple[int, str]] = []
            for rule in self.rules:
                name = rule["name"]
                until = self._hold_until.get(name)
                if until is not None:
                    if now < until:
                        candidates.append((rule.get("priority", 0), name))
                        continue
                    self._hold_until.pop(name)
                    self._cooldown_until[name] = now + rule.get("cooldownSeconds", 3.0)
                if now < self._cooldown_until.get(name, float("-inf")):
                    continue
                if matches(rule.get("when", {}), face):
                    self._hold_until[name] = now + rule.get("holdSeconds", 1.5)
                    candidates.append((rule.get("priority", 0), name))
            if candidates:
                state = max(candidates)[1]

        if state is None:
            state = "talking" if self.talking else "idle"

        if state in ("idle", "talking"):
            if self._next_blink is None:
                self._next_blink = now + self.rng.uniform(self.blink_min, self.blink_max)
            elif now >= self._next_blink:
                self._blink_until = now + self.blink_duration
                self._next_blink = None
            if now < self._blink_until:
                state = "talking_blink" if state == "talking" else "blink"

        return self.assets[state]


class Composer:
    """Compune cadrele: fade între stări, punch la reacții, balans vertical."""

    def __init__(self, assets_dir: Path, cfg: dict):
        self.dir = Path(assets_dir)
        self.height = int(cfg.get("canvas", {}).get("outputHeight", 720))
        motion = cfg.get("motion", {})
        self.fade = float(motion.get("fadeSeconds", 0.09))
        self.bob_amplitude = int(motion.get("bobPixels", 3))
        self.bob_period = float(motion.get("bobPeriodSeconds", 4.0))
        self.punch_scale = float(motion.get("punchScale", 1.03))
        self.punch_seconds = float(motion.get("punchSeconds", 0.15))
        self.punch_states = set(motion.get("punchStates", []))
        self._cache: dict[str, Image.Image] = {}
        self.current: str | None = None
        self._previous: str | None = None
        self._fade_start: float | None = None
        self._punch_start: float | None = None

    def image(self, asset: str) -> Image.Image:
        if asset not in self._cache:
            source = Image.open(self.dir / asset).convert("RGBA")
            width = max(1, round(source.width * self.height / source.height))
            self._cache[asset] = source.resize((width, self.height), Image.LANCZOS)
        return self._cache[asset]

    def set_asset(self, asset: str, now: float) -> bool:
        """Schimbă imaginea; întoarce True dacă s-a schimbat ceva."""
        if asset == self.current:
            return False
        self._previous = self.current
        self.current = asset
        self._fade_start = now if self._previous else None
        self._punch_start = now if Path(asset).stem in self.punch_states else None
        return True

    def _scaled(self, image: Image.Image, factor: float) -> Image.Image:
        width, height = image.size
        scaled = image.resize((max(1, round(width * factor)), max(1, round(height * factor))), Image.LANCZOS)
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        canvas.alpha_composite(scaled, ((width - scaled.width) // 2, (height - scaled.height) // 2))
        return canvas

    @property
    def animating(self) -> bool:
        return self._previous is not None or self._punch_start is not None

    def frame(self, now: float) -> Image.Image:
        """Cadrul de afișat. Fără animație în curs întoarce imaginea simplă."""
        if self.current is None:
            raise RuntimeError("set_asset() trebuie apelat înainte de frame()")
        current = self.image(self.current)
        if self._previous is not None and self._fade_start is not None:
            progress = (now - self._fade_start) / self.fade if self.fade > 0 else 1.0
            if progress >= 1.0:
                self._previous = None
                self._fade_start = None
            else:
                previous = self.image(self._previous)
                if previous.size != current.size:
                    previous = previous.resize(current.size, Image.LANCZOS)
                return Image.blend(previous, current, max(0.0, progress))
        if self._punch_start is not None:
            progress = (now - self._punch_start) / self.punch_seconds if self.punch_seconds > 0 else 1.0
            if progress < 1.0:
                factor = self.punch_scale - (self.punch_scale - 1.0) * max(0.0, progress)
                return self._scaled(current, factor)
            self._punch_start = None
        return current

    def offset(self, now: float) -> int:
        """Deplasare verticală în pixeli (respirație)."""
        if self.bob_amplitude <= 0 or self.bob_period <= 0:
            return 0
        return round(self.bob_amplitude * math.sin(2 * math.pi * now / self.bob_period))


class MicLevel:
    """Nivel RMS de la microfon; import lazy, ca restul să meargă fără sounddevice."""

    def __init__(self, device: int | None = None):
        import sounddevice  # noqa: F401  (verifică instalarea)
        import numpy as np

        self._np = np
        self.stream = sounddevice.InputStream(channels=1, samplerate=16000, dtype="float32", device=device)
        self.stream.start()

    def read(self) -> float:
        try:
            data, _ = self.stream.read(1600)
        except Exception:
            return 0.0
        return float(self._np.sqrt(self._np.mean(self._np.square(data))))

    def close(self) -> None:
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass


def calibrate(device: int | None = None, seconds: float = 5.0) -> int:
    """Măsoară microfonul 3 secunde de tăcere + 2 de voce și sugerează pragul."""
    mic = MicLevel(device)
    print("3 secunde tăcere, apoi 2 secunde vorbește normal...")
    samples: list[float] = []
    start = time.monotonic()
    with_voice = False
    while time.monotonic() - start < seconds:
        if not with_voice and time.monotonic() - start >= 3.0:
            print("   vorbește acum")
            with_voice = True
        samples.append(mic.read())
        time.sleep(0.05)
    mic.close()
    quiet_part = samples[: int(len(samples) * 0.6)] or samples
    quiet = sorted(quiet_part)[len(quiet_part) // 2]
    loud = sorted(samples)[int(len(samples) * 0.95)]
    threshold = round(max(0.01, quiet * 2.0 + 0.005), 3)
    print(f"zgomot de fond {quiet:.3f} / vârf {loud:.3f}")
    if loud <= threshold:
        print("! nu am auzit voce — verifică microfonul sau urcă volumul de intrare")
        return 1
    print(f"pune în states.izentric.json:  \"talk\": {{ \"threshold\": {threshold} }}")
    return 0


def check(cfg: dict, assets_dir: Path = ASSETS) -> int:
    """Verifică pozele și configul înainte de live."""
    problems = 0
    for key, name in cfg["assets"].items():
        path = Path(assets_dir) / name
        if not path.exists():
            print(f"! lipsește {key}: {path}")
            problems += 1
            continue
        with Image.open(path) as image:
            if image.mode != "RGBA":
                print(f"! {name} nu are transparență (mod {image.mode})")
                problems += 1
    for rule in cfg.get("rules", []):
        if rule["name"] not in cfg["assets"]:
            print(f"! regula {rule['name']} nu are imagine în assets")
            problems += 1
    if problems == 0:
        print(f"ok: {len(cfg['assets'])} stări, {len(cfg.get('rules', []))} reguli automate")
    return 1 if problems else 0


def run_overlay(cfg: dict, args) -> int:
    import tkinter as tk

    from PIL import ImageTk

    composer = Composer(ASSETS, cfg)
    director = Director(cfg)

    mic = None
    if args.mic:
        try:
            mic = MicLevel(args.device)
        except Exception as exc:
            print(f"! microfon indisponibil ({exc}) — merg pe hotkey-uri")

    face = None
    if args.face:
        try:
            from facesource import FaceSource

            face = FaceSource(model_path=args.model_path, camera=args.camera).start()
        except Exception as exc:
            print(f"! cameră/expresii indisponibile ({exc}) — merg pe voce + hotkey-uri")

    root = tk.Tk()
    root.title("iZentric")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    background = "#" + args.bg.lstrip("#")
    root.configure(bg=background)

    width = composer.image(cfg["assets"]["idle"]).width
    position = {"x": args.x, "y": args.y}
    if POSITION.exists():
        saved = json.loads(POSITION.read_text(encoding="utf-8"))
        position["x"] = saved.get("x", position["x"])
        position["y"] = saved.get("y", position["y"])
    root.geometry(f"{width}x{composer.height}+{position['x']}+{position['y']}")

    canvas = tk.Canvas(root, width=width, height=composer.height, bg=background, highlightthickness=0)
    canvas.pack()
    item = {"id": None}

    def draw(image):
        photo = ImageTk.PhotoImage(image)
        if item["id"] is None:
            item["id"] = canvas.create_image(width // 2, composer.height // 2, image=photo)
        else:
            canvas.itemconfigure(item["id"], image=photo)
        canvas.image = photo  # ține referința, altfel Tk o colectează

    status = tk.Label(root, text="", bg=background, fg="#7f7f7f")

    def on_key(event):
        state = HOTKEYS.get(event.char)
        if state:
            director.tap(state, time.monotonic())

    drag = {"dx": 0, "dy": 0, "on": False}

    def drag_start(event):
        drag.update(dx=event.x_root - position["x"], dy=event.y_root - position["y"], on=True)

    def drag_move(event):
        if drag["on"]:
            position["x"] = event.x_root - drag["dx"]
            position["y"] = event.y_root - drag["dy"]

    def drag_end(_event):
        drag["on"] = False

    root.bind("<Key>", on_key)
    root.bind("<Escape>", lambda e: root.destroy())
    canvas.bind("<Button-1>", drag_start)
    canvas.bind("<B1-Motion>", drag_move)
    canvas.bind("<ButtonRelease-1>", drag_end)
    root.focus_force()

    def tick():
        now = time.monotonic()
        values = face.update() if face else {}
        level = mic.read() if mic else 0.0
        changed = composer.set_asset(director.update(now, level, values), now)
        if changed or composer.animating:
            draw(composer.frame(now))
        root.geometry(f"{width}x{composer.height}+{position['x']}+{position['y'] + composer.offset(now)}")
        if args.debug:
            status.configure(text=Path(composer.current).stem + (" ♪" if director.talking else ""))
            status.place(relx=0.0, rely=1.0, anchor="sw")
        root.after(33, tick)

    def save_position():
        POSITION.write_text(json.dumps(position), encoding="utf-8")

    tick()
    try:
        root.mainloop()
    finally:
        save_position()
        if mic:
            mic.close()
        if face:
            face.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Overlay VTuber cu stări pentru iZentric")
    parser.add_argument("--config", default=str(CONFIG))
    parser.add_argument("--check", action="store_true", help="validează pozele și configul")
    parser.add_argument("--mic", action="store_true", help="voce → talking")
    parser.add_argument("--face", action="store_true", help="cameră → expresii")
    parser.add_argument("--device", type=int, default=None, help="index microfon")
    parser.add_argument("--camera", type=int, default=0, help="index cameră")
    parser.add_argument("--model-path", default=None, help="face_landmarker.task")
    parser.add_argument("--bg", default="00ff00", help="culoare de fundal pentru chroma key")
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--x", type=int, default=60)
    parser.add_argument("--y", type=int, default=60)
    parser.add_argument("--debug", action="store_true", help="scrie numele stării în colț")
    parser.add_argument("--calibrate", action="store_true", help="măsoară microfonul și sugerează pragul")
    args = parser.parse_args(argv)

    cfg = load_config(Path(args.config))
    if args.height:
        cfg.setdefault("canvas", {})["outputHeight"] = args.height
    if args.check:
        return check(cfg)
    if args.calibrate:
        return calibrate(args.device)
    return run_overlay(cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
