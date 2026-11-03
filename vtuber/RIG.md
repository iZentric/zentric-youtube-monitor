# RIG.md — model Live2D pentru VTube Studio, construit pe standardul oficial

## Pe ce mă bazez (surse, nu impresii)

Fișierele generate aici respectă schemele modelului oficial Live2D, luate din repo-ul `Live2D/CubismWebSamples`:

| ce | sursă |
| --- | --- |
| structura `model3.json` | `Samples/Resources/Mao/Mao.model3.json` — `Version`, `FileReferences{Moc, Textures, Physics, Pose, DisplayInfo, Expressions, Motions}`, `Groups[{Target:"Parameter", Name:"LipSync"/"EyeBlink", Ids}]`, `HitAreas[{Id, Name}]` |
| ID-urile și grupele de parametri standard | `Mao.cdi3.json` — `ParamGroupFace`, `ParamGroupEyes`, `ParamGroupEyeballs`, `ParamGroupBrows`, `ParamGroupMouth`, `ParamGroupBody`, `ParamGroupSway` |
| structura `physics3.json` | `Mao.physics3.json` — `Meta{Fps, EffectiveForces{Gravity, Wind}, PhysicsDictionary}`, `PhysicsSettings[{Input, Output, Vertices, Normalization}]` |

De ce contează: VTube Studio nu ghicește nimic. Dacă grupul `EyeBlink` nu conține `ParamEyeLOpen`/`ParamEyeROpen`, clipitul automat nu merge; dacă `LipSync` nu conține `ParamMouthOpenY`, gura nu se mișcă. Numele inventate = model care se încarcă și nu face nimic.

## Ce e generat (`python vtuber/rig_build.py`)

| fișier | ce e |
| --- | --- |
| `izentric.psd` | PSD grupat: **FACE** (eyes_closed, mouth_open — ascunse; iris_L, iris_R), **MASKS** (eye_mask_L/R, grup ascuns), **HEAD**, **BODY** |
| `izentric.model3.json` | conform schemei Mao, cu `Groups` EyeBlink + LipSync și `HitAreas` Head + Body |
| `izentric.cdi3.json` | 16 parametri cu ID-urile standard și grupele standard |
| `izentric.rigspec.json` | **specificația de rig**: arborele de deformatoare, keyform-urile în pixeli, clippingul |
| `head.png`, `body.png` | tăiate la guler (y=655); **gâtul e în cap, gulerul în trup**, iar gulerul se desenează deasupra — la rotire capul ia gâtul cu el și nu se vede cusătură |
| `iris_L.png`, `iris_R.png` | discuri de rază 52 la (410,427) și (607,424), măsurate pe poza ta |
| `eye_mask_L.png`, `eye_mask_R.png` | elipsele de clipping pentru irise (1,55× / 1,45× raza irisului) |
| `eyes_closed.png`, `mouth_open.png` | pleoapele și gura, extrase din `blink` / `talking` |

Verificat automat: `body` + `head` + cele două irise recompuse dau `idle.png` cu **RMS 0,10** — adică poza ta, tăiată corect, fără nimic redesemnat.

## Specificația de rig (din `izentric.rigspec.json`)

Arbore de deformatoare:

Ordinea de desenare (de sus în jos): `eyes_closed`, `mouth_open`, `iris_L`, `iris_R`, `body`, `head`.
Trupul stă **peste** cap: gulerul acoperă îmbinarea, deci capul poate roti fără cusătură vizibilă.

```
D_Root
├── D_HeadRot (rotation, pivot 512,655)        ← ParamAngleZ
│   └── D_HeadWarp (warp, pivot 512,430)       ← ParamAngleX, ParamAngleY
│       ├── head (cu gâtul), eyes_closed, mouth_open
│       └── iris_L, iris_R (cu clipping pe eye_mask_L/R)
└── D_Body (warp, pivot 512,900)               ← ParamBodyAngleX, ParamBodyAngleZ, ParamBreath
    └── body (fără piele: doar hanoracul)
```

