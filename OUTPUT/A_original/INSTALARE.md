# iZentric — instalare în VTube Studio

**Varianta 2048** — textura e 2048×2048 (16 MB în VRAM), nu 4096. Varianta 4096 a
crăpat VTS pe PC-ul tău; asta e exact ce recomandă mesajul de eroare.

## Pași

1. Copiază folderul în:
   `...\steamapps\common\VTube Studio\VTube Studio_Data\StreamingAssets\Live2DModels\iZentric\`
2. `izentric.model3.json` trebuie să fie **direct** în `iZentric\`.
3. Pornește VTS → *Change model* → **iZentric**.

## Dacă tot crashează la încărcare

Atunci nu textura e cauza, ci fișierul `.moc3` (e scris de mine, nu de Cubism).
Spune-mi și trec pe planul B: PSD pe straturi + export din Cubism la tine.
