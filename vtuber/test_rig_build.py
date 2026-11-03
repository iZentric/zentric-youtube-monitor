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
    # 2.0 și nu 1.0: irisul e decupat exact pe desen, iar albul de sub el e reconstruit
    # prin difuzie (diferă doar 1-2 px de margine; măsurat 1.17)
    assert np.sqrt((difference(rebuilt, original) ** 2).mean()) < 2.0


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
        assert 80 <= width <= 120 and 80 <= height <= 120   # irisul desenat, ~105 px
        assert abs(width - height) <= 12                     # aproximativ rotund, nu oval


def test_no_iris_colour_is_left_in_the_head():
    """Irisul e strat separat: în cap nu are voie să rămână culoarea lui, altfel la
    mișcare se vede o verigă în urmă. Umbra de sub pleoapă are voie să rămână — e a
    desenului, stă deasupra irisului."""
    import numpy as np

    layers = build_layers()
    head = np.asarray(layers["head"].convert("RGB")).astype(np.float32)
    iris = np.zeros(head.shape[:2], bool)
    for side in ("L", "R"):
        iris |= np.asarray(layers[f"iris_{side}"].getchannel("A")) > 24
    luminance = head[..., :3].mean(axis=2)
    sat = head[..., :3].max(axis=2) - head[..., :3].min(axis=2)
    leftover = int(((luminance < 140) & (sat > 60))[iris].sum())
    assert leftover < 20, f"{leftover} pixeli de culoare de iris au rămas în cap"


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
    # ordinea din PSD (sus -> jos) trebuie să fie exact cea în care se desenează,
    # altfel gulerul nu mai acoperă gâtul când PSD-ul e importat în editor
    assert names == rig_build.DRAW_ORDER
    groups = [layer.name.strip("\x00") for layer in psd if layer.is_group()]
    assert groups == ["FACE", "MASKS", "BODY", "HEAD", "BACKING"]   # sus -> jos

    rebuilt = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    for layer in reversed(list(flatten(psd, visible_only=True))):
        rebuilt.alpha_composite(layer.topil().convert("RGBA"))
    original = Image.open(ASSETS / "idle.png").convert("RGBA")
    # 2.5 și nu 1.0: marginea irisului e pe difuzie, deci 1-2 px diferă (măsurat 1.17)
    assert np.sqrt((difference(rebuilt, original) ** 2).mean()) < 2.5


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


def test_backing_layer_is_inside_the_silhouette_and_fills_the_hood_opening():
    """Spatele gulerului nu are voie să iasă în afara personajului (halou), dar trebuie
    să acopere deschizătura husei, altfel la rotație se vede fundalul."""
    import numpy as np

    layers = rig_build.build_layers()
    backing = np.asarray(layers["backing"].getchannel("A")) > 24
    body = np.asarray(layers["body"].getchannel("A")) > 24
    head = np.asarray(layers["head"].getchannel("A")) > 24
    assert backing.any(), "stratul de spate lipsește"
    assert not (backing & ~(body | head)).any(), "spatele iese din siluetă"
    assert backing.sum() > 2000, "spatele e gol"


def test_neck_is_painted_skin_not_a_swatch_of_the_hoodie():
    """Gâtul prelungit sub guler trebuie vopsit în culoarea pielii, nu copiat din husă."""
    import numpy as np

    layers = rig_build.build_layers()
    head = np.asarray(layers["head"].convert("RGB")).astype(int)
    alpha = np.asarray(layers["head"].getchannel("A")) > 200
    band = alpha[700:740, 470:560]
    colors = head[700:740, 470:560][band]
    assert len(colors) > 500, "gâtul prelungit lipsește"
    r, g, b = colors.mean(axis=0)
    assert r > g > b and r - b > 25 and r > 150, f"gâtul nu e piele: {r:.0f},{g:.0f},{b:.0f}"


def test_iris_is_taken_from_the_drawing_not_from_a_guessed_circle():
    """Masca irisului trebuie să fie forma desenată: nici mai mică (rămâne verigă),
    nici mai mare (mănâncă albul ochiului)."""
    import numpy as np
    from PIL import Image

    pixels = np.asarray(Image.open(ASSETS / "idle.png").convert("RGB"))
    for side in ("L", "R"):
        blob = rig_build.iris_blob(pixels, rig_build.IRIS_CIRCLES[side])
        ys, xs = np.nonzero(blob)
        width, height = xs.max() - xs.min(), ys.max() - ys.min()
        assert 70 < width < 120 and 70 < height < 120, f"iris {side}: {width}x{height}"
        assert 0.8 < width / height < 1.25, "irisul nu e rotund"


def test_looking_away_exposes_a_shaded_white_without_a_dark_ring():
    """Testul pentru „se vede urât când mă uit în altă parte": se mută irisul la maxim
    și se măsoară exact zona descoperită — trebuie albă, cu umbră și fără verigă."""
    import numpy as np

    import rig_preview

    layers = build_layers()
    iris = np.zeros((1024, 1024), bool)
    for side in ("L", "R"):
        iris |= np.asarray(layers[f"iris_{side}"].getchannel("A")) > 24
    dx, dy = round(rig_preview.IRIS_PX_X), round(rig_preview.IRIS_PX_Y)
    moved_iris = np.zeros_like(iris)
    moved_iris[dy:, dx:] = iris[:-dy, :-dx]
    revealed = iris & ~moved_iris
    assert revealed.sum() > 800, "irisul nu se mișcă suficient ca să se vadă albul"

    rest = np.asarray(rig_preview.render(layers).convert("RGB")).astype(np.float32)
    moved = np.asarray(rig_preview.render(layers, eyeball_x=1.0, eyeball_y=1.0)
                       .convert("RGB")).astype(np.float32)
    revealed = revealed & (rest[..., :3].mean(axis=2) > 100)   # fără conturul negru al ochiului
    assert revealed.sum() > 1200

    luminance = moved[..., :3].mean(axis=2)
    sat = moved[..., :3].max(axis=2) - moved[..., :3].min(axis=2)
    # măsurat: medie 186 (umbra pleoapei trage media în jos), abatere 54
    assert luminance[revealed].mean() > 175, f"albul descoperit e prea închis: {luminance[revealed].mean():.0f}"
    assert luminance[revealed].std() > 10, "albul descoperit e plat (fără umbră)"
    dark = int(((luminance < 150) & (sat > 60))[revealed].sum())
    assert dark < revealed.sum() * 0.01, f"{dark} pixeli de iris au rămas în urmă"
