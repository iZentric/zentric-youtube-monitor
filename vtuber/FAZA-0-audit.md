# FAZA 0 — audit și plan (poartă G0)

_2026-11-04 · măsurat în sandbox, nu presupus_

## 1. Inventar INPUT

Nu există folder `INPUT/`. Materialele sunt în `vtuber/assets/`.

### Imaginile personajului — 9 fișiere, toate 1024×1024 RGBA

| fișier | KB | ce e |
|---|---|---|
| idle.png | 734 | repaus, ochi deschiși, gura închisă |
| blink.png | 721 | clipit |
| talking.png | 728 | gura deschisă |
| talking_blink.png | 727 | gură deschisă + clipit |
| laugh.png | 723 | râs |
| love.png | 766 | ochi inimă / drag |
| sad.png | 701 | trist |
| shocked.png | 751 | șoc |
| sus.png | 705 | suspicios |

Consecință: emoțiile există ca **desene întregi**, nu ca straturi. Lanțul le desparte în straturi
(`rig_build.py`) — de aici derivă și riscul de „bucăți tăiate greșit", tratat cu teste pixel-cu-pixel.

### Referințe — LIPSESC

| fișier | stare |
|---|---|
| `Dinosaur.zip` | **nu există** în proiect (și e în `.gitignore`) |
| `ellot.zip` | **nu există** în proiect (și e în `.gitignore`) |
| fișiere `.cmo3` | nici unul |
| fișiere `.psd` de referință | nici unul |

Rămân doar notele de audit: `vtuber/audit-A-dinosaur.md`, `vtuber/audit-B-ellot.md`.

## 2. Unelte — ce pot și ce nu pot

| unealtă | stare | dovadă |
|---|---|---|
| Python 3.11.2 | ✅ | `python3 -V` |
| numpy / Pillow / pytest / websockets / pytoshop / psd-tools / six | ✅ instalate acum | `import` OK |
| scipy / OpenCV | ❌ | nu sunt necesare |
| GUI (X/Wayland) | ❌ fără display | `DISPLAY` gol |
| **Cubism Editor** | ❌ **imposibil** | Linux headless, aplicație Windows/macOS cu licență |
| **VTube Studio** | ❌ **imposibil aici** | `127.0.0.1:8001 → Connection refused` (VTS rulează pe PC-ul tău, nu în sandbox) |
| Internet | ✅ | GitHub, docs.live2d.com |
| Control ecran/mouse | ❌ | fără GUI |

**Consecință:** Faza 3 (rig în Cubism) și Fazele 4–5 (VTS live, OBS) nu pot fi executate de mine.
Le acopăr cu: fișiere gata de încărcat, scripturi de validare + randare (`.moc3` citit și desenat
de mine), și pași manuali exacți pentru tine.

## 3. Ce există deja ca produs

`vtuber/rig/izentric-vts.zip` — 12 fișiere: `izentric.model3.json`, `.moc3` (532 800 B),
`texture_00.png` (4096), `.physics3.json`, `.cdi3.json`, `.vtube.json`, 6 × `.exp3.json`.

- 13 ArtMesh-uri, 18 parametri standard, 1060 keyform-uri.
- Ordine de desenare explicită (0–1000, crescătoare) — reparată azi; înainte toate aveau 500.
- Validare: `validate_bundle.py` → „pachet valid"; `pytest vtuber -q` → 118 trecute, 4 sărite.
- **Netestat în VTS.** Acesta e singurul lucru care poate da peste cap tot planul.

## 4. Licențe

Utilizatorul a declarat (2026-11-04): **referințele sunt ale lui / cumpărate, modificarea e
permisă**. Rămâne de completat în `LICENTE.md` cu sursa exactă și tipul licenței, pentru fiecare
din cele 2 referințe — cerut la livrare, nu blochează acum.

## 5. Ordinea propusă și estimări

| # | model | metodă | blocat de | estimare |
|---|---|---|---|---|
| 1 | A_original (pilot) | de la zero, lanțul Python | test VTS | 1–2 zile |
| 2 | B_ref1 | schemă copiată | referința 1 | 3–4 zile |
| 3 | B_ref2 | schemă copiată | referința 2 | 3–4 zile |
| 4 | C_ref1 | rig păstrat, desen înlocuit | licență + referința 1 | 4–6 zile, risc mare |
| 5 | C_ref2 | idem | licență + referința 2 | 4–6 zile, risc mare |

Pilotul A se duce până la G5 **înainte** de orice altceva: validează lanțul și criteriile.

## 6. Poartă G0

| criteriu | rezultat |
|---|---|
| inventar complet | ⛔ imagini da; **referințe lipsă** |
| unelte confirmate | 🟡 Python da; Cubism și VTS — **imposibil în sandbox**, se fac la tine |
| licențe clare | 🟡 declarate de tine, de documentat |
| plan aprobat | ⛔ așteaptă aprobarea ta |

**G0 = FAIL.** Nu avansez la Faza 1 până nu primesc referințele și „ok"-ul tău pe plan.
