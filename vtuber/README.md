# vtuber/ — VTuberul pentru canalul iZentric

Ce e aici:

| fișier | rol |
| --- | --- |
| `assets/` | **personajul tău**, 9 stări PNG 1024×1024 cu transparență (idle, blink, talking, talking_blink, laugh, love, sad, shocked, sus) |
| `pngtuber.py` | **overlay-ul propriu-zis**: arată personajul în OBS și îl schimbă automat după voce și după față |
| `states.izentric.json` | stările, pragurile, timpii de reacție, animația de balans |
| `facesource.py` | citirea expresiilor din cameră (MediaPipe → `jawOpen`, `mouthSmile`, `browInnerUp`) |
| `ASSETS.md` | ce am măsurat în pozele tale și ce lipsește ca să devină model Live2D |
| `README.md` | pornire, OBS, reacții, checklist |
| `vts.py` | conexiunea + autentificarea la API-ul VTube Studio (folosită de ambele scripturi) |
| `face_reactions.py` | pornește expresii când faci anumite fețe (zâmbet, surprindere, cu ochiul, cap înclinat) |
| `reactions.json` | regulile „față → expresie” |
| `vts_bridge.py` | pornește o animație în VTube Studio când monitorul vede un clip nou |
| `model_tool.py` | inspectează un model Live2D și îl instalează în folderul VTube Studio |
| `doctor.py` | verifică tot lanțul într-o comandă: model, tracker, expresii, reguli, monitor |
| `CHARACTER.md` | specificațiile caracterului (straturi, parametri, expresii, pachetul de reacții) pentru rigger |
| `reactions.dog.json` | pachetul de reacții `laugh / panic / bruh / angry`, gata de copiat în `reactions.json` la modelul nou |
| `test_pngtuber.py` | 11 teste pe motorul de stări și pe compunerea cadrelor (fade, punch, balans) |
| `test_vts_bridge.py`, `test_face_reactions.py`, `test_model_tool.py`, `test_doctor.py` | 25 teste, rulate pe un server VTube Studio fals și pe modele de test |
| `models/` | modelele descărcate local (ignorat de git) |

## 0. Pornirea rapidă — personajul tău, gata de live

Pozele tale (9 stări, 1024×1024, fundal transparent) sunt în `vtuber/assets/`. Overlay-ul le ține într-o fereastră fără margini, mereu deasupra, cu fundal verde pentru chroma key în OBS.

```
pip install -r vtuber/requirements.txt
python vtuber/pngtuber.py --check          # verifică pozele și configul (1 secundă)
python vtuber/pngtuber.py --calibrate      # o dată: cât de tare trebuie să vorbești ca să pornească `talking`
python vtuber/pngtuber.py --mic --face     # pornește avatarul
```

Ce face singur:

| situație | ce se vede | cum e detectat |
| --- | --- | --- |
| tăcere | `idle` + clipit la 2,5–6 s | microfon sub prag |
| vorbești | `talking`, clipește în `talking_blink` | nivel RMS peste prag, cu 0,22 s prelungire după ultimul sunet |
| râzi (zâmbet + gură deschisă + ochi strânși) | `laugh` | 1,6 s, apoi pauză 3 s |
| gura căscată + sprâncene sus | `shocked` | 1,2 s, prioritare peste toate |
| sprâncene ridicate, fără zâmbet | `sad` | 1,5 s |
| zâmbet doar pe o parte | `sus` | 1,2 s |

Taste (fereastra trebuie să aibă focus): `1` laugh, `2` love, `3` sad, `4` shocked, `5` sus, `0` idle. `Esc` închide. Poziția se salvează în `vtuber/overlay.json`; o muți trăgând de imagine.

Tranzițiile nu sunt tăieturi: 90 ms de fade, un „punch” de 3% la reacții și un balans de ±3 px la respirație — exact lucrurile care fac diferența între „poze comutate” și avatar viu.

### OBS

1. `Sources` → `+` → **Window Capture** → fereastra `iZentric`.
2. Click dreapta pe sursă → `Filters` → `+` → **Chroma Key** → `Key Color` = verde (`00FF00`); dacă marginile rămân murdare, urcă `Similarity` la ~400.
3. Altă culoare de fundal: `--bg ff00ff` (magenta) și aceeași culoare în Chroma Key.
4. Mărime: `--height 900` pentru avatar mai mare, apoi `Ctrl+S` pe sursă ca să păstrezi transformarea.

Alternativa fără chroma key (fundal cu adevărat transparent) cere `-transparentcolor` pe Windows și nu e stabilă pe toate plăcile video; chroma key-ul e metoda care nu te lasă în off la live.

## 1. Dacă treci pe Live2D: ce model ai (informativ)

