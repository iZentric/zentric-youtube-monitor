# RIG.md — de la pozele tale la model `.moc3` pentru VTube Studio

## Ce e gata (generat, verificat)

`python vtuber/rig_build.py` produce în `vtuber/rig/`:

| fișier | ce e |
| --- | --- |
| `izentric.psd` | **PSD cu 6 straturi**, 1024×1024, cu transparență — se deschide direct în Ayatsuri2D, Umamo sau Cubism |
| `head.png` | capul, cu irisul scos și albul ochiului pus în loc |
| `body.png` | hanoracul și umerii |
| `iris_L.png`, `iris_R.png` | irisurile cu pupilă și reflexe, mutabile |
| `eyes_closed.png` | pleoapele închise (din `blink`) |
| `mouth_open.png` | gura deschisă (din `talking`) |
| `izentric.model3.json`, `izentric.cdi3.json` | fișierele care însoțesc modelul: ce încarcă VTube Studio + numele parametrilor |

Verificare automată, nu pe încredere: `body` + `head` + `iris_L` + `iris_R` recompuse dau `idle.png` cu **eroare RMS 0,17** (4 miimi din pixeli diferiți, din rotunjiri). Adică straturile sunt exact poza ta, tăiată — nimic redesemnat.

Cercurile irisurilor sunt **măsurate** pe poza ta (stâng: centru 410,427 rază 52; drept: centru 607,424 rază 52). Dacă la mișcarea ochiului iese o margine, le ajustezi:

```
python vtuber/rig_build.py --iris L:410,427,52 --iris R:607,424,52
```

## Ultimul pas: nu se poate face din cod

`.moc3` e formatul de runtime al Live2D. **Nu există unealtă cu linie de comandă care să-l scrie** — Ayatsuri2D, Umamo și Cubism sunt toate editoare cu interfață, iar fișierul conține plase (mesh), deformatoare, keyform-uri și atlase de texturi care se construiesc prin editare. Am verificat alternativele înainte să ți le propun:

| unealtă | preț | deschide PSD | exportă moc3 | poate rula fără interfață |
| --- | --- | --- | --- | --- |
| **Ayatsuri2D** | gratis, GPL-3.0 | da | da, 3.0–5.3 (5.0 e ok pentru VTS) | nu |
| Umamo | gratis, GPL-3.0 | da | da, până la 5.4 | nu |
| Live2D Cubism FREE | gratis, dar limite: 100 mesh-uri, o textură de 2048 | da | da | nu |
| Cubism PRO | abonament | da | da | nu |

Deci ultimii ~20 de minute le faci tu în Ayatsuri2D (gratis, fără cont, fără limite la export). Restul e gata: PSD-ul are deja straturile în ordinea corectă și numele potrivite.

## Pașii în Ayatsuri2D (20–40 min)

1. Descarci de pe `ayatsuri-2d.org` (Windows), deschizi, `File > Import PSD…` → `vtuber/rig/izentric.psd`.
2. Fiecare strat devine o parte cu mesh automat. Nu mișca nimic: pozițiile sunt deja corecte, se aliniază de la colțul din stânga-sus.
3. Creezi parametrii din `izentric.cdi3.json` (butonul de import parametri sau manual, în ordinea asta): `ParamAngleX (-30..30)`, `ParamAngleY (-30..30)`, `ParamAngleZ (-30..30)`, `ParamEyeLOpen (0..1)`, `ParamEyeROpen (0..1)`, `ParamEyeBallX (-1..1)`, `ParamEyeBallY (-1..1)`, `ParamMouthOpenY (0..1)`, `ParamBreath (0..1)`, `ParamBodyAngleX (-10..10)`.
4. Lege straturile de parametri, exact așa:

| strat | parametru | ce faci în editor |
| --- | --- | --- |
| `head` | `ParamAngleX/Y/Z` | warp deformer pe tot capul; la X=-30 mută capul la stânga, la +30 la dreapta; la Z înclină ±10° |
| `body` | `ParamBodyAngleX`, `ParamBreath` | warp ușor stânga-dreapta; la `Breath` 0→1 ridică umerii 3–4 px |
| `iris_L`, `iris_R` | `ParamEyeBallX/Y` | translație ±10 px, **cu clipping** pe albul ochiului ca să nu iasă |
| `eyes_closed` | `ParamEyeLOpen`, `ParamEyeROpen` | opacitate 0 la deschis, 100 la închis (sau clipping cu pleoapa) |
| `mouth_open` | `ParamMouthOpenY` | opacitate 0→100; închis e deja desenat în `head` |

5. `Export > moc3`, versiunea **5.0** (VTube Studio nu deschide 5.3), cu `model3.json` și `texture_00.png` bifeză.
6. Pui folderul în `%USERPROFILE%\AppData\LocalLow\DenchiSoft\VTubeStudio\Live2DModels\izentric\` și îl încarci în VTS.

## Ce lipsește din desen (nu din cod)

- **sprâncene separate** — acum sunt desenate în cap, deci nu pot ridica independent;
- **păr pe straturi** (față/spate) — fără ele nu ai fizică la păr;
- **gura pe jumătate** — `mouth_open` comprimat vertical dă o aproximare bună, dar un desen dedicat e curat.

Toate trei sunt în `ART-BRIEF.md`. Modelul funcționează și fără ele — doar că sprâncenele nu se mișcă separat și părul nu are fizică.

## Ce rămâne neverificat

Ayatsuri2D, Umamo și VTube Studio nu rulează în sandbox (fără interfață grafică), deci **nu am putut face eu exportul moc3 și nu am putut deschide modelul în VTS**. Ce e verificat: PSD-ul se citește înapoi corect, are 6 straturi cu alfa, iar compoziția lui dă poza originală la pixel. Restul e pe PC-ul tău.
