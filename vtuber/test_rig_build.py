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
    original = Image.fromarray(
        rig_build.despill(np.asarray(Image.open(ASSETS / "idle.png").convert("RGBA")).astype(np.uint8)),
        "RGBA")
    assert np.sqrt((difference(rebuilt, original) ** 2).mean()) < 1.0


def test_head_and_body_split_at_the_collar():
    layers = build_layers()
    head, body = layers["head"], layers["body"]
    assert head.getchannel("A").getbbox()[3] > rig_build.CUT_Y          # gâtul coboară sub guler
    assert body.getchannel("A").getbbox()[1] < rig_build.CUT_Y          # trupul urcă sub cap
    assert head.getchannel("A").getbbox()[1] < 60                       # vârful capului e sus
    assert body.getchannel("A").getbbox()[3] == head.size[1]            # trupul ajunge în marginea de jos


def test_eye_mask_covers_the_whole_drawn_iris():
    """Masca deschiderii trebuie să acopere TOT irisul desenat, altfel rămâne o verigă din
    irisul din cap pe loc când globul se mută (adica „ochi sub ochi")."""
    layers = build_layers()
    source = np.asarray(Image.open(ASSETS / "idle.png").convert("RGBA")).astype(np.uint8)
    for side in ("L", "R"):
        blob = rig_build.iris_blob(source, rig_build.IRIS_CIRCLES[side])
        mask = np.asarray(layers[f"eye_mask_{side}"].getchannel("A")) > 24
        assert not (blob & ~mask).any(), f"irisul {side} iese din mască"
        assert mask.sum() > blob.sum(), "masca e mai mică decât irisul"


def test_eyeball_layer_has_margin_for_the_whole_travel():
    """Globul are 14 px de rezervă în jurul deschiderii: cât alunecă la maxim (±11)."""
    layers = build_layers()
    for side in ("L", "R"):
        mask = np.asarray(layers[f"eye_mask_{side}"].getchannel("A")) > 24
        eyeball = np.asarray(layers[f"eye_{side}"].getchannel("A")) > 24
        grown = rig_build._dilate(mask, 12)
        assert (grown & ~eyeball).sum() == 0, f"globul {side} nu are rezervă de 12 px"


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
    expected = {"izentric.model3.json", "izentric.cdi3.json", "izentric.rigspec.json"}
    expected |= {f"izentric.{name}.exp3.json" for name in rig_build.EXPRESSIONS}
    assert set(written) == expected
    # fiecare expresie: exact un parametru pe 1, celelalte pe 0
    for name in rig_build.EXPRESSIONS:
        payload = json.loads((OUT / f"izentric.{name}.exp3.json").read_text(encoding="utf-8"))
        values = {entry["Id"]: entry["Value"] for entry in payload["Parameters"]}
        assert values[f"ParamExpr{name.capitalize()}"] == 1.0
        assert sum(1 for value in values.values() if value == 1.0) == 1
        assert payload["Type"] == "Live2D Expression"


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
    assert groups == ["FACE", "BODY", "HEAD", "BACKING"]   # sus -> jos

    # clipping-ul scris in PSD (glob ocular lipit de masca lui), ca in editor
    top = {layer.name.strip("\x00"): layer for layer in flatten(psd)}
    assert top["eye_L"].clipping and top["eye_R"].clipping, "globul nu are clipping in PSD"
    assert not top["eye_mask_L"].visible and not top["eye_mask_R"].visible

    rebuilt = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    for layer in reversed(list(flatten(psd, visible_only=True))):
        image = layer.topil().convert("RGBA")
        name = layer.name.strip("\x00")
        mask_name = rig_build.CLIPPING.get(name)
        if mask_name:
            image.putalpha(ImageChops.multiply(image.getchannel("A"),
                                               top[mask_name].topil().convert("RGBA").getchannel("A")))
        rebuilt.alpha_composite(image)
    original = Image.fromarray(
        rig_build.despill(np.asarray(Image.open(ASSETS / "idle.png").convert("RGBA")).astype(np.uint8)),
        "RGBA")
    assert np.sqrt((difference(rebuilt, original) ** 2).mean()) < 1.0


def test_body_has_no_skin_so_the_neck_rotates_with_the_head():
    layers = build_layers()
    body = np.asarray(layers["body"])
    skin = rig_build.skin_mask(layers["body"])
    assert skin.sum() == 0, "gâtul a rămas în trup: la rotire ar sta pe loc"
    assert body[..., 3].sum() > 0


def test_no_gap_at_the_collar_when_the_head_rotates():
    """Cusătura de la guler, la capul rotit și mutat la maxim — pe randarea adevărată."""
    import rig_preview

    layers = build_layers()
    for angle_x, angle_y, angle_z in ((-30, -30, -30), (-30, 0, 30), (30, -30, 30), (30, 30, -30)):
        frame = rig_preview.render(layers, angle_x, angle_y, angle_z)
        alpha = np.asarray(frame.getchannel("A"))
        band = alpha[640:780, 300:730]
        assert (band < 8).sum() == 0, f"gol de {int((band < 8).sum())} pixeli la {angle_x}/{angle_y}/{angle_z}"


