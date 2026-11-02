# vtuber/ — VTuberul pentru canalul iZentric

Ce e aici:

| fișier | rol |
| --- | --- |
| `README.md` | ce soft alegi, setări, OBS, checklist |
| `vts_bridge.py` | pornește o animație în VTube Studio când monitorul vede un clip nou |
| `test_vts_bridge.py` | 6 teste, rulate pe un server VTube Studio fals |
| `model/` | pui aici `Pachan_1.1` dezarhivat (ignorat de git) |

## 1. Verdict: ce model ai (confirmat)

| fișier din Drive | ce e | consecință |
| --- | --- | --- |
| `Pachan_1.1.rar` (3,5 MB) | model **2D Live2D half-body** gratis de la medwokl2d (art: koahri1), publicat pe BOOTH ca „Half-Body Model, VTube Studio (FREE)” | **VTube Studio e softul corect.** Nu Warudo, nu VNyan — alea sunt pentru modele 3D |
| `mini (1).7z` (122,7 MB) | [presupus] veadotube mini (aplicația PNGtuber; build-ul Windows x64 are ~106 MB) | setup-ul actual = 2 imagini comutate de microfon, fără tracking de față |

Diferența reală la trecerea pe VTS: capul, ochii, sprâncenele și gura urmăresc fața ta, nu doar „gură deschisă / închisă”. Asta se vede imediat pe ecran.

**Licență — citește înainte să crești canalul:** modelul cere **credit obligatoriu** (rigger + artist) și permite doar **personal use**; interzice redistribuirea și declararea lui ca al tău. „Personal use” nu acoperă explicit un canal monetizat, deci înainte de monetizare scrie-i lui medwokl2d pe BOOTH sau comandă-ți un model propriu. Credit de pus în descriere: `Model: Pachan 1.1 — art @koahri1, rig @MedL2D`.

Dacă mai târziu schimbi modelul: `*.moc3` + `*.model3.json` → 2D Live2D → VTube Studio; `*.vrm` → 3D → VNyan/Warudo; doar `*.png`/`*.webp` → PNGtuber. VTube Studio nu deschide VRM.

## 2. VTube Studio + webcam (calea pentru model 2D)

1. Steam → VTube Studio (gratuit; watermark-ul dispare cu DLC plătit).
2. Încarcă modelul → `Settings` → **API**: pornește serverul de plugin-uri (port implicit **8001**) și permite plugin-urile. Fără asta, bridge-ul de la punctul 4 nu se poate conecta.
3. Webcam, în ordinea importanței: lumină difuză în față, fără fereastră/bec în spate, cameră la nivelul ochilor, 50–80 cm, 30 fps. Închide Zoom/Teams/Discord video înainte — fură camera.
4. Calibrează pe față neutră, pune smoothing cât să nu tremure, apoi fă-ți 3–5 hotkeys/expresii pentru reacții (râs, surprins, ridicat sprâncene). Notează numele exact al hotkey-urilor din fereastra `Hotkeys` — Pachan are setul lui, iar același nume intră în `VTS_HOTKEY` la punctul 4.

Calitatea tracking-ului, după producător: **iPhone > webcam > Android**.

## 3. OBS: avatar cu fundal transparent

- În VTS: `Background` → `Color Picker` → pornește **Transparent (OBS)**.
- În OBS: `Sources` → `+` → **Game Capture** → *Capture specific window* → VTube Studio → bifează **Allow Transparency**. Window Capture nu trece canalul alfa, deci nu îl folosi.
- Alternativă cu load mai mic: Spout2 (plugin `obs-spout2`, apoi `Settings → Spout2 → Enable` în VTS). Dacă marginile modelului arată urât, revino la Game Capture.

## 4. Bridge: reacție automată când apare un clip nou

Ia `data/latest.json` produs de `monitor.py` și pornește un hotkey în VTube Studio:

```
pip install -r vtuber/requirements.txt
python vtuber/vts_bridge.py
```

- `VTS_HOTKEY` — numele exact al hotkey-ului din VTS (implicit `Surprised`).
- `VTS_URL` — implicit `ws://127.0.0.1:8001`.
- Prima rulare doar memorează ce e deja în `latest.json` și nu declanșează nimic. După aceea, la fiecare rulare pornește hotkey-ul o dată pentru fiecare clip nou de pe cele 4 canale monitorizate.
- Token-ul de plugin se salvează în `vtuber/token.json`. Dacă ștergi plugin-ul din VTS, scriptul cere singur alt token.
- Verificat: `python -m pytest vtuber -q` → 6 teste pe un server VTS fals (autentificare, token expirat, hotkey, eroare VTS, VTS oprit, prima rulare).

## 5. Compoziție care ține omul pe video (Minecraft, video editate)

- Avatar 15–20% din înălțimea cadrului, colț dreapta-jos; niciodată peste hotbar, inventar sau minimap.
- O reacție clară la 60–90 de secunde (hotkey/expresie tăiată la 0.3–0.8 s la montaj), nu continuu.
- Primele 15 secunde: hook + avatarul deja pe ecran. Fără intro de 20 de secunde.
- Avatarul nemișcat se vede ca lag: calibrare pe față neutră, dar lasă respirația/micile mișcări active.

## 6. Checklist înainte de înregistrare

1. VTS pornește cu modelul corect, tracking activ.
2. `Transparent (OBS)` pornit + **Allow Transparency** în OBS → fără dreptunghi negru sau verde.
3. Avatarul nu acoperă UI-ul jocului.
4. Hotkeys/expresiile testate (bridge sau taste).
5. API pornit pe 8001, dacă rulezi bridge-ul.
6. Lumină în față, cameră la nivelul ochilor, Zoom/Teams închise.
7. Microfonul se aude în căști; OBS arată nivelul lui, nu doar al jocului.
8. Înregistrare 1080p60, encoder pe GPU (NVENC/QuickSync), 2 piste audio separate (joc + microfon) pentru montaj.
9. O reacție la fiecare 60–90 s, în montaj.
10. Prima secundă din video e cea mai bună — fără intro.

## Ce rămâne neverificat

- Conținutul arhivelor (rar/7z) nu poate fi deschis din sandbox — Drive îmi dă doar metadate, iar descărcarea binară nu trece prin sandbox. Verdictul din secțiunea 1 vine din pagina BOOTH a modelului și din dimensiunile fișierelor.
- `mini.7z` = veadotube mini rămâne [presupus] (nume + 122,7 MB vs ~106 MB build-ul oficial).
- Ce expressions/hotkeys are exact Pachan 1.1 se vede abia la prima încărcare în VTS.
- Bridge-ul e testat pe un server VTS fals, nu pe VTube Studio real (aici nu rulează Windows/OBS). Prima rulare reală o confirmi tu.
- Tracking pe iPhone/Android nu e acoperit; e opțiunea următoare dacă webcam-ul nu e suficient.
