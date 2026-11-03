# Faza 4 — pachetul VTS (ce e în el și de ce)

Generat de `vtuber/rig_moc3.py`. Toate fișierele sunt în `vtuber/rig/`, iar pachetul de
pus în VTS e `izentric-vts.zip` (1,8 MB).

| fișier | rol |
|---|---|
| `izentric.moc3` | modelul: 13 art mesh-uri, 18 parametri, 1060 keyform-uri |
| `texture_00.png` | atlas 4096², cu bordură de 2 px pe fiecare tile |
| `izentric.model3.json` | referințe + `Groups` (LipSync, EyeBlink) + `HitAreas` |
| `izentric.physics3.json` | 2 setări: păr (AngleX/AngleZ → HairSwayX) și corp (AngleZ → BodyAngleZ) |
| `izentric.cdi3.json` | 6 grupuri de parametri (Față, Ochi, Gură, Corp, Păr, Accesorii, Expresii) |
| `izentric.*.exp3.json` | 5 stări (Râs, Îndrăgostit, Trist, Șocat, Suspicios) + comutatorul de coarne |
| `izentric.vtube.json` | setările VTS: mapările de tracking + 7 hotkey-uri |

## Comutatorul de coarne (mecanism copiat din modelele de referință)

VTS **nu** are hotkey de tip „schimbă parametrul": enumul oficial `HotkeyAction`
(`Files/HotkeyAction.cs`) are `ToggleExpression = 2`, `RemoveAllExpressions = 3`,
`ToggleItemScene = 13`, `ExecuteItemAction = 15` etc., dar nimic pentru parametri.
Calea oficială — și ce folosesc ambele modele de referință („SaturnRing Vis",
„LittleDragon Vis", „머리안경") — e **expresia-toggle**:

1. art mesh-ul `horns` are opacitatea legată de `ParamHornsVis` (0 → coarnele dispar);
2. `izentric.hornsoff.exp3.json` scrie `ParamHornsVis = 0` cu `Overwrite`, fade 0,15 s;
3. hotkey-ul „Coarne ascunse" e de tip `ToggleExpression` pe fișierul de mai sus.

Apăsat o dată → coarnele dispar; apăsat din nou → expresia se oprește, parametrul revine la
valoarea implicită (1) și coarnele apar la loc. Zero plugin-uri, zero cod.

## Ce am reparat la pachet în faza asta

- **Locul coarnelor rămânea gol** (se vedea fundalul prin păr). Acum:
  1. masca prinde și umbra conturului (94, 5, 3), nu doar roșul aprins:
     `r > 50 & r > g·1,6 & r > b·1,6 & g < 160 & a > 40`;
  2. gaura se umple cu **potrivire de textură**: pentru fiecare corn se caută offset-ul
     (pas 4 px) care seamănă cel mai bine pe inelul din jurul găurii, cu condiția ca sursa
     să fie păr și să aibă luminozitate apropiată (nu se amestecă părul alb cu cel negru),
     apoi bucata se copiază și cusătura se estompează pe 2 px.
  Rezultat: 0 pixeli roșii rămași în `head`, `verificare-coarne.png`.
- **Inelul alb din jurul ochilor** — stratul `eye_L/R` avea 14 px de alb vopsit în jurul
  desenului, ca să acopere alunecarea globului. Se vedea ca margine peste geană și obraz.
  Acum globul = exact desenul; în urmă rămâne albul reconstruit din `head`, deci la privirea
  maximă (±11 px) nu apare nici gol, nici piele (test automat + randare la 9 poziții).
- **Bleeding între tile-uri în atlas** — fiecare tile are acum 2 px de bordură care repetă
  marginea, altfel bilingărul lua pixeli din stratul vecin (halou colorat pe contur).