Testat la rotirea maximă din spec: la ±8° rămân **0, respectiv 1 pixel** transparent în banda gulerului (verificat de `test_no_gap_at_the_collar_when_the_head_rotates`).

Keyform-uri (pe canvasul de 1024):

| parametru | valoare | efect |
| --- | --- | --- |
| `ParamAngleX` | ±30 | cap ±14 px orizontal |
| `ParamAngleY` | ±30 | cap ∓10 px vertical |
| `ParamAngleZ` | ±30 | rotire cap ±8° în jurul gâtului |
| `ParamEyeLOpen` / `ParamEyeROpen` | 0 → 1 | `eyes_closed` opacitate 100 → 0 |
| `ParamEyeBallX` | ±1 | irise ±11 px (cu clipping) |
| `ParamEyeBallY` | ±1 | irise ±9 px (cu clipping) |
| `ParamMouthOpenY` | 0 → 1 | `mouth_open` opacitate 0 → 100 |
| `ParamBodyAngleX` | ±10 | trup ±6 px |
| `ParamBreath` | 0 → 1 | trup −3 px |

## Ultimul pas: exportul `.moc3` (nu se poate face din cod)

`.moc3` conține plase, deformatoare, keyform-uri și atlas de texturi — se construiește doar prin editare, iar toate editoarele care îl scriu au interfață grafică. Verificat pe surse:

| unealtă | licență | deschide PSD | exportă moc3 | CLI |
| --- | --- | --- | --- | --- |
| **Ayatsuri2D** | GPL-3.0, gratis | da (PSD/Krita/Clip) | da, 3.0–5.3, implicit 5.0 | nu |
| Umamo | GPL-3.0, gratis | da | da, până la 5.4 | nu |
| Live2D Cubism FREE | gratis, limite 100 mesh / 2048 px | da | da | nu |

### Pașii în Ayatsuri2D (20–40 min)

1. `File > Import PSD…` → `vtuber/rig/izentric.psd`. Grupurile devin părți, layerele devin mesh-uri.
2. Deschizi `izentric.rigspec.json` într-un editor de text lângă — fiecare valoare din tabel e gata calculată.
3. Creezi deformatoarele din arborele de mai sus (2 warp-uri + 1 rotation).
4. Legi parametrii din tabelul de keyform-uri; irisele primesc clipping pe `eye_mask_L`/`eye_mask_R`.
5. `Export > moc3`, versiunea **5.0**, cu `model3.json` și texturile.
6. Verifici înainte de VTS:

```
python vtuber/check_model.py <folderul exportat>
```

Îți spune în 2 secunde dacă modelul se încarcă: moc3 lipsă, moc3 prea nou pentru VTS, textură peste 4096, parametru din `Groups` care nu există în `cdi3`, referințe către fizică/expresii care duc în gol. Validatorul e testat pe un model Live2D real (Mao, moc3 v5) — trece.

## Ce lipsește din desen, nu din cod

- **sprâncenele** sunt desenate în cap → `ParamBrowLY/RY` există în `cdi3`, dar nu au ce mișca;
- **părul** nu e pe straturi → fără fizică (de aici și `ParamHairFront`, `ParamString` declarate dar nelegate);
- **gura pe jumătate** desenată — acum se aproximează prin comprimarea verticală a gurii deschise.

Toate trei sunt în `ART-BRIEF.md`.

## Ce rămâne neverificat

Ayatsuri2D, Umamo și VTube Studio nu rulează în sandbox (fără interfață grafică), deci **exportul moc3 și încărcarea în VTS nu au fost făcute de mine**. Verificat: PSD-ul se recitește corect (4 grupuri, 8 layere, variantele ascunse), compoziția vizibilă dă `idle.png` la pixel, schemele JSON sunt cele oficiale, iar validatorul trece pe un model real.

## Previzualizare în mișcare

`python vtuber/rig_preview.py` scrie `vtuber/rig/preview.gif`: 90 de cadre, 6 secunde,
capul se uită stânga–dreapta (±22°), se înclină (±5°), clipește de două ori și vorbește.
Mișcările folosesc exact valorile din `izentric.rigspec.json`, deci ce se vede în GIF este
ce va face modelul după export.

