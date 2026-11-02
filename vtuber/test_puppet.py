from __future__ import annotations

import numpy as np
from PIL import Image, ImageChops

from puppet import ASSETS, Puppet, difference_mask, load_config


def make() -> Puppet:
    return Puppet(ASSETS, motion=load_config().get("motion", {}))


def changed_box(first: Image.Image, second: Image.Image) -> tuple[int, int, int, int] | None:
    return ImageChops.difference(first.convert("RGBA"), second.convert("RGBA")).getbbox(alpha_only=False)


def inside(inner, outer, margin: int = 2) -> bool:
    return (
        inner[0] >= outer[0] - margin
        and inner[1] >= outer[1] - margin
        and inner[2] <= outer[2] + margin
        and inner[3] <= outer[3] + margin
    )


def test_masks_land_on_eyes_and_mouth():
    puppet = make()
    width, height = puppet.base.size
    eyes = puppet.eye_mask.getbbox()
    mouth = puppet.mouth_mask.getbbox()
    # ochii: bandă în treimea de sus a cadrului
    assert 0.25 < eyes[1] / height < 0.42
    assert eyes[3] / height < 0.60
    # gura: sub ochi, mai îngustă, centrată
    assert mouth[1] > eyes[3] - 0.06 * height
    assert (mouth[2] - mouth[0]) < (eyes[2] - eyes[0])
    assert 0.34 < mouth[0] / width and mouth[2] / width < 0.68


def test_identity_composition_reproduces_original_state():
    """idle + gura din talking + pleoapele din blink trebuie să dea talking_blink."""
    puppet = make()
    frame = puppet.compose(1.0, 1.0)
    reference = Image.open(ASSETS / "talking_blink.png").convert("RGBA").resize(frame.size, Image.LANCZOS)
    difference = np.abs(np.asarray(frame).astype(int) - np.asarray(reference).astype(int))
    assert np.sqrt((difference**2).mean()) < 20
    assert 100 * (difference.max(axis=2) > 24).mean() < 3.0


def test_mouth_layer_touches_only_the_mouth():
    puppet = make()
    box = changed_box(puppet.compose(1.0, 0.0), puppet.base)
    assert box is not None
    assert inside(box, puppet.mouth_mask.getbbox())


def test_eye_layer_touches_only_the_eyes():
    puppet = make()
    box = changed_box(puppet.compose(0.0, 1.0), puppet.base)
    assert box is not None
    assert inside(box, puppet.eye_mask.getbbox())


def test_mouth_follows_voice_and_settles():
    puppet = make()
    for _ in range(12):
        puppet.set_inputs(0.5, {})
        puppet.frame(0.0)
    assert puppet._mouth > 0.9
    for _ in range(20):
        puppet.set_inputs(0.0, {})
        puppet.frame(1.0)
    assert puppet._mouth < 0.2


def test_jaw_blendshape_opens_mouth_without_microphone():
    puppet = make()
    for _ in range(6):
        puppet.set_inputs(0.0, {"jawOpen": 0.9})
    assert puppet._mouth > 0.6


def test_emotion_states_bypass_layers():
    puppet = make()
    assert puppet.set_asset("laugh.png", 0.0) is True
    assert puppet.set_asset("laugh.png", 0.1) is False
    frame = puppet.frame(1.0)
    assert frame.size == puppet.image("laugh.png").size
    assert changed_box(frame, puppet.image("laugh.png")) is None


def test_sway_keeps_the_canvas_and_moves_only_the_head():
    puppet = make()
    straight = puppet.compose(0.0, 0.0, (0.0, 0.0))
    tilted = puppet.compose(0.0, 0.0, (0.6, 0.0))
    assert tilted.size == straight.size
    box = changed_box(tilted, straight)
    assert box is not None and box[3] <= straight.height * 0.75


def test_difference_mask_is_empty_for_identical_images():
    image = Image.open(ASSETS / "idle.png").convert("RGBA")
    assert difference_mask(image, image).getbbox() is None


def test_frames_are_scaled_to_the_configured_height():
    """Regresie: stratul compus ieșea la 1024 și apărea decupat în fereastra de 720."""
    short = Puppet(ASSETS, output_height=480, motion={})
    assert short.frame(0.0).size == (480, 480)
    assert short.compose(1.0, 1.0).size == (480, 480)
    assert short.eye_mask.size == short.base.size
    tall = Puppet(ASSETS, output_height=900, motion={})
    assert tall.frame(0.0).height == 900
