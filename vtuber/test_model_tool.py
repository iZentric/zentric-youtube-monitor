"""Teste pentru model_tool.py (inspectare și instalare de modele Live2D)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import model_tool


def make_model(root: Path, textures: bool = True) -> Path:
    (root / "expressions").mkdir(parents=True)
    (root / "Akari.moc3").write_bytes(b"moc3")
    (root / "Akari.physics3.json").write_text("{}", encoding="utf-8")
    (root / "tex.png").write_bytes(b"png")
    (root / "expressions" / "exp_01.exp3.json").write_text(
        json.dumps({"Parameters": [{"Id": "ParamEyeLOpen", "Value": 1}, {"Id": "ParamMouthForm", "Value": 0}]}),
        encoding="utf-8",
    )
    model = {
        "Version": 3,
        "FileReferences": {
            "Moc": "Akari.moc3",
            "Textures": ["tex.png"] if textures else ["missing.png"],
            "Physics": "Akari.physics3.json",
            "Expressions": [{"Name": "exp_01", "File": "expressions/exp_01.exp3.json"}],
            "Motions": {"Idle": [{}, {}]},
        },
    }
    (root / "Akari.model3.json").write_text(json.dumps(model), encoding="utf-8")
    return root


def test_read_model_lists_expressions_and_params(tmp_path):
    model = model_tool.read_model(make_model(tmp_path / "Akari"))

    assert model["name"] == "Akari"
    assert model["motions"] == 2
    assert model["problems"] == []
    assert model["expressions"] == [
        {"name": "exp_01", "file": "expressions/exp_01.exp3.json", "params": {"ParamEyeLOpen": 1, "ParamMouthForm": 0}}
    ]


def test_read_model_reports_missing_files(tmp_path):
    model = model_tool.read_model(make_model(tmp_path / "Akari", textures=False))
    assert model["problems"] == ["textură lipsă: missing.png"]


def test_find_model_file_needs_exactly_one(tmp_path):
    folder = make_model(tmp_path / "Akari")
    (folder / "Altul.model3.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="aștept exact un"):
        model_tool.find_model_file(folder)


def test_install_copies_complete_model(tmp_path):
    model = model_tool.read_model(make_model(tmp_path / "Akari"))
    destination = model_tool.install(model, tmp_path / "Live2DModels")

    assert destination == tmp_path / "Live2DModels" / "Akari"
    assert (destination / "Akari.model3.json").exists()
    assert (destination / "expressions" / "exp_01.exp3.json").exists()


def test_install_refuses_incomplete_or_existing_model(tmp_path):
    broken = model_tool.read_model(make_model(tmp_path / "Broken", textures=False))
    with pytest.raises(SystemExit, match="model incomplet"):
        model_tool.install(broken, tmp_path / "Live2DModels")

    model = model_tool.read_model(make_model(tmp_path / "Akari"))
    model_tool.install(model, tmp_path / "Live2DModels")
    with pytest.raises(SystemExit, match="există deja"):
        model_tool.install(model, tmp_path / "Live2DModels")


def test_vts_models_dir_finds_folder_under_userprofile(tmp_path, monkeypatch):
    expected = tmp_path / "AppData" / "LocalLow" / "DenchiSoft" / "VTubeStudio" / "VTube Studio_Data" / "StreamingAssets" / "Live2DModels"
    expected.mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    assert model_tool.vts_models_dir() == expected


def test_vts_models_dir_explains_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    with pytest.raises(SystemExit, match="--target"):
        model_tool.vts_models_dir()