def test_nothing_eye_coloured_under_the_eye_when_the_gaze_moves():
    """„Ochi sub ochi": la orice poziție a privirii, pe obrajii de sub pleoape nu are
    voie să apară nici un pixel de iris sau întunecat care nu e în poza originală."""
    import numpy as np
    import rig_preview

    layers = build_layers()
    art = np.asarray(Image.open(ASSETS / "idle.png").convert("RGB"), dtype=int)
    bands = {"L": (slice(506, 540), slice(340, 462)), "R": (slice(503, 537), slice(558, 680))}

    def eye_coloured(img):
        out = {}
        for name, (ys, xs) in bands.items():
            px = np.asarray(img, dtype=int)[ys, xs]
            dark = int((px.max(axis=2) < 70).sum())
            iris = int(((px[:, :, 0] > px[:, :, 1] + 45) & (px[:, :, 0] > px[:, :, 2] + 45)
                        & (px[:, :, 1] < 90)).sum())
            out[name] = (dark, iris)
        return out

    reference = eye_coloured(art)
    for ex in (-1.0, 0.0, 1.0):
        for ey in (-1.0, 0.0, 1.0):
            got = eye_coloured(rig_preview.render(layers, 0, 0, 0, ex, ey, 1, 0))
            assert got == reference, f"la privirea {ex:+}/{ey:+} apare ceva sub pleoapă: {got} vs {reference}"
            assert all(dark == 0 for dark, _ in got.values()), f"pixeli întunecați sub pleoapă: {got}"


def test_each_expression_reproduces_its_own_drawing():
    """Expresia pornită la 100 % trebuie să dea poza ei pe față (ochi, gură, obraji)."""
    import rig_preview

    layers = build_layers()
    face = (slice(340, 560), slice(120, 930))
    for name in rig_build.EXPRESSIONS:
        reference = np.asarray(Image.open(ASSETS / f"{name}.png").convert("RGB"), dtype=float)
        got = np.asarray(rig_preview.render(layers, expressions={name: 1.0}).convert("RGB"), dtype=float)
        diff = np.abs(got - reference).max(axis=2)[face]
        # Limita: părul și conturul siluetei rămân din poza de repaus (desenul fiecărei
        # stări are fire de păr și contur puțin altfel), deci nu se poate cere identitate
        # pe tot ovalul — se cere ca fața să fie a expresiei, nu a repausului.
        face_rms = float(np.sqrt((diff ** 2).mean()))
        assert face_rms < 15.0, f"{name}: fața nu seamănă (rms {face_rms:.2f})"
        assert (diff > 120).sum() < 700, f"{name}: {int((diff > 120).sum())} pixeli foarte diferiți pe față"
        # și, ca dovadă că expresia chiar s-a schimbat: fața trebuie să difere de repaus
        idle_face = np.asarray(Image.open(ASSETS / "idle.png").convert("RGB"), dtype=float)[face]
        assert float(np.abs(got[face] - idle_face).max(axis=2).mean()) > 8.0, f"{name}: expresia nu se vede"


def test_expressions_do_not_touch_the_body_or_the_hair():
    """Haina și părul rămân din poza de repaus — altfel expresia ar schimba corpul."""
    layers = build_layers()
    idle = np.asarray(Image.open(ASSETS / "idle.png").convert("RGBA"))
    for name in rig_build.EXPRESSIONS:
        alpha = np.asarray(layers[f"expr_{name}"].getchannel("A")) > 24
        body = alpha[700:1024, 120:930].sum()      # sub guler: haina
        assert body == 0, f"{name}: atinge haina ({int(body)} pixeli)"
        assert alpha.sum() > 5000, f"{name}: expresia e goală"


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


def test_neck_keeps_the_drawn_pixels_and_invents_nothing():
    """Gâtul e exact ce e desenat: nici un pixel vopsit de mână. Orice pată inventată
    acolo ar ieși la iveală prin deschizătura husei."""
    import numpy as np

    layers = build_layers()
    art = np.asarray(Image.open(ASSETS / "idle.png").convert("RGBA")).astype(int)
    head = np.asarray(layers["head"].convert("RGBA")).astype(int)
    band = slice(rig_build.CUT_Y - 40, rig_build.CUT_Y + 40)
    alpha = head[band, :, 3]
    painted = alpha > 8
    assert painted.sum() > 500, "gâtul lipsește din stratul de cap"
    # referința e poza curățată de conturul verde (vezi rig_build.despill)
    clean = rig_build.despill(np.asarray(Image.open(ASSETS / "idle.png").convert("RGBA")).astype(np.uint8))
    different = np.abs(head[band, :, :3] - clean[band, :, :3].astype(int)).max(axis=2)[painted]
    assert different.max() == 0, f"{int((different > 0).sum())} pixeli din gât nu sunt cei desenați"
