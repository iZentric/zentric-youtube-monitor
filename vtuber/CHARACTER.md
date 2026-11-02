# Caracterul VTuber — specificații pentru rigger + pachet de reacții

**Ce pot și ce nu pot analiza eu:** `youtube.com` e blocat din sandbox, deci **nu pot vedea** clipurile sau avatarul folosit de Sky / INSANITY. Ce e mai jos nu e „ce are avatarul lui”, ci **specificația minimă ca să obții același efect** cu un cățel propriu, plus reacțiile transformate în configurări concrete pentru VTube Studio și pentru `face_reactions.py`.

Context verificat: Sky = canalul **Jocuri Horror** (`UC7Tmdxj18fdu4tTtxVUhoCA`, ~1,1M abonați, 2,3K clipuri) — deja e primul canal din `monitor.py`. INSANITY = `@QSanityx`.

> **Nu copia personajul lui.** Desen propriu, în același registru (cățel antropomorf, linii groase, culori saturate). Personajul altcuiva e risc de copyright și de „model furat”, care se vede imediat în comunitate.

## 1. Nivelul de avatar și ce cumperi cu el

| nivel | ce e | ce simte spectatorul | efort |
| --- | --- | --- | --- |
| PNGtuber | 2-3 imagini (gură închisă / deschisă / ochi închiși), comutate de microfon | „vorbește”, dar fața e rigidă | 1 zi de desen |
| **Live2D half-body** | model cu parametri: cap, ochi, sprâncene, gură, urechi cu fizică | reacții reale la fața ta, urechile se mișcă inerțial | desen + rigging (2-6 săptămâni de muncă sau comandă) |
| Live2D + ARKit (perfect sync) | model cu blend shapes pentru iPhone | „ca VTuberii mari”: sprâncene separate, obraji, limbă | rigging avansat; are sens doar cu iPhone ca tracker |

Pentru canalul tău (webcam, video editate) nivelul 2 e ținta corectă. Nivelul 3 doar dacă faci pasul cu iPhone-ul.

## 2. Ce trebuie să conțină modelul (brief pentru artist + rigger)

**Straturi obligatorii** (fiecare separat, cu 5-10 px de „bleed” în afara conturului, altfel apar goluri când întoarce capul):

```
cap + gât, trup (hanorac), mâini sus/jos (opțional)
ureche stânga: bază + vârf (2 straturi, pentru fizică)
ureche dreapta: bază + vârf
sprânceană stânga / dreapta
pleoapă superioară stg/dr, pleoapă inferioară stg/dr
scleră, iris, pupilă, 2-3 reflexii (highlights)
bot + nas, dinți sus, dinți jos, limbă, cavitate bucală
accesorii: căști / șapcă (strat separat, ca să poți face toggle)
```

**Parametri Live2D — folosește ID-urile standard**, altfel VTube Studio nu poate face Auto-Setup și trebuie mapat manual fiecare:

| intrare VTS | parametru Live2D | de ce contează |
| --- | --- | --- |
| FaceAngleX/Y/Z | `ParamAngleX/Y/Z` | capul urmărește fața |
| EyeOpenLeft/Right | `ParamEyeLOpen`, `ParamEyeROpen` | clipit + cu ochiul |
| MouthOpen | `ParamMouthOpenY` | lip-sync |
| MouthSmile | `ParamMouthForm` | zâmbet / expresivitate |
| Brows, BrowLeftY/RightY | `ParamBrowLY/RY`, `ParamBrowLForm/RForm` | surprindere, furie |
| — | `ParamBreath`, `ParamBodyAngleX` | respirație, nu pare mort |
| — | `ParamCheek` | blush (bonus) |

**Fizică** obligatorie pe: vârfurile urechilor, șnururile hanoracului, moțul de blană. Fără ea, modelul arată ca un sticker.

**Expresii** = fișiere `.exp3.json`, exact ce poate porni `face_reactions.py`:

| fișier | ce face | parametri atinși |
| --- | --- | --- |
| `laugh.exp3.json` | râs, ochii închiși de zâmbet | `ParamEyeLOpen/ROpen` 0, `ParamEyeLSmile/RSmile` 1, `ParamMouthForm` 1 |
| `panic.exp3.json` | sperietură | `ParamEyeLOpen/ROpen` 1.2, `ParamBrowLY/RY` 1, `ParamMouthOpenY` 1 |
| `bruh.exp3.json` | confuzie (un ochi mic, gura strâmbă) | `ParamEyeLOpen` 0.4 / `ParamEyeROpen` 1, `ParamMouthForm` -0.6 |
| `angry.exp3.json` | furie comică | `ParamBrowLAngle/RAngle` -1, `ParamMouthForm` -1, `ParamCheek` 0.5 |
| `cry.exp3.json` | plâns dramatizat | `ParamEyeLOpen/ROpen` 0.2, `ParamBrowLForm/RForm` -1, lacrimi ca item |
| `hype.exp3.json` | victorie | ochi cu scânteie (item peste ochi), `ParamMouthForm` 1, urechi sus |

