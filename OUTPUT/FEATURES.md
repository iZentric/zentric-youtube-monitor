# Ce are modelul — comparat cu modelul real de referință (`ellot.moc3`, se încarcă în VTS)

| Funcție | ellot (referință) | iZentric | Dovadă |
|---|---|---|---|
| `.moc3` acceptat de Cubism Core | da | **da** | `python vtuber/check_moc3.py …` → `"ok": true` |
| Textură | 8192 | 2048 (sub limita care dădea crash) | `texture_00.png` 2048×2048 |
| Cap X/Y/Z | da | da (±30°) | `OUTPUT/VERIFICARE/simplu-foaie-cap.png` |
| Corp / respirație | da | da | idem |
| Fizică păr | da | da (`izentric.physics3.json`) | parametru `ParamHairSwayX` |
| Gură din microfon (lip sync) | da | da (`ParamMouthOpenY`, grup `LipSync`) | `foaie-gura.png`, poziția „gură deschisă" |
| Expresii | 10+ | 6 (râs, îndrăgostit, trist, șocat, suspicios, coarne on/off) | `foaie-gura.png` |
| Clipit automat | da | da (grup `EyeBlink`) — în varianta cu privire | `cu-privire-foaie-ochi.png` |
| Privire (iris care se mișcă) | da | da — varianta `A_cu_privire` (±3 px, iris lipit de stratul ochiului) sau `A_iris` (**±6 px, doar irisul se mișcă**) | `iris-priviri.png` |
| Animație de repaus | da (`Scene1.motion3.json`) | da (`izentric.idle.motion3.json`, buclă 5 s) | legată în `.vtube.json` |
| Icon model | da | da (`icon.png`) | în pachet |
| Hotkey-uri | da | da (7: expresii + șterge expresii) | `izentric.vtube.json` |
| Hit areas (Head/Body) | da | da | `HitAreaHead`, `HitAreaBody` |

## Varianta `A_iris` — iris tăiat exact (2026-11-05)

Irisul e decupat **pe elipsa lui** (`iris_L.png`, `iris_R.png`) și e un strat separat, așezat
peste cap. Albul sclerii rămâne în `head.png` ca fundal. Măsurători, nu impresii:

| Verificare | Rezultat |
|---|---|
| pixeli de iris în afara elipsei | 0 (toleranță 40 px pentru anti-alias) |
| marginea irisului (ultimii 10%) | luminanță medie < 190 → fard fără franjuri albe |
| iris rămas în `head.png` | < 2% pixeli albaștri în elipsă (doar umbra de sub geană) |
| deplasare `ParamEyeBallX` −1 → +1 | **12 px** măsurat în `.moc3` |
| sclera/geana în același timp | 0 px mișcați (în afara elipsei irisului) |
| model la repaus vs. desen | < 3% pixeli diferiți în iris |
| bbox iris desen vs. model | ±1 px |

Dovezi: `VERIFICARE/iris-priviri.png`, `iris-cap.png`, `iris-fata-de-desen.png`,
`iris-foaie-ochi.png`. Teste: `vtuber/test_iris_separat.py` (5 teste).

## Ce NU are (și de ce)
- **Item-uri / accesorii trase cu mouse-ul** — cer artă separată per item; nu inventez desen.
- **Mișcări (motion) pentru expresii** — ar cere fișiere `.motion3.json` per expresie.
- **Privire foarte mare (±10 px)** — s-ar vedea o margine albă de câțiva pixeli între iris și
  geană; la ±6 px irisul rămâne complet în sclera. Se poate crește din `IRIS_PX` din
  `vtuber/rig_moc3.py` și reconstrui.
