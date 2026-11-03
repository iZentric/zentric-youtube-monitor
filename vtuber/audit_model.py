"""Audit al unui model Live2D/VTube Studio: mecanisme, nu artă.

Folosire: python vtuber/audit_model.py <folder_model> --moc3 <fisier.moc3> [--model3 ...]
Scrie markdown pe stdout.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from moc3_read import Moc3


def _fmt_param(p: dict) -> str:
    """Expresiile au două forme: Value listă de benzi (Value/Blend) sau float simplu."""
    val = p.get("Value")
    if isinstance(val, list):
        return f"{p['Id']}=" + "/".join(f"{b['Value']:g}" for b in val)
    return f"{p['Id']}={val:g}"


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def audit(folder: str, moc3_path: str, model3_path: str) -> str:
    out = []
    add = out.append
    model3 = _load(model3_path)
    fr = model3["FileReferences"]
    moc = Moc3(moc3_path)
    cdi = _load(os.path.join(folder, fr["DisplayInfo"])) if fr.get("DisplayInfo") else {}

    add(f"# Audit: {os.path.basename(moc3_path)}")
    add("")
    add(f"- moc3: versiune {moc.blob[4]} ({len(moc.blob)} B), "
        f"{moc.counts[4]} art mesh, {moc.counts[5]} parametri, {moc.counts[0]} părți, "
        f"{moc.counts[2]} warp + {moc.counts[3]} rotation deformeri, {moc.counts[17]} măști")
    tex = fr.get("Textures", [])
    add(f"- texturi: {len(tex)}")
    for t in tex:
        p = os.path.join(folder, t)
        from PIL import Image
        with Image.open(p) as im:
            add(f"  - {t}: {im.size[0]}x{im.size[1]} {im.mode}")
    add(f"- fișiere: fizică={bool(fr.get('Physics'))}, cdi={bool(fr.get('DisplayInfo'))}, "
        f"expresii={len(fr.get('Expressions', []))}, mișcări={sum(len(v) for v in fr.get('Motions', {}).values())}")

    # --- parametri
    params = moc.parameters()
    groups = {g["Id"]: g for g in cdi.get("ParameterGroups", [])}
    by_group = {}
    for p in params:
        by_group.setdefault(p.get("group", "?"), []).append(p["id"])
    add("")
    add(f"## Parametri ({len(params)})")
    add("")
    add("| id | min | max | default |")
    add("|---|---|---|---|")
    for p in params:
        add(f"| {p['id']} | {p['min']:.2f} | {p['max']:.2f} | {p['default']:.2f} |")

    if cdi:
        add("")
        add("## Grupuri de parametri / părți (cdi3)")
        add("")
        for g in cdi.get("ParameterGroups", []):
            add(f"- {g.get('Name')} → {len(g.get('Ids', []))} parametri")
        add(f"- părți cdi3: {len(cdi.get('Parts', []))}")

    # --- art meshes pe textură
    ams = moc.art_meshes()
    add("")
    add(f"## ArtMesh ({len(ams)})")
    add("")
    add("| id | textură | vertecși | UV x0,y0 → x1,y1 | mască |")
    add("|---|---|---|---|---|")
    for a in ams:
        u = a["uv"]
        add(f"| {a['id']} | {a['texture']} | {a['vertices']} | "
            f"{u[0]:.3f},{u[1]:.3f} → {u[2]:.3f},{u[3]:.3f} | {a['mask_count']} |")

    # --- fizică (și când fișierul există dar nu e legat în model3)
    physics_file = fr.get("Physics") or next(
        (os.path.basename(f) for f in glob.glob(os.path.join(folder, "*.physics3.json"))), None)
    if physics_file:
        ph = _load(os.path.join(folder, physics_file))
        meta = ph["Meta"]
        if not fr.get("Physics"):
            add("")
            add(f"**Atenție:** `{physics_file}` există dar NU e referit în model3 → fizica nu rulează în VTS.")
        add("")
        add(f"## Fizică: {meta['PhysicsSettingCount']} setări, "
            f"{meta['TotalInputCount']} intrări, {meta['TotalOutputCount']} ieșiri")
        add("")
        add("| setare | intrări | ieșiri |")
        add("|---|---|---|")
        for s in ph["PhysicsSettings"]:
            ins = ", ".join(sorted({i["Source"]["Id"] for i in s["Input"]}))
            outs = ", ".join(sorted({o["Destination"]["Id"] for o in s["Output"]}))
            add(f"| {s['Id']} | {ins} | {outs} |")

    # --- expresii
    add("")
    add("## Expresii")
    add("")
    for e in fr.get("Expressions", []):
        path = os.path.join(folder, e["File"])
        if not os.path.exists(path):
            add(f"- {e.get('Name')}: **fișier lipsă** {e['File']}")
            continue
        exp = _load(path)
        parts = []
        for p in exp.get("Parameters", []):
            vals = ", ".join(f"{b['Value']:g}({b['Blend']})" for b in p["Value"])
            parts.append(f"{p['Id']}={vals}")
        fade = exp.get("FadeInTime", 0), exp.get("FadeOutTime", 0)
        add(f"- **{e.get('Name')}** (fade {fade[0]}/{fade[1]}): " + "; ".join(parts))
    for f in sorted(glob.glob(os.path.join(folder, "**", "*.exp3.json"), recursive=True)):
        name = os.path.basename(f)
        if any(name == os.path.basename(e["File"]) for e in fr.get("Expressions", [])):
            continue
        exp = _load(f)
        parts = [_fmt_param(p) for p in exp.get("Parameters", [])]
        add(f"- (nelegat în model3) {name}: " + "; ".join(parts))

    # --- mișcări
    add("")
    add("## Mișcări")
    add("")
    for group, items in fr.get("Motions", {}).items():
        for item in items:
            path = os.path.join(folder, item["File"])
            if not os.path.exists(path):
                add(f"- {group}/{item['File']}: **lipsă**")
                continue
            mot = _load(path)
            meta = mot.get("Meta", {})
            add(f"- {group}: {item['File']} — durată {meta.get('Duration', 0):.2f}s, "
                f"loop={meta.get('Loop')}, fadeIn={meta.get('FadeInTime')}, "
                f"curbe={len(mot.get('Curves', []))}, "
                f"parametri={sorted({c['Target'] for c in mot.get('Curves', [])})[:8]}")
    if not fr.get("Motions"):
        add("- (niciuna în model3)")

    # --- vtube.json
    vt_path = glob.glob(os.path.join(folder, "*.vtube.json"))
    if vt_path:
        vt = _load(vt_path[0])
        add("")
        add(f"## VTube Studio ({os.path.basename(vt_path[0])})")
        add("")
        ps = vt.get("ParameterSettings", [])
        add(f"### Parameter Setup ({len(ps)})")
        add("")
        add("| nume | input VTS | → parametru | interval | smoothing | blink | breath |")
        add("|---|---|---|---|---|---|")
        for s in ps:
            add(f"| {s.get('Name')} | {s.get('Input')} | {s.get('OutputLive2D')} | "
                f"{s.get('InputRangeLower'):g}..{s.get('InputRangeUpper'):g} → "
                f"{s.get('OutputRangeLower'):g}..{s.get('OutputRangeUpper'):g} | "
                f"{s.get('Smoothing', 0)} | {s.get('UseBlinking')} | {s.get('UseBreathing')} |")

        hk = vt.get("Hotkeys", [])
        add("")
        add(f"### Hotkeys ({len(hk)})")
        add("")
        add("| nume | acțiune | fișier/țintă | trigger |")
        add("|---|---|---|---|")
        for h in hk:
            trig = h.get("Trigger") or {}
            desc = trig.get("TriggerType") or ""
            if trig.get("KeyboardKey"):
                desc += f" {trig['KeyboardKey']}"
            if trig.get("HotkeyRangeLower") is not None:
                desc += f" [{trig.get('HotkeyRangeLower')}..{trig.get('HotkeyRangeUpper')}]"
            add(f"| {h.get('Name')} | {h.get('Action')} | {h.get('File') or h.get('Target') or ''} | {desc} |")

        ar = vt.get("ArtMeshDetails", {})
        add("")
        add("### ArtMesh tint / scene lighting")
        for k, v in ar.items():
            add(f"- {k}: {json.dumps(v, ensure_ascii=False)[:400]}")
        it = vt.get("ItemSettings", {})
        pin = os.path.join(folder, "items_pinned_to_model.json")
        add("")
        add("### Items")
        add(f"- pinned: {json.dumps(_load(pin), ensure_ascii=False)[:300] if os.path.exists(pin) else 'niciunul'}")
        add(f"- setări: {json.dumps(it, ensure_ascii=False)[:400]}")
        add("")
        add("### Setări generale")
        for k, v in (vt.get("GeneralSettings") or {}).items():
            add(f"- {k}: {v}")
        for k, v in (vt.get("PhysicsSettings") or {}).items():
            add(f"- fizică VTS {k}: {v}")
    return "\n".join(out)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--moc3", required=True)
    ap.add_argument("--model3", required=True)
    args = ap.parse_args(argv)
    print(audit(args.folder, args.moc3, args.model3))


if __name__ == "__main__":
    main(sys.argv[1:])
