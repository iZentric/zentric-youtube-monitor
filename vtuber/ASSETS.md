# ASSETS.md — ce e în pozele tale, măsurat

Sursa: cele 9 fișiere urcate pe GitHub (`idle, blink, talking, talking_blink, laugh, love, sad, shocked, sus`), copiate în `vtuber/assets/`. Tot ce e mai jos e măsurat cu Pillow, nu estimat din privire.

## 1. Format — identic la toate

| proprietate | valoare |
| --- | --- |
| dimensiune | **1024 × 1024** la toate 9 |
| mod | **RGBA** (canal alfa real, nu fundal alb) |
| fundal | complet transparent în afara personajului |
| acoperire | 50,3–52,5 % din cadru |
| tăiere | personajul se termină **în marginea de jos** a cadrului (bust, fără picioare) |

Canvasele sunt identice, deci pozele se pot schimba între ele fără să re-poziționezi nimic în OBS.

## 2. Ancoră — personajul nu „sare” la schimbarea stării

Emblema yin-yang de pe hanorac, măsurată ca centru de masă al pixelilor negri din zona toracică:

| stare | centru emblemă (x, y) |
| --- | --- |
| idle / blink / talking / talking_blink | 553,8 / 875,8 |
| laugh | 554,9 / 876,6 |
| love | 554,4 / 876,3 |
| sad | 554,7 / 876,3 |
| shocked | 554,4 / 876,2 |
| sus | 555,1 / 876,7 |

Împrăștiere **sub 1,5 px** la 1024 px. Capul are același vârf la toate (y = 37–39). Altfel spus: pozele au fost generate din aceeași ancoră, deci un fade între ele arată ca o schimbare de expresie, nu ca un salt.

## 3. Ce diferă între stări (și de ce contează)

| stare | lățime cap (y=300) | lățime umeri (y=950) | observație |
| --- | --- | --- | --- |
| idle | 555 | 717 | referință |
| laugh | 544 | **764** | umerii se lățesc cu 47 px, corpul „se umflă” la râs |
| love | **562** | **790** | cea mai lată — inima/efectele ies din siluetă |
| sad | 545 | 738 | capul se lasă, umerii se strâng |
| shocked | 546 | 765 | corp tras în spate |
| sus | 545 | 726 | capul se lasă pe o parte |

Diferența maximă între siluete: **±73 px** la nivelul umerilor (≈7 %). De asta overlay-ul folosește un fade de 90 ms și un „punch” de 3 % la reacții: tăietura brută s-ar vedea ca un tresărire a corpului, fade-ul o citește ca expresivitate.

## 4. Ce ai exact, ca vocabular de stări

| fișier | rol în overlay | declanșator |
| --- | --- | --- |
| `idle.png` | stare de repaus | implicit |
| `blink.png` | clipit din idle | aleator 2,5–6 s |
| `talking.png` | vorbești | microfon peste prag |
| `talking_blink.png` | clipit în timp ce vorbești | combinație din cele două |
| `laugh.png` | râs | zâmbet + gură deschisă + ochi strânși |
| `shocked.png` | șoc | gură căscată + sprâncene sus |
| `sad.png` | tristețe | sprâncene ridicate, fără zâmbet |
| `sus.png` | ironic / „hmm” | zâmbet pe o singură parte |
| `love.png` | dragoste | hotkey `2` (nu are un echivalent facial stabil) |

Asta e exact setul minim de PNGtuber (idle/talk/blink + emoții) — nu-ți lipsește nimic ca să pornești azi.

## 5. Ce lipsește ca să devină model Live2D (nu PNG comutat)

Pozele sunt **aplatizate**: un singur strat per stare. Un model Live2D are nevoie de straturi separate, fiecare cu 5–10 px de „bleed” sub vecin:

- cap/față + gât, trup/hanorac, mâini
- pe fiecare ureche/corn: 2 segmente
- sprâncene stânga/dreapta, pleoape sus/jos, sclera/iris/pupilă/2–3 reflexe
- bot/gură, dinți sus/jos, limbă, cavitatea gurii
- păr (șuvițe separate), accesoriu (căști)

Fără ele nu există `.moc3`, deci nici VTube Studio nu poate mișca capul/ochii pe parametri. Lista completă, cu ID-urile standard de parametri, e în `CHARACTER.md` — aia e tema pentru rigger (sau pentru tine, în Cubism/Ayatsuri2D).

Varianta care deblochează Live2D cel mai repede: **desenezi sau comanzi doar cele 4 straturi de față** (ochi, pleoape, gură, sprâncene) peste corpul deja existent. Restul (păr, cornițe, hanorac) poate rămâne un singur strat, cu fizică pe cornițe.

## 6. Alte fișiere urcate, analizate

| fișier | ce e | util? |
| --- | --- | --- |
| `izentric_emote_pack.zip` | 6 emoții 1024×1024 **RGB, fără alfa** + preview | pentru emote-uri pe Discord/YouTube, **nu** pentru overlay (fără transparență) |
| `izentric_fara_fundal.zip` | aceleași 6 emoții, tot RGB fără canal alfa | la fel — „fără fundal” e alb, nu transparent |
| `evo.veado` | proiect binar al aplicației vechi (header `VEADOTUBE`, meta „1.4”) | se ignoră; pozele sunt sursa, nu proiectul |
| `CB3IRDWf…png`, `Tiex1FQ…png`, `Minecraft_SUPERCITY_logo_png.png` | artwork de rezervă / logo | nefolosite de overlay |

## 7. Verificare

```
python vtuber/pngtuber.py --check     # 9 stări, 4 reguli automate, toate RGBA
python -m pytest vtuber -q            # 36 teste
```
