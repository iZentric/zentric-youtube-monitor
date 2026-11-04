# iZentric — instalare în VTube Studio

Ce e în folderul ăsta: **model complet, gata de încărcat** (12 fișiere, 2,2 MB).
Nu trebuie redenumit nimic — fișierele se referă între ele pe nume.

## Pași

1. Copiază **tot folderul** `A_original` în:

   ```
   ...\steamapps\common\VTube Studio\VTube Studio_Data\StreamingAssets\Live2DModels\
   ```

   și redenumește-l `iZentric` (să nu rămână `A_original`).

   Dacă nu găsești folderul: în VTS, *Model Settings* îți arată calea folosită.

2. Verifică structura — `izentric.model3.json` trebuie să fie **direct** în `iZentric\`,
   lângă `.moc3` și `texture_00.png`. Dacă ai `iZentric\A_original\...`, e un nivel în plus:
   mută conținutul un nivel mai sus.

3. Pornește VTS → click pe model / *Change model* → **iZentric** apare în listă → dublu-click.

## Ce ar trebui să meargă

| | |
|---|---|
| parametri | `ParamAngleX/Y/Z` ±30, `ParamBodyAngleX/Z` ±10, `ParamEyeLOpen/ROpen`, `ParamEyeBallX/Y`, `ParamMouthOpenY`, `ParamBreath`, `ParamHairSwayX`, `ParamHornsVis`, 5 × `ParamExpr*` |
| expresii (hotkey) | râs, drag, trist, șoc, suspicios + coarnele oprite |
| fizică | păr, corp, coarne |
| clipit | din `ParamEyeLOpen/ROpen` |
| privire | `ParamEyeBallX/Y` — irisul alunecă pe sub geană |

## Ce încă NU e în pachet

- **Ochii refăcuți din piese separate** (regula nouă) — sunt construiți și verificați ca piese
  (`vtuber/rig/eyes/`), dar nu sunt încă integrați în `.moc3`. Modelul de aici are ochiul
  dintr-o singură bucată (varianta veche, testată).
- Hotkey-urile pentru stările AI (smirk/anger/shock/hype) — vin la Faza 4.

## Dacă nu se încarcă — ce să-mi trimiți

Textul exact al erorii din VTS (apare în colț jos, roșu) și, dacă se poate, un screenshot.
Fără textul erorii nu pot distinge între: `.moc3` respins, textură lipsă, JSON invalid.
