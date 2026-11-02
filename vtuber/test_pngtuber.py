from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image, ImageChops

from pngtuber import ASSETS, CONFIG, Composer, Director, check, load_config


def config() -> dict:
    return load_config(CONFIG)


def same(a: Image.Image, b: Image.Image) -> bool:
    return ImageChops.difference(a.convert("RGBA"), b.convert("RGBA")).getbbox(alpha_only=False) is None


def test_config_points_to_real_transparent_images():
    cfg = config()
    assert check(cfg) == 0
    for name in cfg["assets"].values():
        image = Image.open(ASSETS / name)
        assert image.mode == "RGBA"
        assert image.getchannel("A").getbbox() is not None


def test_every_state_used_by_a_rule_exists():
    cfg = config()
    for rule in cfg["rules"]:
        assert rule["name"] in cfg["assets"]
        assert rule["holdSeconds"] > 0
        assert rule["cooldownSeconds"] >= 0
        assert rule["when"]


def test_silent_is_idle_and_loud_is_talking():
    director = Director(config(), rng=random.Random(0))
    director.blink_min = director.blink_max = 100.0
    assert director.update(0.0, mic=0.0) == "idle.png"
    assert director.update(0.1, mic=0.5) == "talking.png"


def test_talking_hangs_over_after_voice_stops():
    cfg = config()
    director = Director(cfg, rng=random.Random(0))
    director.blink_min = director.blink_max = 100.0
    director.update(0.0, mic=0.5)
    assert director.update(0.1, mic=0.0) == "talking.png"
    assert director.update(0.1 + cfg["talk"]["hangoverSeconds"] + 0.01, mic=0.0) == "idle.png"


def test_blink_when_idle_and_while_talking():
    cfg = config()
    cfg["blink"] = {"minIntervalSeconds": 0.05, "maxIntervalSeconds": 0.05, "durationSeconds": 0.13}
    director = Director(cfg, rng=random.Random(0))
    assert director.update(0.0) == "idle.png"
    assert director.update(0.06) == "blink.png"
    assert director.update(0.30) == "idle.png"
    director.update(1.0, mic=0.8)
    assert director.update(1.06, mic=0.8) == "talking_blink.png"


def test_laugh_triggered_by_face_and_respects_hold_and_cooldown():
    cfg = config()
    director = Director(cfg, rng=random.Random(0))
    director.blink_min = director.blink_max = 100.0
    smile = {"mouthSmileLeft": 0.5, "mouthSmileRight": 0.5, "jawOpen": 0.5, "eyeSquintLeft": 0.3}
    assert director.update(0.0, face=smile) == "laugh.png"
    assert director.update(1.0, face={}) == "laugh.png"
    assert director.update(1.7, face={}) == "idle.png"
    assert director.update(2.0, face=smile) == "idle.png"
    assert director.update(5.0, face=smile) == "laugh.png"


def test_shocked_beats_laugh_when_both_match():
    cfg = config()
    director = Director(cfg, rng=random.Random(0))
    face = {
        "jawOpen": 0.9,
        "browInnerUp": 0.9,
        "mouthSmileLeft": 0.5,
        "mouthSmileRight": 0.5,
        "eyeSquintLeft": 0.3,
    }
    assert director.update(0.0, face=face) == "shocked.png"


def test_manual_hotkey_wins_and_expires():
    director = Director(config(), rng=random.Random(0))
    director.blink_min = director.blink_max = 100.0
    director.tap("love", 0.0, hold_seconds=1.0)
    assert director.update(0.5) == "love.png"
    assert director.update(1.5) == "idle.png"


def test_composer_crossfades_between_two_images():
    cfg = config()
    composer = Composer(ASSETS, cfg)
    composer.set_asset("idle.png", 0.0)
    assert same(composer.frame(0.0), composer.image("idle.png"))

    assert composer.set_asset("talking.png", 1.0) is True
    assert composer.set_asset("talking.png", 1.0) is False
    start = composer.frame(1.0)
    assert same(start, composer.image("idle.png"))

    middle = composer.frame(1.0 + cfg["motion"]["fadeSeconds"] / 2)
    assert not same(middle, composer.image("idle.png"))
    assert not same(middle, composer.image("talking.png"))
    assert same(composer.frame(1.0 + cfg["motion"]["fadeSeconds"]), composer.image("talking.png"))


