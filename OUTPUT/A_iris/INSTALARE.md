# iZentric — instalare în VTube Studio (varianta cu iris separat)

**Ce e diferit aici**: irisul e tăiat exact pe elipsa lui și e un strat separat.
Se mișcă **doar irisul**; albul din jur rămâne fundal, nemișcat. Geana și pleoapa
sunt în stratul capului, deci irisul nu poate „ieși" peste ele.

Ce știe modelul:
- cap X/Y/Z, corp, respirație, legănare păr (fizică);
- privire în toate direcțiile (`ParamEyeBallX/Y`, ±6 px de iris);
- clipit (pleoapele acoperă irisul);
- gură din microfon (lip sync) + expresii: râs, îndrăgostit, trist, șocat, suspicios;
- coarne on/off; animație de repaus de 5 s.

Instalare:
1. Închide VTS complet (și din tray).
2. Șterge `...\VTube Studio_Data\StreamingAssets\Live2DModels\iZentric\`.
3. Dezarhivează arhiva acolo → `Live2DModels\iZentric\izentric.model3.json`.
4. VTS → *Change model* → **iZentric**.

Microfon: VTS → Settings → **Microphone** pornit; Windows → Privacy → Microphone →
permite aplicațiilor desktop.

Imagini de control în `../VERIFICARE/` (randate din fișierul `.moc3`, nu din desen):
`iris-priviri.png` (privire stânga/dreapta/sus/jos), `iris-cap.png` (cap întors + clipit),
`iris-fata-de-desen.png` (model vs. desen, în aceeași cadră).
