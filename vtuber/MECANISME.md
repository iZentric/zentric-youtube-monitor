# Faza 0 + Faza 1 — audit A și B, matricea de mecanisme

Modele primite pe GitHub (`main`, commit `ec60448`), extrase local:
`Dinosaur.zip` = **modelul A**, `ellot.zip` = **modelul B**.
Rapoartele complete, generate automat: `audit-A-dinosaur.md`, `audit-B-ellot.md`
(`python vtuber/audit_model.py <folder> --moc3 <f> --model3 <f>`).

## Faza 0 — ce am primit

| | A (Dinosaur) | B (ellot) |
|---|---|---|
| `.moc3` | ✅ v4.2, 1,24 MB | ✅ v4.2, 5,06 MB |
| `.model3.json` | ✅ | ✅ |
| texturi | ✅ 8 × 1024×1024 | ✅ 1 × 8192×8192 |
| `.physics3.json` | ✅ (dar **nelegat** în model3) | ✅ legat |
| `.cdi3.json` | ✅ | ✅ |
| `.exp3.json` | ✅ 8 | ✅ 9 |
| `.motion3.json` | ✅ 1 (`Tearing`, nelegat) | ✅ 1 (`Scene1`, nelegat) |
| `.vtube.json` | ✅ + `items_pinned_to_model.json` | ✅ + `items_pinned_to_model.json` |
| sursă de editare | ⛔ niciun PSD / `.cmo3` / `.can3` | 🟡 `Untitled Animation.can3` (doar animație) |

Fără PSD/cmo3 nu pot muta mesh-uri sau edita rig-ul existent — relevant la Faza 2.

## Faza 1 — audit

### A — Dinosaur
- 133 ArtMesh, 123 parametri (30 standard / 93 custom), 30 părți, 163 warp + 24 rotation deformeri, 40 măști, 8 texturi folosite toate.
- Fizică: 62 setări (păr, coadă, aripi, jachetă, saturn, sclipiri) — **`model3.json` nu conține cheia `Physics`**, deci în VTS fizica nu rulează. Fișierul e complet, doar nelegat.
- Expresii (8, toate doar în `.vtube.json`): Sad (sprâncene + lacrimi `ParamLTearVis/ParamRTearVis` + gură), Angry (sprâncene + gură), Happy (`ParamSparkle`), Panic Eye (`ParamPanic`), Pale (`ParamPaleface`), Sweating (`ParamSweatSwitch`), SaturnRing Vis (`ParamSaturnVis`), LittleDragon Vis (`ParamDragonVis`).
- Mișcări: `Tearing.motion3.json` (picătură de lacrimă), nu e legată în model3.
- VTS: 18 Parameter Setup (unghiuri cap −30..30 → ParamAngle*, corp → ParamBodyAngle*, ochi, sprâncene, gură, auto-breath, **blush automat la zâmbet**: `MouthSmile → ParamCheek 0.5..1` smoothing 45), 9 hotkeys (8 expresii + 1 animație), tint gol, items pinned fără intrări.

### B — ellot
- 240 ArtMesh, 171 parametri (19 standard / 152 custom, majoritatea `ParamNNN` fără nume), 32 părți, 416 warp + 2 rotation deformeri, 36 măști, **o singură textură 8192** (8× suprafața lui A, grea pentru GPU).
- Fizică: 62 setări legate, ieșirile sunt `ParamNNN` — fiecare șuviță de păr/haină are parametrul ei; intrare principală `ParamAngleX/Z` + `ParamBodyAngle*`.
- Expresii (9, doar în `.vtube.json`, nume coreene): lacrimi, ochi sclipitori, „întunecat", ochi inimă, obrajii roșii, ochelari pe cap, ochelari pe față, furie, gamepad — toate comută vizibilitatea unor ArtMesh prin parametri `ParamNNN`.
- VTS: 25 Parameter Setup (include `TongueOut`, `CheekPuff`, `MouthX`, `MouthFunnel`, `MouthShrug`, `MouthPucker` → parametri de gură), 10 hotkeys incl. **`RemoveAllExpressions`**.

### Puncte slabe găsite
1. **A: fizica nu e legată** — modelul pare rigid deși are 62 setări gata făcute.
2. **B: parametri fără nume** (`Param118`…`Param152`) — imposibil de depanat, hotkeys fragile.
3. Ambele: nicio expresie în `model3.json` (doar hotkeys VTS) → cine încarcă modelul în alt runtime (warudo/PrprLive) nu vede expresiile.
4. Ambele: fără `HitAreas` (nu răspunde la click pe cap/corp), fără `Pose`.
5. Ambele: nicio referință la mișcări în `model3.json`.
6. A: 8 texturi separate (8 draw calls), B: o textură 8192 (VRAM).

## Matricea de mecanisme (A ∪ B → modelul nou)

