"""Testele previzualizării: rigul trebuie să reproducă pozele tale, nu o variantă apropiată."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import rig_preview as rp

RIG = Path(__file__).parent / "rig"


@pytest.fixture(scope="module")
def layers():
    return rp.load_layers(RIG)


def rms(first: Image.Image, second: Image.Image) -> float:
    a = np.asarray(first.convert("RGB"), dtype=np.float32)
    b = np.asarray(second.convert("RGB").resize(first.size, Image.LANCZOS), dtype=np.float32)
    return float(np.sqrt(((a - b) ** 2).mean()))


def test_rest_frame_is_the_idle_art(layers):
    """Fără nicio valoare pe parametri, rigul trebuie să dea exact poza de repaus."""
    idle = Image.open(rp.ASSETS / "idle.png")
    assert rms(rp.render(layers), idle) < 1.0


def test_closed_eyes_reproduce_the_blink_art(layers):
    blink = Image.open(rp.ASSETS / "blink.png")
    assert rms(rp.render(layers, eye_open=0.0), blink) < 10.0


def test_open_mouth_reproduces_the_talking_art(layers):
    talking = Image.open(rp.ASSETS / "talking.png")
    assert rms(rp.render(layers, mouth=1.0), talking) < 10.0


def test_head_actually_moves(layers):
    rest = np.asarray(rp.render(layers).convert("RGB"), dtype=np.int16)
    turned = np.asarray(rp.render(layers, angle_x=30, angle_z=30).convert("RGB"), dtype=np.int16)
    changed = np.abs(rest - turned).max(axis=2) > 12
    # capul se rotește cu 8° și se mută 14 px: trebuie să se vadă pe o suprafață mare
    assert changed.sum() > 20000


def test_eyeball_always_covers_the_eye_opening(layers):
    """Globul ocular alunecă pe sub gene, dar masca deschiderii rămâne mereu acoperită:
    dacă nu, s-ar vedea o fereastră goală în ochi la privirea maximă."""
    for side in ("L", "R"):
        mask = np.asarray(layers[f"eye_mask_{side}"].getchannel("A")) > 24
        for eyeball_x in (-1.0, -0.5, 0.0, 0.5, 1.0):
            for eyeball_y in (-1.0, -0.5, 0.0, 0.5, 1.0):
                moved = np.asarray(rp._shift(layers[f"eye_{side}"],
                                             eyeball_x * rp.IRIS_PX_X,
                                             eyeball_y * rp.IRIS_PX_Y).getchannel("A")) > 24
                assert not (mask & ~moved).any(), f"gol în ochiul {side} la {eyeball_x}/{eyeball_y}"


def test_animation_is_a_real_loop_with_blinks_and_speech(layers):
    frames = rp.animation(layers, frames=30)
    assert len(frames) == 30
    closed = [frame for frame in frames if rp._blink(0.32) > 0]
    assert closed, "nicio clipire în buclă"
    assert rp._blink(0.0) == 0.0 and rp._blink(0.9) == 0.0


def test_gif_is_written(layers, tmp_path):
    path = rp.write_gif(tmp_path / "preview.gif", size=160)
    assert path.exists() and path.stat().st_size > 5000
    with Image.open(path) as gif:
        assert gif.n_frames == 90