def test_composer_bob_offset_follows_sine():
    cfg = config()
    composer = Composer(ASSETS, cfg)
    period = cfg["motion"]["bobPeriodSeconds"]
    amplitude = cfg["motion"]["bobPixels"]
    assert composer.offset(0.0) == 0
    assert composer.offset(period / 4) == amplitude
    assert composer.offset(period / 2) == 0
    assert composer.offset(3 * period / 4) == -amplitude


def test_composer_punch_keeps_canvas_size():
    composer = Composer(ASSETS, config())
    composer.set_asset("laugh.png", 0.0)
    frame = composer.frame(0.0)
    assert frame.size == composer.image("laugh.png").size
    assert not same(frame, composer.image("laugh.png"))
    assert same(composer.frame(1.0), composer.image("laugh.png"))


def test_overlay_loop_runs_with_fake_tkinter(monkeypatch, tmp_path):
    """Fereastra nu poate fi deschisă în sandbox, dar bucla poate fi rulată pe un Tk fals."""
    import sys
    import types

    calls = {"geometry": [], "images": 0, "binds": [], "after": 0}

    class FakeCanvas:
        def __init__(self, *_args, **_kwargs):
            self.items = {}
            self.photo = None

        def pack(self, *_args, **_kwargs):
            pass

        def create_image(self, *_args, **kwargs):
            calls["images"] += 1
            self.items[1] = kwargs
            return 1

        def itemconfigure(self, index, **kwargs):
            calls["images"] += 1
            self.items[index].update(kwargs)

        def bind(self, sequence, _function):
            calls["binds"].append(sequence)

    class FakeLabel:
        def __init__(self, *_args, **_kwargs):
            pass

        def place(self, **_kwargs):
            pass

        def configure(self, **_kwargs):
            pass

    class FakeRoot:
        def __init__(self):
            self.position = (0, 0)

        def title(self, *_args):
            pass

        def overrideredirect(self, *_args):
            pass

        def attributes(self, *_args):
            pass

        def configure(self, **_kwargs):
            pass

        def geometry(self, value=None):
            if value:
                calls["geometry"].append(value)
                coordinates = value.split("+")
                self.position = (int(coordinates[1]), int(coordinates[2]))

        def bind(self, sequence, _function):
            calls["binds"].append(sequence)

        def focus_force(self):
            pass

        def winfo_x(self):
            return self.position[0]

        def winfo_y(self):
            return self.position[1]

        def after(self, _delay, function):
            calls["after"] += 1
            if calls["after"] < 6:
                function()

        def mainloop(self):
            pass

        def destroy(self):
            pass

    fake_tk = types.ModuleType("tkinter")
    fake_tk.Tk = FakeRoot
    fake_tk.Canvas = FakeCanvas
    fake_tk.Label = FakeLabel
    monkeypatch.setitem(sys.modules, "tkinter", fake_tk)

    fake_image_tk = types.ModuleType("PIL.ImageTk")

    class FakePhoto:
        def __init__(self, image):
            self.image = image

    fake_image_tk.PhotoImage = FakePhoto
    monkeypatch.setitem(sys.modules, "PIL.ImageTk", fake_image_tk)
    import PIL

    monkeypatch.setattr(PIL, "ImageTk", fake_image_tk, raising=False)

    import pngtuber

    monkeypatch.setattr(pngtuber, "POSITION", tmp_path / "overlay.json")

    class FakeMic:
        def __init__(self, *_args):
            pass

        def read(self):
            return 0.4

        def close(self):
            pass

    monkeypatch.setattr(pngtuber, "MicLevel", FakeMic)

    class Args:
        mic = True
        face = False
        device = None
        camera = 0
        model_path = None
        bg = "00ff00"
        x = 60
        y = 60
        debug = True
        puppet = False

    assert pngtuber.run_overlay(config(), Args()) == 0
    assert calls["images"] >= 1
    assert calls["after"] == 6
    assert any(value.startswith("720x720+60+") for value in calls["geometry"])
    assert (tmp_path / "overlay.json").exists()
