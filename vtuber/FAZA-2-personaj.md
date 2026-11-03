# Faza 2 — personajul nou vs. matricea de mecanisme

## Ce am, măsurat pe fișiere (nu presupus)

| Ce | Detaliu |
|---|---|
| Desene sursă | 9 PNG 1024×1024: `idle, blink, talking, talking_blink, laugh, love, sad, shocked, sus` |
| Natura desenului | **o singură bucată** — păr + față + corp desenate împreună, fără straturi |
| Straturi derivate deja | 14 în `vtuber/rig/`: `head` (295 281 px opaci, y 37–691), `body` (245 332 px, y 635–1023), `eye_L` (19 018), `eye_R` (17 073), `eyes_closed` (46 026), `mouth_open` (21 420), `expr_{laugh,love,sad,shocked,sus}`, `eye_mask_L/R`, `backing` (gât) |
| Păr | 133 585 px în `head`, y 38–654 — desenat peste față, fără separație breton/lateral/spate |
| PSD / mesh / .cmo3 | ⛔ niciunul |

## Matrice mecanism → am / lipsește

| Mecanism din A∪B | Am? | Ce ar cere |
|---|---|---|
| Unghi cap X/Y/Z (bucată `head`) | ✅ | mesh pe `head` + keyforms |
| Corp X/Y/Z (bucată `body`) | ✅ | mesh pe `body` |
| Clipit (`EyeBlink`) | ✅ | `eyes_closed` peste ochi, opac 100 % |
| Glob ocular X/Y | ✅ | `eye_L/R` alunecă în mască ±3 px |
| Gură deschisă (`MouthOpenY`) | ✅ | `mouth_open` |
| Respirație (`ParamBreath`) | ✅ | scalare fină pe `body` |
| 5 expresii (râs/îndrăgostit/trist/șocat/suspicios) | ✅ | `expr_*` pe opacitate |
| HitAreas cap/corp | ✅ (EXTRA) | declarate în `model3.json` |
| `RemoveAllExpressions` | ✅ | hotkey VTS |
| Fizică păr (șuvițe) | 🟡 | părul e o bucată → pot lega **tot părul** ca un pendul, nu șuvițe |
| Fizică haine/coadă | ⛔ | hainele sunt contopite cu `body` |
| Sprâncene separate (Y / Form) | ⛔ | desenate în `head` |
| Gură fonetică A/I/U/E/O, TongueOut, CheekPuff, Pucker, Funnel, Shrug | ⛔ | există doar „gura deschisă" dintr-o singură formă |
| Blush, lacrimi, sclipiri, ochi inimă, „întunecat", pale, sudoare | 🟡 | parțial în cele 5 expresii desenate; nu ca straturi separate |
| Props: ochelari ×2, gamepad, saturn, dragon | ⛔ | nu există în desenele tale |
| Zone ascunse (sub breton, sub bărbie, sub haine) | ⛔ | desenul nu le conține; la mișcare mare apar goluri |
| Items pinned / tint | 🟡 | structura o copiez, conținutul e al tău |

## Verdict pe cele trei drumuri

- **DRUMUL A (reskin pe mesh-ul A sau B): ⛔ imposibil.** Nu am PSD-ul lor și nici UV-uri potrivite pentru desenul tău; a desena peste mesh-ul altcuiva înseamnă să inventez artă care nu e a ta — contrazice regula „personajul arată ca el".
- **DRUMUL B (PSD → Cubism → export): 🟡 posibil**, dar depinde de Cubism Editor la tine și de ochiul tău la rigging; nu îl propun ca drum principal.
- **DRUMUL C (writer `.moc3` propriu, verificat cu Cubism Core): ✅ recomandat.** Am deja scriitorul acceptat de Core (commit `e2ee731`). Iau straturile tale, construiesc mesh + parametri + fizică + expresii, generez tot pachetul și îl validez cu Core înainte să ți-l dau.

## Ce pot livra 100 % din arta ta, fără niciun pixel inventat

Model care se încarcă în VTube Studio și are: unghi cap X/Y/Z, înclinare corp, clipit, privire ±3 px, gură deschisă (lip sync), respirație, cele 5 expresii, hit areas, fizică de pendul pe cap+păr ca bloc, `RemoveAllExpressions` + hotkeys. Adică **toate mecanismele care nu cer piese noi**.

## Ce NU se poate fără pixeli noi (spus direct)

Sprâncene separate, gura fonetică A/I/U/E/O, blush/lacrimi/sclipiri/ochi inimă, props, fizică pe șuvițe separate, completarea zonelor ascunse. Astea cer desen nou — fie de la tine, fie aprobat de tine ca să-l deriv din desenele tale existente (tăiere pe zone + extindere de culoare, nu artă inventată).
