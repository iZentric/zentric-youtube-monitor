from __future__ import annotations

import json
from pathlib import Path

import pytest

import check_model
import rig_build
from check_model import check_bundle, moc3_version

REAL_MODEL = Path("/tmp/vtsmodels/Mao")


def make_bundle(folder: Path, moc_version: int = 5, texture=(1024, 1024), write_texture=True) -> Path:
    """Model minim valid: model3 + cdi3 + moc3 fals cu antet corect + o textură."""
    from PIL import Image

    folder.mkdir(parents=True, exist_ok=True)
    (folder / "izentric.model3.json").write_text(
        json.dumps(rig_build.model3("texture_00.png"), ensure_ascii=False), encoding="utf-8"
    )
    (folder / "izentric.cdi3.json").write_text(json.dumps(rig_build.cdi3(), ensure_ascii=False), encoding="utf-8")
    (folder / "izentric.moc3").write_bytes(b"MOC3" + bytes([moc_version]) + bytes(60))
    if write_texture:
        Image.new("RGBA", texture, (0, 0, 0, 0)).save(folder / "texture_00.png")
    return folder


def test_moc3_version_is_read_from_the_header(tmp_path):
    path = tmp_path / "fake.moc3"
    path.write_bytes(b"MOC3\x05" + bytes(8))
    assert moc3_version(path) == 5
    path.write_bytes(b"XXXX\x05" + bytes(8))
    assert moc3_version(path) is None


@pytest.mark.skipif(not REAL_MODEL.exists(), reason="modelul Live2D real nu e descărcat")
def test_real_live2d_model_passes():
    errors, _warnings = check_bundle(REAL_MODEL)
    assert errors == []
    assert moc3_version(REAL_MODEL / "Mao.moc3") == 5


def test_generated_bundle_passes(tmp_path):
    errors, warnings = check_bundle(make_bundle(tmp_path / "ok"))
    assert errors == []


def test_missing_moc3_is_an_error(tmp_path):
    folder = make_bundle(tmp_path / "nomoc")
    (folder / "izentric.moc3").unlink()
    errors, _ = check_bundle(folder)
    assert any("moc3" in error for error in errors)


def test_too_new_moc3_is_an_error(tmp_path):
    folder = make_bundle(tmp_path / "nou", moc_version=6)
    errors, _ = check_bundle(folder)
    assert any("VTube Studio" in error for error in errors)


def test_missing_texture_is_an_error(tmp_path):
    folder = make_bundle(tmp_path / "fara-textura", write_texture=False)
    errors, _ = check_bundle(folder)
    assert any("textură lipsă" in error for error in errors)


def test_oversized_texture_is_an_error(tmp_path):
    folder = make_bundle(tmp_path / "mare", texture=(5000, 5000))
    errors, _ = check_bundle(folder)
    assert any("peste limita" in error for error in errors)


def test_missing_display_info_is_an_error(tmp_path):
    folder = make_bundle(tmp_path / "fara-cdi")
    (folder / "izentric.cdi3.json").unlink()
    errors, _ = check_bundle(folder)
    assert any("DisplayInfo" in error for error in errors)


def test_empty_folder_is_reported(tmp_path):
    errors, _ = check_bundle(tmp_path / "gol")
    assert errors and "model3.json" in errors[0]


def test_model3_matches_the_official_live2d_structure():
    """Scheletul e cel din modelul oficial Live2D (Mao.model3.json)."""
    model = rig_build.model3()
    assert set(model) == {"Version", "FileReferences", "Groups", "HitAreas"}
    assert set(model["FileReferences"]) <= {"Moc", "Textures", "Physics", "Pose", "DisplayInfo", "Expressions", "Motions"}
    assert model["Version"] == 3
    assert [group["Name"] for group in model["Groups"]] == ["LipSync", "EyeBlink"]
    assert all(target["Target"] == "Parameter" for target in model["Groups"])
    assert {area["Name"] for area in model["HitAreas"]} == {"Head", "Body"}


def test_cdi3_uses_the_standard_parameter_ids_and_groups():
    display = rig_build.cdi3()
    ids = {entry["Id"] for entry in display["Parameters"]}
    assert {
        "ParamAngleX",
        "ParamAngleY",
        "ParamAngleZ",
        "ParamEyeLOpen",
        "ParamEyeROpen",
        "ParamEyeBallX",
        "ParamEyeBallY",
        "ParamMouthOpenY",
        "ParamMouthForm",
        "ParamBodyAngleX",
        "ParamBreath",
    } <= ids
    groups = {entry["Id"] for entry in display["ParameterGroups"]}
    assert all(entry["GroupId"] in groups for entry in display["Parameters"])


def test_rig_spec_only_mentions_existing_layers_and_parameters():
    spec = rig_build.rig_spec()
    layers = {"head", "body", "iris_L", "iris_R", "eyes_closed", "mouth_open", "eye_mask_L", "eye_mask_R"}
    parameters = {entry["Id"] for entry in rig_build.cdi3()["Parameters"]}
    deformers = {entry["id"] for entry in spec["deformers"]}

    assert set(spec["draw_order"]) == layers
    assert set(spec["clipping"]) <= layers
    assert set(spec["clipping"].values()) <= layers

    for param, keyforms in spec["keyforms"].items():
        assert param in parameters
        for keyform in keyforms:
            if "layer" in keyform:
                assert keyform["layer"] in layers
            if "layers" in keyform:
                assert set(keyform["layers"]) <= layers
            if "deformer" in keyform:
                assert keyform["deformer"] in deformers

    for deformer in spec["deformers"]:
        for param in deformer.get("parameters", []):
            assert param in parameters
        for layer in deformer.get("layers", []):
            assert layer in layers
