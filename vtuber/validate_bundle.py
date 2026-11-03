"""Faza 5 — validare automată a pachetului: tot ce promite `model3.json` trebuie să existe.

Rulare: python vtuber/validate_bundle.py vtuber/rig
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from moc3_read import Moc3


def validate(folder: Path) -> list[str]:
    errors: list[str] = []

    def load(path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"JSON invalid: {path.name}: {exc}")
            return None

    model_path = folder / "izentric.model3.json"
    model = load(model_path)
    if model is None:
        return errors
    refs = model.get("FileReferences", {})

    if not refs.get("Moc"):
        errors.append("model3: lipsește FileReferences.Moc")
        return errors
    moc = Moc3(str(folder / refs["Moc"]))
    params = {p["id"] for p in moc.parameters()}
    meshes = {m["id"] for m in moc.art_meshes()}

    files = [refs["Moc"], refs.get("Physics"), refs.get("DisplayInfo"), *(refs.get("Textures") or [])]
    files += [e["File"] for e in refs.get("Expressions", [])]
    for name in files:
        if name and not (folder / name).exists():
            errors.append(f"model3: fișierul lipsește: {name}")

    textures = refs.get("Textures") or []
    used = {m["texture"] for m in moc.art_meshes()}
    if used - set(range(len(textures))):
        errors.append(f"model3: moc3 cere textura {sorted(used - set(range(len(textures))))}, "
                      f"dar model3 declară {len(textures)}")

    for exp in refs.get("Expressions", []):
        data = load(folder / exp["File"])
        if data is None:
            continue
        for entry in data.get("Parameters", []):
            if entry.get("Id") not in params:
                errors.append(f"{exp['File']}: parametrul {entry['Id']} nu există în moc3")

    for group in model.get("Groups", []):
        for pid in group.get("Ids", []):
            if pid not in params:
                errors.append(f"model3 grup {group.get('Name')}: parametrul {pid} nu există")

    for area in model.get("HitAreas", []):
        if area.get("Id") not in meshes:
            errors.append(f"model3: HitArea {area.get('Id')} nu are art mesh cu acest nume")

    physics_name = refs.get("Physics")
    if physics_name:
        physics = load(folder / physics_name)
        if physics:
            meta = physics.get("Meta", {})
            settings = physics.get("PhysicsSettings", [])
            counts = {
                "PhysicsSettingCount": len(settings),
                "TotalInputCount": sum(len(s.get("Input", [])) for s in settings),
                "TotalOutputCount": sum(len(s.get("Output", [])) for s in settings),
                "VertexCount": sum(len(s.get("Vertices", [])) for s in settings),
            }
            for key, value in counts.items():
                if meta.get(key) != value:
                    errors.append(f"physics3: Meta.{key}={meta.get(key)} dar real {value}")
            for setting in settings:
                for item in setting.get("Input", []):
                    if item["Source"]["Id"] not in params:
                        errors.append(f"physics3: intrare {item['Source']['Id']} inexistentă")
                for item in setting.get("Output", []):
                    if item["Destination"]["Id"] not in params:
                        errors.append(f"physics3: ieșire {item['Destination']['Id']} inexistentă")

    for forbidden in ("ellot", "VT_Dino", "Dinosaur", "dino"):
        if forbidden.lower() in model_path.read_text(encoding="utf-8").lower():
            errors.append(f"model3: încă referă modelul {forbidden}")

    return errors


def main(argv: list[str]) -> int:
    folder = Path(argv[0] if argv else "vtuber/rig")
    errors = validate(folder)
    if errors:
        print(f"{len(errors)} probleme:")
        for e in errors:
            print("  -", e)
        return 1
    print("pachet valid: toate referințele există, parametrii și hit areas se potrivesc")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