| fișier din Drive | ce e | consecință |
| --- | --- | --- |
| `Pachan_1.1.rar` (3,5 MB) | model **2D Live2D half-body** gratis de la medwokl2d (art: koahri1), publicat pe BOOTH ca „Half-Body Model, VTube Studio (FREE)” | **VTube Studio e softul corect.** Nu Warudo, nu VNyan — alea sunt pentru modele 3D |

Secțiunea asta rămâne valabilă abia când personajul există ca **straturi separate** (ochi, pleoape, gură, sprâncene, păr) — atunci se righează în Live2D și VTube Studio îl mișcă pe parametri. Pozele actuale sunt aplatizate, deci varianta de azi e overlay-ul din secțiunea 0; diferența o explică `ASSETS.md`.

**Licență — citește înainte să crești canalul:** modelul cere **credit obligatoriu** (rigger + artist) și permite doar **personal use**; interzice redistribuirea și declararea lui ca al tău. „Personal use” nu acoperă explicit un canal monetizat, deci înainte de monetizare scrie-i lui medwokl2d pe BOOTH sau comandă-ți un model propriu. Credit de pus în descriere: `Model: Pachan 1.1 — art @koahri1, rig @MedL2D`.

Dacă mai târziu schimbi modelul: `*.moc3` + `*.model3.json` → 2D Live2D → VTube Studio; `*.vrm` → 3D → VNyan/Warudo; doar `*.png`/`*.webp` → PNGtuber. VTube Studio nu deschide VRM.

### De ce VTube Studio și nu altceva

| program | formate | ce are / ce lipsește |
| --- | --- | --- |
| **VTube Studio** | 2D Live2D | singurul care deschide Pachan; webcam + iPhone (ARKit) + NVIDIA Broadcast + Mediapipe + Android; API public cu expresii, hotkeys, parametri — pe asta se sprijină `face_reactions.py` |
| VNyan | 3D VRM | foarte bun pentru 3D: automatizări de stream, scene, trigger-uri; nu deschide Live2D |
| Warudo | 3D VRM | scenă 3D, hand/full-body tracking; cere GPU decentă; nu deschide Live2D |
| VSeeFace | 3D VRM | gratuit și simplu, dar fără API de expresii; nu deschide Live2D |

Concluzia: pentru un model Live2D, VTube Studio nu e „o variantă”, e singura variantă serioasă. Alternativele devin relevante doar dacă treci pe model 3D.

### Există ceva mai bun? (verificat pe GitHub, noiembrie 2026)