## 3. Pachetul de reacții (ce pui în VTuber, nu în montaj)

Coloana „declanșator” e ce se poate automatiza; restul sunt taste apăsate de tine în timpul jocului (hotkeys în VTube Studio) — așa face toată lumea, pentru că o reacție trebuie să pornească în 100 ms, nu după ce o detectează un script.

| reacție | declanșator | expresie | hold / cooldown | accent la montaj (opțional) |
| --- | --- | --- | --- | --- |
| râs | `MouthSmile ≥ 0.55` (automat) | `laugh` | 1.2 s / 3 s | zoom 130%, fără SFX |
| panică | `MouthOpen ≥ 0.75` + `Brows ≥ 0.5` (automat) sau taste `P` | `panic` | 1.2 s / 4 s | boom + zoom 150% |
| bruh / confuzie | cu ochiul: `EyeOpenLeft ≤ 0.2` + `EyeOpenRight ≥ 0.4` (automat) | `bruh` | 0.8 s / 5 s | record scratch, freeze 0.3 s |
| furie | `Brows ≤ -0.5` + `MouthOpen ≥ 0.3` (automat) | `angry` | 1 s / 8 s | shake 2 px, fără zoom |
| plâns | tastă `C` (manual — webcam-ul nu detectează „trist”) | `cry` | 2 s | muzică tristă 3 s |
| hype / victorie | tastă `V` (manual — e reacție la joc, nu la față) | `hype` | 1.5 s | confetti + whoosh |

Regulile automate, gata de lipit în `vtuber/reactions.json` (înlocuiește conținutul când modelul are fișierele de mai sus):

```json
{
  "rules": [
    {"name": "laugh",  "expressionFile": "laugh.exp3.json",  "when": {"MouthSmile": {"min": 0.55}}, "holdSeconds": 1.2, "cooldownSeconds": 3},
    {"name": "panic",  "expressionFile": "panic.exp3.json",  "when": {"MouthOpen": {"min": 0.75}, "Brows": {"min": 0.5}}, "holdSeconds": 1.2, "cooldownSeconds": 4},
    {"name": "bruh",   "expressionFile": "bruh.exp3.json",   "when": {"EyeOpenLeft": {"max": 0.2}, "EyeOpenRight": {"min": 0.4}}, "holdSeconds": 0.8, "cooldownSeconds": 5},
    {"name": "angry",  "expressionFile": "angry.exp3.json",  "when": {"Brows": {"max": -0.5}, "MouthOpen": {"min": 0.3}}, "holdSeconds": 1.0, "cooldownSeconds": 8}
  ]
}
```

Pragurile sunt valori de start: rulezi `python vtuber/doctor.py`, apoi `face_reactions.py` și ajustezi după 2 minute de teste reale (dacă „panic” pornește prea des, urcă `MouthOpen` la 0.85).

**Ce NU se pune în VTuber** (rămâne la montaj): zoom-urile, boom/whoosh/record scratch, tăieturile, muzica. Programul de VTuber are grijă doar de față, gură și fizică.

## 4. Cum arată lucrul în practică (ordinea corectă)

1. Desen + rigging → primești folderul modelului (`*.model3.json`, `*.moc3`, texturi, `*.exp3.json`).
2. `python vtuber/model_tool.py install <folder>` → îl pune în VTube Studio.
3. În VTS: Auto-Setup, apoi legi tastele pentru `cry`/`hype` și verifici că expresiile pornesc.
4. `python vtuber/doctor.py` → trebuie să zică „gata de înregistrare”.
5. `python vtuber/face_reactions.py` → reacțiile automate merg cât înregistrezi.

## 5. Brief scurt pentru rigger (copy-paste)

> Model Live2D half-body, personaj original: cățel antropomorf, linii de contur groase, culori saturate, hanorac + căști.
> Cer: parametri cu ID-uri standard Live2D (`ParamAngleX/Y/Z`, `ParamEyeLOpen/ROpen`, `ParamBrowLY/RY`, `ParamMouthOpenY`, `ParamMouthForm`, `ParamBreath`, `ParamBodyAngleX`), fizică pe urechi (2 segmente), șnururi și moț, 6 expresii `.exp3.json` (`laugh`, `panic`, `bruh`, `angry`, `cry`, `hype`), export `.moc3` SDK 4.0+ cu `physics3.json` înregistrat în `model3.json`.
> Dacă se poate: blend shapes ARKit pentru viitor (iPhone), dar prioritar e webcam-ul.
