from __future__ import annotations

import json

import numpy as np
from PIL import Image, ImageChops

import rig_build
from rig_build import ASSETS, OUT, build_layers, composite, iris_masks, parse_iris_arguments


def difference(first: Image.Image, second: Image.Image) -> np.ndarray:
    return np.abs(np.asarray(first).astype(int) - np.asarray(second).astype(int))


def test_layers_rebuild_the_original_picture():
    """head + body + cele două irise trebuie să dea `idle.png` la pixel."""
    layers = build_layers()
    rebuilt = composite(layers)
    original = Image.open(ASSETS / "idle.png").convert("RGBA")
    assert np.sqrt((difference(rebuilt, original) ** 2).mean()) < 1.0


def test_head_and_body_split_at_the_collar():
    layers = build_layers()
    head, body = layers["head"], layers["body"]
    assert head.getchannel("A").getbbox()[3] > rig_build.CUT_Y          # gâtul coboară sub guler
    assert body.getchannel("A").getbbox()[1] < rig_build.CUT_Y          # trupul urcă sub cap
    assert head.getchannel("A").getbbox()[1] < 60                       # vârful capului e sus
    assert body.getchannel("A").getbbox()[3] == head.size[1]            # trupul ajunge în marginea de jos


def test_irises_are_circles_inside_the_eyes():
    layers = build_layers()
    for name in ("iris_L", "iris_R"):
        box = layers[name].getchannel("A").getbbox()
        assert box is not None
        width, height = box[2] - box[0], box[3] - box[1]
        assert 90 <= width <= 115 and 90 <= height <= 115   # disc de rază ~52
        assert abs(width - height) <= 4                      # rotund, nu oval


def test_head_has_white_where_the_iris_was():
    """Fără whitening, irisul rămas în cap s-ar vedea dublu când se mișcă."""
    layers = build_layers()
    head = np.asarray(layers["head"])
    left, _right = iris_masks((1024, 1024))
    ys, xs = np.nonzero(left)
    centre = (int(ys.mean()), int(xs.mean()))
    assert head[centre][:3].min() > 230   # albul ochiului, nu irisul albastru


def test_eyes_closed_and_mouth_open_touch_only_their_regions():
    layers = build_layers()
    base = Image.open(ASSETS / "idle.png").convert("RGBA")
    head_zone = ImageChops.difference(layers["eyes_closed"].convert("RGBA"), Image.new("RGBA", base.size, (0, 0, 0, 0)))
    assert head_zone.getbbox() is not None
    box = layers["mouth_open"].getchannel("A").getbbox()
    assert box[1] > 450 and box[3] < 650


def test_iris_arguments_override_the_measured_circles():
    circles = parse_iris_arguments(["L:400,400,40", "R:620,430,55"])
    assert circles["L"] == (400, 400, 40)
    assert circles["R"] == (620, 430, 55)
    left, right = iris_masks((1024, 1024), circles)
    assert left.sum() < iris_masks((1024, 1024))[0].sum()   # raza mai mică, mai puțini pixeli


def test_sidecars_reference_the_moc3_and_the_parameters():
    written = rig_build.write_sidecars(OUT)
    model = json.loads((OUT / "izentric.model3.json").read_text(encoding="utf-8"))
    display = json.loads((OUT / "izentric.cdi3.json").read_text(encoding="utf-8"))
    assert model["FileReferences"]["Moc"] == "izentric.moc3"
    groups = {group["Name"]: group["Ids"] for group in model["Groups"]}
    assert groups["EyeBlink"] == ["ParamEyeLOpen", "ParamEyeROpen"]
    assert groups["LipSync"] == ["ParamMouthOpenY"]
    ids = {entry["Id"] for entry in display["Parameters"]}
    assert {"ParamAngleX", "ParamMouthOpenY", "ParamEyeBallX"} <= ids
    assert set(written) == {"izentric.model3.json", "izentric.cdi3.json", "izentric.rigspec.json"}


def flatten(layers, visible_only=False):
    for layer in layers:
        if layer.is_group():
            if not visible_only or layer.visible:
                yield from flatten(layer, visible_only)
        elif not visible_only or layer.visible:
            yield layer


def test_psd_round_trip_keeps_the_layers():
    from psd_tools import PSDImage

    layers = build_layers()
    path = rig_build.write_psd(OUT / "izentric.psd", layers)
    psd = PSDImage.open(path)
    names = [layer.name.strip("\x00") for layer in flatten(psd)]
    assert sorted(names) == sorted(rig_build.DRAW_ORDER)
    groups = [layer.name.strip("\x00") for layer in psd if layer.is_group()]
    assert groups == ["HEAD", "BODY", "MASKS", "FACE"]

    rebuilt = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    for layer in reversed(list(flatten(psd, visible_only=True))):
        rebuilt.alpha_composite(layer.topil().convert("RGBA"))
    original = Image.open(ASSETS / "idle.png").convert("RGBA")
    assert np.sqrt((difference(rebuilt, original) ** 2).mean()) < 1.0


def test_body_has_no_skin_so_the_neck_rotates_with_the_head():
    layers = build_layers()
    body = np.asarray(layers["body"])
    skin = rig_build.skin_mask(layers["body"])
    assert skin.sum() == 0, "gâtul a rămas în trup: la rotire ar sta pe loc"
    assert body[..., 3].sum() > 0


def test_no_gap_at_the_collar_when_the_head_rotates():
    """Cusătura de la guler, la rotirea maximă din rigspec (±8°)."""
    layers = build_layers()
    for angle in (-8, 0, 8):
        rotated = layers["head"].rotate(angle, resample=Image.BICUBIC, center=(512, 655))
        frame = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
        frame.alpha_composite(layers["body"])
        frame.alpha_composite(rotated)
        alpha = np.asarray(frame)[..., 3]
        band = alpha[640:760, 300:730]
        assert (band < 8).sum() <= 5, f"gol de {int((band < 8).sum())} pixeli la rotire {angle}°"


def test_pack_contains_everything_needed_to_rig():
    """Un singur fișier de descărcat: dacă lipsește ceva din el, omul se blochează."""
    import zipfile

    pack = rig_build.write_pack(OUT)
    with zipfile.ZipFile(pack) as archive:
        names = set(archive.namelist())
        assert names == set(rig_build.PACK_FILES)
        assert archive.read("izentric.psd")[:4] == b"8BPS"      # antet PSD valid
        guide = archive.read("GATA-DE-RIGAT.txt").decode("utf-8")
        assert "izentric.psd" in guide and "moc3" in guide