| soft | sursă | 2D Live2D (`.moc3`) | API pentru automatizări | verdict |
| --- | --- | --- | --- | --- |
| **VTube Studio** | closed source, Steam | da | **da** (API public: expresii, hotkeys, parametri) | **ales** — singurul unde merge `face_reactions.py` |
| [open-vt](https://github.com/erodozer/open-vt) | MIT, ★307, activ (push oct. 2026) | da, prin runtime-ul Ayagami | **nu** — „feature parity cu VTS, excluzând pluginurile” | singura alternativă open-source serioasă; Linux-first, build din sursă, fără API |
| LilacVT | MIT, fork după open-vt, ★2, v0.1.7 | da | nu | experimental, nu pentru producție |
| Inochi2D / Inochi Session | BSD-2 | nu — format propriu (INP) | nu | alt ecosistem, modelul se righează din nou |
| VSeeFace, VNyan, Warudo | gratuite, closed source | nu | parțial (VMC) | doar pentru modele 3D VRM |
| Ayatsuri2D | GPL-3.0 (editor), runtime MIT | exportă `.moc3` | n/a (editor, nu tracker) | de folosit când îți faci model propriu, gratis, în loc de Cubism PRO |

Concluzia pe surse, nu pe impresii: pentru model Live2D + webcam + automatizări pe Windows, **VTube Studio rămâne singura opțiune completă**. open-vt e proiectul de urmărit, dar nu are API de pluginuri, deci reacțiile automate de aici nu ar funcționa în el.

### Modele gratuite bune și legale (instalate de `model_tool.py`)

Modelele oficiale Live2D (repo `Live2D/CubismWebSamples`) sunt complete: moc3 + texturi + physics + expresii + motion-uri. Cele folosibile comercial pentru un canal mic:

| model | expresii | ce e | licență |
| --- | --- | --- | --- |
| **Mao Niziiro** (`Mao`, 4,2 MB) | 8 (zâmbet, ochi scânteietori, supărat, blush, smug) | jumătate de corp, physics, 8 motion-uri | **Live2D Original Character** → uz comercial permis persoanelor fizice / firmelor mici + text de credit |
| `Haru`, `Hiyori`, `Mark`, `Ren`, `Rice`, `Wanko` | 8 / 0 / 0 / … | tot personaje Live2D originale | la fel ca Mao; Hiyori nu permite modificarea designului |
| `Natori` | 11, cu nume clare (`Smile`, `Surprised`, `Angry`, `Sad`) | cel mai expresiv | **Collaboration Character → NU se folosește comercial** |

Instalare (descarcă din repo-ul oficial, validează fișierele, copiază în folderul VTube Studio):

```
python vtuber/model_tool.py install --github Mao
python vtuber/model_tool.py inspect vtuber/models/Mao      # ce expresii are, ce parametri atinge fiecare
python vtuber/model_tool.py install C:\Downloads\Model --target "C:\...\Live2DModels"
```

Pe Windows `--target` se poate omite: scriptul caută singur folderul `Live2DModels` din `AppData\LocalLow\DenchiSoft\VTubeStudio`. Marca de copyright obligatorie la utilizarea personajelor Live2D originale, în descrierea video:

> This content uses sample data owned and copyrighted by Live2D Inc. The sample data are utilized in accordance with terms and conditions set by Live2D Inc. This content itself is created at the author's sole discretion.

Modelul Pachan rămâne o opțiune (e frumos și e deja la tine), dar licența lui e „personal use” — pentru monetizare, Mao/Haru sunt varianta curată până îți comanzi un model propriu.

## 2. VTube Studio + webcam (calea pentru model 2D)

1. Steam → VTube Studio (gratuit; watermark-ul dispare cu DLC plătit).
2. Încarcă modelul → `Settings` → **API**: pornește serverul de plugin-uri (port implicit **8001**) și permite plugin-urile. Fără asta, bridge-ul de la punctul 4 nu se poate conecta.
3. Webcam, în ordinea importanței: lumină difuză în față, fără fereastră/bec în spate, cameră la nivelul ochilor, 50–80 cm, 30 fps. Închide Zoom/Teams/Discord video înainte — fură camera.
4. **Trackerul face diferența la nivel de față.** Butonul **Tracking Quality** → alege **„[Google] Mediapipe Tracker”** (Windows, fără GPU special): prinde sprâncenele separat, gura și ochii mai bine decât trackerul implicit (OpenSeeFace), plus hand tracking. Alternativă: trackerul NVIDIA (dacă ai placă NVIDIA). După prima pornire calibrează o dată pe față neutră, cu privirea în cameră.
5. Pune smoothing cât să nu tremure și verifică pe rând fiecare expresie cu `face_reactions.py`.

Calitatea tracking-ului, după producător: **iPhone (ARKit) > webcam cu Mediapipe/NVIDIA > webcam implicit > Android**. Dacă vrei saltul „ca la VTuberii mari”, singura investiție care contează e un iPhone folosit ca tracker — restul îl avem deja.

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

## 5. Reacții după față (ca la VTuberii mari)

`face_reactions.py` citește parametrii de tracking din VTube Studio (un request la 0,25 s îi ia pe toți) și pornește/oprește expresii Live2D după reguli:

```
python vtuber/face_reactions.py --list     # ce expresii (.exp3.json) are modelul încărcat
python vtuber/face_reactions.py            # pornește motorul; Ctrl+C îl oprește
```

`reactions.json` e calibrabil pentru **Mao**: zâmbet → `exp_02` (ochi închiși de zâmbet), gură deschisă + sprâncene sus → `exp_04` (scânteie), sprâncene încruntate → `exp_05` (supărat), cu ochiul → `exp_08` (smug). Pentru alt model: rulezi `--list`, iei numele fișierelor de expresie, le pui în `vtuber/reactions.json`, rulezi din nou. Regulile care nu găsesc fișierul în model sunt sărite cu un avertisment, nu crapă.

O regulă arată așa:

| câmp | sens |
| --- | --- |
| `when` | condiții pe parametri de tracking: `{"MouthSmile": {"min": 0.5}}` = „zâmbet peste 0,5”; poți combina mai mulți parametri |
| `holdSeconds` | cât stă pornită expresia, chiar dacă fața se schimbă |
| `cooldownSeconds` | pauză până poate fi declanșată din nou (anti-spam) |

Parametri utili **pe webcam** (restul sunt doar pe iPhone): `MouthOpen`, `MouthSmile`, `Brows`, `BrowLeftY`, `BrowRightY`, `EyeOpenLeft`, `EyeOpenRight`, `EyeLeftX/Y`, `EyeRightX/Y`, `FaceAngleX/Y/Z`, `FacePositionX/Y/Z`, `VoiceVolume`. **Nu** funcționează pe webcam: `TongueOut`, `CheekPuff`, `FaceAngry`, `MouthX` — nu construi reguli pe ele.

Pentru „reacționează când vorbesc”: lasă lip-sync-ul din VTube Studio pe microfon (sau pe `MouthOpen`) și, dacă vrei o expresie separată de „vorbesc”, adaugi o regulă pe `VoiceVolume`, de exemplu `{"name": "talk", "expressionFile": "talk.exp3.json", "when": {"VoiceVolume": {"min": 0.3}}, "holdSeconds": 0.6, "cooldownSeconds": 0.3}`.

Calibrare: pornește cu praguri la 0,5 și ajustează după 2 minute de teste — dacă se declanșează prea des, urcă pragul; dacă nu prinde, coboară-l. Cine vrea mai mult: modelul trebuie să aibă expresii bune (rigger-ul le face), softul doar le pornește.

### Ordinea de pornire (3 comenzi)

```
python vtuber/model_tool.py install --github Mao   # o dată: instalează modelul în VTube Studio
python vtuber/doctor.py                            # înainte de fiecare sesiune: ce e în neregulă
python vtuber/face_reactions.py                    # cât timp înregistrezi: reacții după față
```

`doctor.py` tipărește exact ce nu merge (fără model, trackerul nu vede fața, lipsesc parametri de tracking, regulile nu se potrivesc cu expresiile modelului) și întoarce cod de ieșire 1 dacă nu ești gata de înregistrare.

## 6. Compoziție care ține omul pe video (Minecraft, video editate)

- Avatar 15–20% din înălțimea cadrului, colț dreapta-jos; niciodată peste hotbar, inventar sau minimap.
- O reacție clară la 60–90 de secunde (hotkey/expresie tăiată la 0.3–0.8 s la montaj), nu continuu.
- Primele 15 secunde: hook + avatarul deja pe ecran. Fără intro de 20 de secunde.
- Avatarul nemișcat se vede ca lag: calibrare pe față neutră, dar lasă respirația/micile mișcări active.

## 7. Checklist înainte de înregistrare

1. `python vtuber/doctor.py` spune „gata de înregistrare”.
2. `Transparent (OBS)` pornit + **Allow Transparency** în OBS → fără dreptunghi negru sau verde.
3. Avatarul nu acoperă UI-ul jocului.
4. Hotkeys/expresiile testate: fiecare față din `reactions.json` trece o dată prin `face_reactions.py`.
5. API pornit pe 8001, dacă rulezi bridge-ul.
6. Lumină în față, cameră la nivelul ochilor, Zoom/Teams închise.
7. Microfonul se aude în căști; OBS arată nivelul lui, nu doar al jocului.
8. Înregistrare 1080p60, encoder pe GPU (NVENC/QuickSync), 2 piste audio separate (joc + microfon) pentru montaj.
9. O reacție la fiecare 60–90 s, în montaj.
10. Prima secundă din video e cea mai bună — fără intro.

## Ce rămâne neverificat

- Conținutul arhivelor (rar/7z) nu poate fi deschis din sandbox — Drive îmi dă doar metadate, iar descărcarea binară nu trece prin sandbox. Verdictul din secțiunea 1 vine din pagina BOOTH a modelului și din dimensiunile fișierelor.
- Pozele din `assets/` sunt măsurate în `ASSETS.md` (canvas, ancoră, diferențe între stări). Ce nu se poate afla din ele: cum au fost desenate și dacă mai există sursa pe straturi.
- Overlay-ul e testat pe logică și pe cadre compuse, nu cu fereastră reală, cameră și microfon (sandbox fără GUI). Prima pornire pe PC-ul tău e testul adevărat; `--check` și `--mic` separat izolează orice problemă.
- Ce expressions/hotkeys are exact Pachan 1.1 se vede abia la prima încărcare în VTS.
- Scripturile sunt testate pe un server VTS fals, nu pe VTube Studio real (aici nu rulează Windows/OBS/webcam). Instalarea de model e testată real, dar într-un folder temporar, nu în VTS. Prima rulare reală o confirmi tu.
- Trackerul Mediapipe/NVIDIA nu poate fi testat aici (fără cameră); recomandarea vine din documentația VTS.
- `doctor.py` a fost rulat doar pe un server VTS fals; pe VTube Studio real îți spune el ce lipsește la prima rulare.
- Pragurile din `reactions.json` (0,5 / 0,6 / 0,2 / 15°) sunt valori de start, nu calibrate pe fața ta — se ajustează în 2 minute de teste.
- Numele fișierelor de expresie din `reactions.json` sunt exemple: modelul Pachan are propriile `.exp3.json`, le vezi cu `--list`.
- Tracking pe iPhone/Android nu e acoperit; e opțiunea următoare dacă webcam-ul nu e suficient.
