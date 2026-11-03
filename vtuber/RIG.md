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

## Gâtul și ochii: ce s-a reparat, măsurat

Trei lucruri cerute explicit — „nici un pixel pus prost", „să nu îi fuga gâtul", „să nu aibă
ochi sub ochi" — sunt acum reparate și măsurate, nu „arată bine".

**Gâtul.** Nu se mai desenează nimic peste el. Banda de gât din stratul HEAD este exact ce e
desenat în poză: `head[band] = pixels[band]` doar acolo unde pixelul e piele, restul 0.
Orice culoare inventată (ton mediu, gradient, continuarea rândului de deasupra) se vedea
prin deschizătura husei ca o pată — de aceea a fost scoasă complet.

Sub guler, gaura din BODY se umple cu **țesătura husei** (difuzie din jur, 400 de iterații),
nu cu ce e sub cap: acolo arta e goală și ieșea o dungă gri lipită de guler.

**Capul se deformează, nu se mută.** `_warp_head` mută rândurile gradual: 0 px la guler
(y=655), maxim sus (y=37). Așa capul se înclină fără să descopere gulerul. Rotația se face
în jurul lui (512, 700), nu al pivotului, ca gulerul să rămână pe loc.

**Pleoapele acoperă ochiul, nu se estompează peste el.** Stratul `eyes_closed` era o
„diferență" estompată pe 7 px: la opacitate maximă rămânea urma ochiului deschis dedesubt
plus un inel gri în jurul pleoapei. Acum e decupat tare (margine 0 px) pe zona care chiar
se schimbă între deschis și închis. Rezultat: rama închisă = poza `blink.png`
(aberație maximă 29 pe 5 pixeli), gura deschisă = poza `talking.png` (36 pe 45 de pixeli).

**Dovadă că nu e ochi sub ochi:** la toate cele 9 poziții ale privirii (±1 pe X și Y), banda
de sub fiecare pleoapă are **0 pixeli întunecați** și exact același număr de pixeli ca poza
originală — privirea nu adaugă nimic acolo. Vezi `test_nothing_eye_coloured_under_the_eye_when_the_gaze_moves`.

Imagini de control: `vtuber/rig/verificare-gat.png` (repaus, ±30°) și
`vtuber/rig/verificare-ochi.png` (deschis / închis / pe jumătate / vorbit).