Verificat prin teste (`vtuber/test_rig_preview.py`, 7 teste):

| cadru | referință | rms |
|---|---|---|
| repaus | `assets/idle.png` | **0,03** |
| ochi închiși | `assets/blink.png` | 5,56 |
| gură deschisă | `assets/talking.png` | 4,29 |

Irisul este testat la toate cele 9 poziții (±1, ±1) și nu iese din masca ochiului la niciuna.

## Strat nou: BACKING (spatele gulerului)

La rotație maximă, între gât și guler se vedea fundalul. Două reparacii, ambele măsurate:

1. **gâtul coboară 100 px sub linia gulerului** și e vopsit în culoarea pielii (medie din
   jurul gulerului, cu umbră spre interior). Gulerul, desenat deasupra, îl ascunde la repaus
   și îl folosește ca umplutură la rotație.
2. **stratul BACKING** umple deschizătura husei cu culoarea estompată a husei. E la fundul
   stivei și nu iese niciodată în afara siluetei (testat).

### Ordinea din PSD era inversată

Până acum, în PSD grupul HEAD ajungea deasupra lui BODY — adică gulerul nu ar fi acoperit
gâtul după importul în editor. Acum `DRAW_ORDER` se **derivă** din `GROUPS`, iar testul
compară ordinea citită din PSD cu `DRAW_ORDER`, deci nu mai pot diverge.

## Harness diferențial: 281 de cazuri

`python vtuber/differential.py --cases 281` — fiecare caz e desenat și măsurat:

| măsurătoare | limită | rezultat |
|---|---|---|
| găuri în siluetă (se vede dedesubt) | ≤ 164 (cât are arta de repaus) | **164** |
| găuri în banda gulerului | 0 | **0** |
| iris ieșit din masca ochiului | 0 | **0** |
| variația ariei personajului | ≤ 2 % | **1,27 %** |
| cazuri picate | 0 | **0 / 281** |

Comparație cu modelele oficiale (`python vtuber/reference_diff.py`, Haru/Hiyori/Mao):
**0 parametri inventați**, toate cele 16 ID-uri sunt standard; 170 de parametri standard
lipsesc (brațe, păr, fizică, cele 5 vocale) — exact lucrurile care cer artă separată.

## Ochiul care se uită în altă parte

Problema raportată: când irisul se mută, în urmă se vedea urât. Cauza nu era un singur
lucru, ci trei, toate măsurate:

1. **Irisul nu era decupat pe desen** — se folosea un disc ghicit (rază 52) în loc de forma
   reală. Irisul din desen are 105 px lățime la ochiul albastru și 86 px la cel roșu, deci
   rămânea o verigă de iris în cap. Acum forma se ia din saturație (`iris_blob`), iar
   conturul închis al irisului se adaugă explicit (`iris_mask_with_outline`).
2. **Albul ochiului era vopsit cu o culoare plată** `[248,250,252]`, deci apărea un disc
   alb vizibil. Acum se rezolvă o umplere armonică (`eye_white`): fiecare pixel devine
   media vecinilor, marginea rămâne culoarea desenului → umbra de sub pleoapă continuă
   natural, fără cusătură.
3. **Capul se construia din desenul original**, nu din imaginea cu irisul scos — un bug de
   o linie (`head_pixels[:CUT_Y] = pixels[:CUT_Y]`), din cauza căruia tot efortul de
   ștergere a irisului se pierdea. Acum folosește imaginea curățată.

Verificat (`vtuber/test_rig_build.py`):

| măsurătoare | rezultat |
|---|---|
| culoare de iris rămasă în cap | **2 px** dintr-un iris de ~9 000 |
| zona descoperită la privire maximă | luminanță medie **186**, abatere **54** (nu e plată) |
| pixeli întunecați rămași în urmă | **0** |
| cadru de repaus vs `idle.png` | rms **1,17** (doar 1-2 px la marginea irisului) |

Comparație vizuală: `vtuber/rig/eye-before-after.png` (stânga înainte, dreapta după).
