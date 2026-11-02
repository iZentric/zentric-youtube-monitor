"""Verifică un model Live2D înainte să-l încarci în VTube Studio.

Ayatsuri2D (sau Cubism) îți exportă un folder cu `*.model3.json`, `*.moc3`, texturi și
fișierele auxiliare. Ăsta e pre-flight-ul care spune, în 2 secunde, ce nu se va încărca:

    python vtuber/check_model.py "C:\\...\\Live2DModels\\izentric"
    python vtuber/check_model.py --all "C:\\...\\Live2DModels"

Verifică exact lucrurile care fac VTS să refuze un model: fișierul moc3 lipsă sau prea nou,
texturile care nu există ori sunt prea mari, parametrii din `Groups` care nu există în
`cdi3.json`, referințele către fizică/expresii/motion-uri care duc în gol.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

MOC3_MAGIC = b"MOC3"
VTS_MAX_MOC3_VERSION = 5      # VTS nu deschide încă moc3 5.3
MAX_TEXTURE = 4096


def moc3_version(path: Path) -> int | None:
    """Versiunea din antetul moc3 (`MOC3` + un octet de versiune). None dacă nu e moc3."""
    with open(path, "rb") as handle:
        header = handle.read(16)
    if header[:4] != MOC3_MAGIC:
        return None
    if len(header) < 5:
        return None
    version = header[4]
    return version if 1 <= version <= 9 else None


def texture_size(path: Path) -> tuple[int, int] | None:
    from PIL import Image

    try:
        with Image.open(path) as image:
            return image.size
    except Exception:
        return None


def compare_versions(model: dict) -> int:
    """`Version` trebuie să fie 3 (singura pe care o încarcă VTS)."""
    return int(model.get("Version", 0))


def check_bundle(folder: Path) -> tuple[list[str], list[str]]:
    """Întoarce (erori, avertismente). Lista de erori goală = se încarcă."""
    folder = Path(folder)
    errors: list[str] = []
    warnings: list[str] = []

    models = sorted(folder.glob("*.model3.json"))
    if not models:
        return [f"nu găsesc niciun *.model3.json în {folder}"], warnings
    if len(models) > 1:
        warnings.append(f"mai multe modele în folder ({len(models)}): {[m.name for m in models]}")
    model_path = models[0]
    try:
        model = json.loads(model_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{model_path.name} nu e JSON valid: {exc}"], warnings

    if compare_versions(model) != 3:
        errors.append(f"model3 Version = {model.get('Version')}, trebuie 3")

    references = model.get("FileReferences", {})
    identifier = model.get("FileReferences", {}).get("Moc")
    if not identifier:
        errors.append("FileReferences.Moc lipsește")
    else:
        moc = folder / identifier
        if not moc.exists():
            errors.append(f"moc3 lipsă: {identifier}")
        else:
            version = moc3_version(moc)
            if version is None:
                errors.append(f"{identifier} nu începe cu MOC3 (nu e un moc3 valid)")
            elif version > VTS_MAX_MOC3_VERSION:
                errors.append(f"{identifier} e moc3 v{version}; VTube Studio deschide până la v{VTS_MAX_MOC3_VERSION}")

    textures = references.get("Textures", [])
    if not textures:
        errors.append("FileReferences.Textures e gol")
    for texture in textures:
        path = folder / texture
        if not path.exists():
            errors.append(f"textură lipsă: {texture}")
            continue
        size = texture_size(path)
        if size is None:
            errors.append(f"textura {texture} nu se poate citi ca imagine")
        elif max(size) > MAX_TEXTURE:
            errors.append(f"textura {texture} are {size[0]}×{size[1]}, peste limita {MAX_TEXTURE}")

    display_name = references.get("DisplayInfo")
    parameter_ids: set[str] = set()
    if display_name:
        display = folder / display_name
        if not display.exists():
            errors.append(f"DisplayInfo lipsă: {display_name}")
        else:
            try:
                info = json.loads(display.read_text(encoding="utf-8"))
                parameter_ids = {entry["Id"] for entry in info.get("Parameters", [])}
            except (json.JSONDecodeError, KeyError) as exc:
                errors.append(f"{display_name} invalid: {exc}")

    for group in model.get("Groups", []):
        for param in group.get("Ids", []):
            if parameter_ids and param not in parameter_ids:
                warnings.append(f"grupul {group.get('Name')} cere {param}, care nu e în {display_name}")

    for key in ("Physics", "Pose"):
        name = references.get(key)
        if name and not (folder / name).exists():
            errors.append(f"{key} lipsă: {name}")

    for expression in references.get("Expressions", []):
        name = expression.get("File")
        if name and not (folder / name).exists():
            errors.append(f"expresie lipsă: {name}")

    for group_name, motions in references.get("Motions", {}).items():
        for motion in motions:
            name = motion.get("File")
            if name and not (folder / name).exists():
                errors.append(f"motion lipsă ({group_name}): {name}")

    if not any(group.get("Name") == "EyeBlink" for group in model.get("Groups", [])):
        warnings.append("nu există grupul EyeBlink: clipitul automat nu va merge")
    if not any(group.get("Name") == "LipSync" for group in model.get("Groups", [])):
        warnings.append("nu există grupul LipSync: sincronizarea buzelor nu va merge")

    return errors, warnings


def report(folder: Path) -> int:
    errors, warnings = check_bundle(folder)
    name = Path(folder).name
    for warning in warnings:
        print(f"  ! {name}: {warning}")
    for error in errors:
        print(f"  ✗ {name}: {error}")
    if not errors:
        print(f"  ✓ {name}: modelul se poate încărca")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--all":
        roots = [Path(arg) for arg in argv[1:]]
    else:
        roots = [Path(arg) for arg in argv]
    status = 0
    for root in roots:
        if (root / "*.model3.json").parent == root and list(root.glob("*.model3.json")):
            status |= report(root)
        elif root.is_dir():
            for child in sorted(root.iterdir()):
                if child.is_dir() and list(child.glob("*.model3.json")):
                    status |= report(child)
        else:
            print(f"  ✗ {root}: nu e folder cu *.model3.json")
            status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
