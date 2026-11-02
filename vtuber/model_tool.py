"""Unelte pentru modele Live2D: inspectează un model și instalează-l în VTube Studio.

    python vtuber/model_tool.py inspect <folder sau .model3.json>
    python vtuber/model_tool.py install <folder> [--target DIR]
    python vtuber/model_tool.py install --github Mao [--target DIR]
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

GITHUB_TARBALL = "https://codeload.github.com/Live2D/CubismWebSamples/tar.gz/refs/heads/develop"


def find_model_file(path: Path) -> Path:
    if path.is_file():
        return path
    found = sorted(path.glob("*.model3.json"))
    if len(found) != 1:
        raise SystemExit(f"aștept exact un *.model3.json în {path}, am găsit {len(found)}")
    return found[0]


def read_model(path: Path) -> dict:
    model_file = find_model_file(path)
    refs = json.loads(model_file.read_text(encoding="utf-8")).get("FileReferences", {})
    folder, problems = model_file.parent, []

    for kind, names in (("moc3", [refs.get("Moc")]), ("textură", refs.get("Textures", [])), ("physics", [refs.get("Physics")])):
        for name in names:
            if name and not (folder / name).exists():
                problems.append(f"{kind} lipsă: {name}")

    expressions = []
    for expression in refs.get("Expressions", []):
        file = folder / expression["File"]
        params = {}
        if file.exists():
            params = {p["Id"]: p["Value"] for p in json.loads(file.read_text(encoding="utf-8")).get("Parameters", [])}
        else:
            problems.append(f"expresie lipsă: {expression['File']}")
        expressions.append({"name": expression["Name"], "file": expression["File"], "params": params})

    return {
        "name": model_file.name.removesuffix(".model3.json"),
        "folder": folder,
        "expressions": expressions,
        "motions": sum(len(group) for group in refs.get("Motions", {}).values()),
        "physics": bool(refs.get("Physics")),
        "problems": problems,
    }


def report(model: dict) -> None:
    print(f"model: {model['name']}")
    print(f"motoare: {model['motions']} motion-uri, physics={model['physics']}, expresii={len(model['expressions'])}")
    for expression in model["expressions"]:
        changed = ", ".join(f"{name}={value}" for name, value in expression["params"].items() if value) or "neutru"
        print(f"  {expression['file']:<32} {changed}")
    for problem in model["problems"]:
        print(f"! {problem}")


def vts_models_dir() -> Path:
    root = Path(os.environ.get("USERPROFILE") or Path.home()) / "AppData" / "LocalLow" / "DenchiSoft" / "VTubeStudio"
    for candidate in root.rglob("Live2DModels"):
        return candidate
    raise SystemExit(f"nu găsesc folderul Live2DModels în {root} — deschide-l din VTS și dă calea cu --target")


def download(name: str, workdir: Path) -> Path:
    """Ia doar folderul Samples/Resources/<name> din repo-ul oficial Live2D."""
    marker = f"/Samples/Resources/{name}/"
    root = workdir / name
    found = False
    with urllib.request.urlopen(GITHUB_TARBALL, timeout=300) as response:
        with tarfile.open(fileobj=response, mode="r|gz") as archive:
            for member in archive:
                if marker not in member.name:
                    continue
                found = True
                relative = member.name.split(marker, 1)[1]
                if not relative:
                    continue
                destination = root / relative
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(archive.extractfile(member).read())
    if not found:
        raise SystemExit(f"modelul {name} nu există în repo-ul Live2D (încearcă Haru, Hiyori, Mao, Mark, Natori, Ren, Rice, Wanko)")
    return root


def install(model: dict, target: Path) -> Path:
    if model["problems"]:
        raise SystemExit("model incomplet:\n  " + "\n  ".join(model["problems"]))
    destination = target / model["folder"].name
    if destination.exists():
        raise SystemExit(f"{destination} există deja")
    shutil.copytree(model["folder"], destination)
    return destination


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "inspect"
    target = Path(argv[argv.index("--target") + 1]) if "--target" in argv else None

    if command == "inspect":
        report(read_model(Path(argv[1])))
        return 0
    if command != "install":
        raise SystemExit(__doc__)

    if "--github" in argv:
        source = download(argv[argv.index("--github") + 1], Path(os.environ.get("TEMP", "/tmp")) / "live2d")
    else:
        source = Path(argv[1])
    model = read_model(source)
    report(model)
    destination = install(model, target or vts_models_dir())
    print(f"\ninstalat în: {destination}")
    print("pornește VTube Studio → rulează Auto-Setup pe model → python vtuber/face_reactions.py --list")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
