# STATUS — iZentric VTuber (proiect cu 5 modele)

_Actualizat: 2026-11-04 · branch `arena/1c1bafd0-zentric-youtube-monitor` · commit `6672711`_

## Faza curentă
**Faza 0 — audit și plan. Poartă G0: ⛔ FAIL (2 criterii).** Detalii în `vtuber/FAZA-0-audit.md`.

## Ce e gata
- Inventar complet al imaginilor personajului: 9 PNG 1024×1024 RGBA (vezi audit).
- Lanțul tehnic funcțional: `rig_build.py` → straturi + PSD; `rig_moc3.py` → `.moc3` + `model3/physics3/cdi3/vtube/exp3` + zip-uri; `validate_bundle.py`; `preview_moc3.py`; `diagnostic_ochi.py`.
- **118 teste trec** (`python -m pytest vtuber -q`), inclusiv 17 pentru ochi.
- Model pilot A: `vtuber/rig/izentric-vts.zip` (12 fișiere, 1,8 MB) — **netestat încă în VTS**.

## Ce lipsește (blochează G0)
1. **Pachetele de referință `Dinosaur.zip` și `ellot.zip` nu sunt în proiect** (nici în git, sunt în `.gitignore`). Fără ele nu există B1, B2, C1, C2 — adică 4 din 5 modele.
2. **Cubism Editor și VTube Studio nu există în mediul meu** (Linux fără GUI). Faza 3 și Fazele 4–5 se pot face doar pe PC-ul utilizatorului.

## Ce urmează
1. Utilizatorul încarcă cele 2 pachete de referință.
2. Pilot A până la G5: încărcare în VTS → sweep → hotkey-uri → test în OBS.
3. B1/B2: extrag „Rig Spec" din referințe, construiesc aceeași schemă pe iZentric.
4. C1/C2: după confirmarea licenței (utilizatorul a spus „ale mele").

## ⛔ Defect BLOCKER dovedit (2026-11-04)
`.moc3`-ul scris de cod **nu e valid**: Cubism Core oficial (SDK 5-r.5) crapă la încărcare
(`python vtuber/check_moc3.py vtuber/rig-2048/izentric.moc3` → `"ok": false, "error": "Core a
respins fișierul (cod -11)"`; -11 = SIGSEGV). VTS crapă din același motiv.
Textura NU era cauza: și la 2048 crapă la fel.
Consecință: nici un model din lanțul Python nu poate fi încărcat până nu se repară scriitorul.

## Defecte deschise
| # | severitate | defect | stare |
|---|---|---|---|
| 1 | BLOCKER (proiect) | referințele lipsesc → B/C imposibile | aștept fișierele |
| 2 | — | `.moc3` produs din cod, netestat în VTS | se testează la G5 |
| 3 | MINOR | 184 px diferă între `.moc3` și straturi (muchii de alpha) | acceptat |