| Mecanism | A | B | Decizie |
|---|---|---|---|
| Unghiuri cap X/Y/Z | ✅ −30..30 | ✅ −30..30 | **păstrăm B** (input −40..40, clamp mai larg) |
| Corp X/Y/Z | ✅ ±10 | ✅ X±10 Y±5 Z±10 | combinăm: X±10, Y±5, Z±10 |
| Deschidere ochi L/R | ✅ 0..0.7 | ✅ 0..1 → 0..1.9 | **B** (rezervă peste 1.0 pentru ochi mari) |
| Zâmbet ochi L/R (`EyeSmile`) | ✅ din `MouthSmile` | ✅ din `MouthSmile` | păstrăm |
| Glob ocular X/Y | ✅ ±0.8 / −0.5..0.8 | ✅ ±1 | **B** (interval complet) |
| Sprâncene Y L/R | ✅ | ✅ | păstrăm |
| Sprâncene Form L/R | ⛔ | ✅ | **B** |
| Gură: formă + deschidere | ✅ (−0.2..0.8 / 0.4..0.8) | ✅ (0..1 / 0.03..0.7 → 0..2.1) | **B** |
| Gură: TongueOut, CheekPuff, MouthX, Funnel, Shrug, Pucker | ⛔ | ✅ | **B** |
| Auto-breath | ✅ `ParamBreath` | ✅ | păstrăm |
| Blush automat la zâmbet | ✅ `ParamCheek` | ⛔ (blush doar pe hotkey) | **A** + hotkey din B |
| Fizică păr/haine/corp | ✅ 62 setări (nelegate) | ✅ 62 setări (legate) | **B** ca model de legare; setările A refolosite pentru coadă/aripi dacă apar |
| Expresii fețe: trist / furie / fericit | ✅ | ✅ (parțial suprapuse) | combinăm, aceleași nume |
| Lacrimi | ✅ expresie + motion `Tearing` | ✅ expresie | combinăm: expresie + motion |
| Obrajii roșii | ✅ automat | ✅ hotkey | ambele |
| Ochi sclipitori / ochi inimă / „întunecat" | 🟡 `Sparkle`, `Panic` | ✅ 3 expresii | **B** |
| Pale | ✅ | ⛔ | A |
| Sweating | ✅ | ⛔ | A |
| Props: saturn, dragon, ochelari cap/față, gamepad | ✅ saturn + dragon | ✅ ochelari ×2 + gamepad | toate, ca expresii de vizibilitate |
| `RemoveAllExpressions` | ⛔ | ✅ | **B** |
| HitAreas cap/corp | ⛔ | ⛔ | EXTRA (îl adaug eu) |
| Mișcări idle/oops | ⛔ | ⛔ (are `Scene1` nelegat) | legăm ce există + idle simplu |
| Items pinned | ✅ gol | ✅ gol | structura o păstrez, conținutul e al tău |
| Tint / scene lighting | gol | gol | nu inventăm |

**Conflict rezolvat:** deschiderea ochilor — A limitează inputul la 0..0.7 ca să nu spargă pleoapa, B lasă până la 1.9 cu parametrul mergând peste 1. Aleg B pentru că permite clipit + ochi mari fără să atingă plafonul, dar leg maparea pe graficul feței mele (0..1, nu 0..1.9) ca să nu tremure.

## Faza 2 — verdict (previzualizare, aștept confirmarea)

Personajul tău există ca **9 desene PNG 1024×1024** (repaus, clipit, vorbit, vorbit+clipit, râs, îndrăgostit, trist, șocat, suspicios), fără PSD și fără mesh.

- **DRUMUL A (reskin pe mesh-ul A sau B): ⛔ imposibil.** N-am PSD-ul lor și nici al tău; a desena peste UV-urile lor ar însemna să inventez artă care nu e a ta. Contradice regula „personajul arată ca el".
- **DRUMUL B (PSD → Cubism → export): 🟡 posibil**, dar cere Cubism Editor la tine și încă nu știu dacă îl ai; rezultatul depinde de ochiul tău la rigging.
- **DRUMUL C (scriitorul meu de `.moc3`, verificat cu Cubism Core): ✅ recomandat.** Iau cele 9 desene ale tale, le despart în straturi, construiesc mesh-urile, parametrii și fizica din matricea de mai sus, generez `.moc3` + `.model3.json` + `.physics3.json` + `.exp3.json` + `.vtube.json` și verific fiecare pas cu Cubism Core (validatorul din repo). Tu încarci folderul în VTS.

Ce **am** din desenele tale: cap, față, păr (o singură bucată desenată), ochi, gură ×5 (râs/trist/șocat/îndrăgostit/suspicios), corp/haine.
Ce **lipsește** pentru mecanismele din matrice: straturi separate de păr (breton / lateral / spate) pentru fizică, sprâncene separate, pleoape, blush, lacrimi, sclipiri, ochi inimă, props (ochelari, gamepad, saturn, dragon), gură fonetică A/I/U/E/O.
