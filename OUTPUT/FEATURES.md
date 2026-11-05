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
| Privire (iris care se mișcă) | da | da, ±3 px — în varianta cu privire | idem |
| Animație de repaus | da (`Scene1.motion3.json`) | da (`izentric.idle.motion3.json`, buclă 5 s) | legată în `.vtube.json` |
| Icon model | da | da (`icon.png`) | în pachet |
| Hotkey-uri | da | da (7: expresii + șterge expresii) | `izentric.vtube.json` |
| Hit areas (Head/Body) | da | da | `HitAreaHead`, `HitAreaBody` |

## Ce NU are (și de ce)
- **Item-uri / accesorii trase cu mouse-ul** — cer artă separată per item; nu inventez desen.
- **Mișcări (motion) pentru expresii** — ar cere fișiere `.motion3.json` per expresie.
- **Privire mare (±10 px)** — irisul e în stratul ochiului; la deplasări mari s-ar vedea
  geana alunecând. Se poate face cu iris separat, dar atunci un ochi poate rămâne gol
  dacă stratul nu se desenează (exact defectul raportat).
