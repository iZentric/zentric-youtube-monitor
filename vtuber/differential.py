"""Test diferențial: 281 de cadre, fiecare măsurat, nu privit.

Ideea vine din ce se strică de obicei la un model 2D: nu pozele de repaus, ci极端-urile —
capul rotit maxim, mutat maxim, irisul la marginea ochiului. Aici fiecare combinație este
desenată și măsurată, iar rezultatul e o cifră, nu o părere.

Măsurători pe fiecare cadru:
  gauri        - pixeli transparenți închiși în interiorul siluetei (se vede dedesubt)
  guler        - aceleași gauri, dar în banda gulerului (y 600-780) — trebuie 0
  iou          - cât se suprapune silueta cu cea de repaus (capul are voie să se miște)
  ochi_gol     - pixeli nemascați în deschiderea ochiului la orice privire — trebuie 0
  miscare      - câți pixeli chiar se schimbă (un parametru care nu face nimic e un bug)

Rulare:  python vtuber/differential.py [--cases 281] [--save-worst DIR]
Cod de ieșire: 0 dacă toate cazurile trec, 1 altfel.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import rig_preview as rp  # noqa: E402

CASES = 281
COLLAR = (600, 780, 250, 780)      # y0, y1, x0, x1


def closed_holes(alpha: np.ndarray, box: tuple[int, int, int, int] | None = None) -> int:
    """Pixeli goi închiși de siluetă; dacă `box`, doar în acea fereastră.

    Umplerea pornește din toate cele patru colțuri (implementare C din Pillow), deci
    orice buzunar care nu se poate atinge de margine rămâne gol — adică „se vede dedesubt".
    """
    from PIL import ImageDraw

    y0, y1, x0, x1 = box or (0, alpha.shape[0], 0, alpha.shape[1])
    window = (alpha[y0:y1, x0:x1] > 24).astype(np.uint8) * 255
    height, width = window.shape
    filled = Image.fromarray(window, "L").copy()   # altfel floodfill nu are voie să scrie
    for corner in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        if filled.getpixel(corner) == 0:
            ImageDraw.floodfill(filled, corner, 128)
    return int((np.asarray(filled) == 0).sum())


def cases(count: int = CASES) -> list[dict]:
    """Combinații deterministe: colțurile întâi, apoi grilă, apoi umplutură împrăștiată."""
    out: list[dict] = []
    edges = (-30, 0, 30)
    for angle_x in edges:                      # 27 de colțuri/fețe ale cubului de parametri
        for angle_y in edges:
            for angle_z in edges:
                out.append({"angle_x": angle_x, "angle_y": angle_y, "angle_z": angle_z,
                            "eye_open": 1.0, "mouth": 0.0, "eyeball_x": 0.0, "eyeball_y": 0.0})
    for eye_open in (0.0, 0.5, 1.0):           # 81 cu pleoapele și gura
        for mouth in (0.0, 0.5, 1.0):
            for angle_z in (-30.0, 0.0, 30.0):
                for angle_x in (-30.0, 0.0, 30.0):
                    for angle_y in (-30.0, 0.0, 30.0):
                        out.append({"angle_x": angle_x, "angle_y": angle_y, "angle_z": angle_z,
                                    "eye_open": eye_open, "mouth": mouth,
                                    "eyeball_x": 0.0, "eyeball_y": 0.0})
    rng = random.Random(20261103)              # restul: umplutură reproductibilă până la `count`
    while len(out) < count:
        out.append({"angle_x": rng.uniform(-30, 30), "angle_y": rng.uniform(-30, 30),
                    "angle_z": rng.uniform(-30, 30), "eye_open": rng.random(),
                    "mouth": rng.random(), "eyeball_x": rng.uniform(-1, 1),
                    "eyeball_y": rng.uniform(-1, 1)})
    return out[:count]


def measure(layers: dict[str, Image.Image], case: dict, baseline: np.ndarray) -> dict:
    frame = rp.render(layers, case["angle_x"], case["angle_y"], case["angle_z"],
                      eyeball_x=case["eyeball_x"], eyeball_y=case["eyeball_y"],
                      eye_open=case["eye_open"], mouth=case["mouth"])
    alpha = np.asarray(frame.getchannel("A"))
    solid = alpha > 24
    union = solid | baseline
    iou = float((solid & baseline).sum() / max(1, union.sum()))
    # globul ocular acoperă masca complet? (dacă nu, rămâne o fereastră goală în ochi)
    eye_gap = 0
    for side in ("L", "R"):
        mask = np.asarray(layers[f"eye_mask_{side}"].getchannel("A")) > 24
        eyeball = np.asarray(rp._shift(layers[f"eye_{side}"],
                                       case["eyeball_x"] * rp.IRIS_PX_X,
                                       case["eyeball_y"] * rp.IRIS_PX_Y).getchannel("A")) > 24
        eye_gap += int((mask & ~eyeball).sum())

    area = int(solid.sum())
    return {"frame": frame, "holes": closed_holes(alpha), "area": area,
            "collar": closed_holes(alpha, COLLAR), "iou": iou, "eye_gap": eye_gap}


def run(count: int = CASES, save_worst: Path | None = None, verbose: bool = True) -> dict:
    layers = rp.load_layers()
    rest = rp.render(layers)
    baseline_alpha = np.asarray(rest.getchannel("A"))
    rest_solid = baseline_alpha > 24
    rest_rgb = np.asarray(rest.convert("RGB"), dtype=np.int16)

    results = []
    for index, case in enumerate(cases(count)):
        row = measure(layers, case, rest_solid)
        rgb = np.asarray(row["frame"].convert("RGB"), dtype=np.int16)
        row["moved"] = int((np.abs(rgb - rest_rgb).max(axis=2) > 12).sum())
        row["case"] = case
        row["index"] = index
        results.append(row)

    baseline_holes = closed_holes(baseline_alpha)
    baseline_area = int(rest_solid.sum())
    limits = {
        "collar": 0,
        "eye_gap": 0,
        "holes": baseline_holes + 10,
        "area_change": 0.02,      # forma se schimbă la rotire, dar masa personajului nu
    }
    failures = []
    for row in results:
        problems = []
        if row["collar"] > limits["collar"]:
            problems.append(f"guler {row['collar']}")
        if row["eye_gap"] > limits["eye_gap"]:
            problems.append(f"ochi gol {row['eye_gap']}")
        if row["holes"] > limits["holes"]:
            problems.append(f"gauri {row['holes']} > {limits['holes']}")
        change = abs(row["area"] - baseline_area) / baseline_area
        row["area_change"] = change
        if change > limits["area_change"]:
            problems.append(f"arie {change * 100:.2f}%")
        if problems:
            failures.append((row, problems))

    if save_worst and failures:
        save_worst.mkdir(parents=True, exist_ok=True)
        for row, _ in failures[:10]:
            row["frame"].save(save_worst / f"caz-{row['index']:03d}.png")

    summary = {
        "cases": len(results),
        "failed": len(failures),
        "baseline_holes": baseline_holes,
        "worst_collar": max(row["collar"] for row in results),
        "worst_holes": max(row["holes"] for row in results),
        "min_iou": min(row["iou"] for row in results),
        "worst_area": max(row["area_change"] for row in results),
        "worst_eye_gap": max(row["eye_gap"] for row in results),
        "still_cases": sum(1 for row in results if row["moved"] < 200),
    }
    if verbose:
        print(f"cazuri: {summary['cases']}   picate: {summary['failed']}")
        print(f"  gauri repaus (referinta): {baseline_holes}   maxim in teste: {summary['worst_holes']}")
        print(f"  gauri la guler: maxim {summary['worst_collar']} (trebuie 0)")
        print(f"  ochi gol (masca neacoperita): maxim {summary['worst_eye_gap']} (trebuie 0)")
        print(f"  variatie arie: maxim {summary['worst_area'] * 100:.2f}% (trebuie <= 2%)")
        print(f"  suprapunere silueta (informativ): minim {summary['min_iou']:.3f}")
        print(f"  cazuri fara nicio miscare: {summary['still_cases']}")
        for row, problems in failures[:10]:
            case = row["case"]
            print(f"  PICA #{row['index']:03d} x{case['angle_x']:+.1f} y{case['angle_y']:+.1f} "
                  f"z{case['angle_z']:+.1f} ochi{case['eye_open']:.1f} gura{case['mouth']:.1f}: "
                  + ", ".join(problems))
    return {"summary": summary, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser(description="Test diferențial pe rigul iZentric")
    parser.add_argument("--cases", type=int, default=CASES)
    parser.add_argument("--save-worst", type=Path, default=None)
    args = parser.parse_args()
    outcome = run(args.cases, args.save_worst)
    return 0 if outcome["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
