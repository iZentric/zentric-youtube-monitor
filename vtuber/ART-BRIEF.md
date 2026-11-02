# ART-BRIEF.md — ce poze îmi trebuie ca să duc personajul la nivelul următor

Starea de azi: cu cele **9 poze** existente merge overlay-ul automat (voce + expresii + clipit + legănare + gura pe 3 trepte). Demo-ul rulează deja. Ce lipsește nu ține de soft, ține de **desen**.

Regula care face totul să funcționeze: orice poză nouă trebuie să fie **același personaj, în aceeași poziție, pe același canvas**. Nu se redesenează personajul, nu se mută, nu se rescalează — altfel straturile nu se mai suprapun și totul „sare”.

## Specificația tehnică (obligatorie pentru fiecare fișier)

| ce | valoare |
| --- | --- |
| format | PNG, 32 biți, **RGBA** (fundal transparent real, nu alb) |
| canvas | **1024 × 1024**, exact ca pozele actuale |
| ancoră | emblema yin-yang centrată în **(554, 876)**; vârful capului la **y = 37** |
| poziționare | personajul încadrat identic cu `idle.png`, tăiat la marginea de jos (bust) |
| bleed | fiecare strat care acoperă altceva are **6–10 px în plus** sub margine (ex.: irisul se desenează cu 8 px peste pleoapă) |
| umbre | fără umbre de contact între straturi (se adaugă la randare) |
| nume | exact cele din tabelele de mai jos, litere mici, fără diacritice |

Zonele măsurate în pozele tale, ca reper pentru desen:

- **ochi**: dreptunghi (303, 327) → (709, 513)
- **gură**: dreptunghi (415, 480) → (617, 632)

## Nivel 1 — 1 fișier — cel mai bun raport efort/efect

| fișier | ce conține | ce deblochează |
| --- | --- | --- |
| `eyes_half.png` | pleoape pe jumătate, restul identic cu `idle.png` | clipitul devine deschis → pe jumătate → închis → pe jumătate → deschis, în loc să sară direct |

Acum clipitul are două poziții; cu fișierul ăsta arată ca un clipit real. E o singură poză, ~30 de minute de muncă.

## Nivel 2 — 3 fișiere — ochii care se uită

| fișier | ce conține |
| --- | --- |
| `eye_L_white.png` | albul ochiului stâng, **fără** iris și fără pupilă |
| `eye_R_white.png` | albul ochiului drept, la fel |
| `iris.png` | **un singur** iris + pupilă + reflexe, desenat separat, mai mare decât ochiul (ca să poată aluneca pe sub pleoapă fără să iasă din alb) |

Se aplică peste `idle.png` peste alb. Cu ele, ochii urmăresc poziția feței în cameră și cursorul — exact lucrul care face diferența între „PNGtuber” și „VTuber”.

## Nivel 3 — 3 fișiere — capul separat de corp

| fișier | ce conține |
| --- | --- |
| `head.png` | capul + gâtul, **fără** corp |
| `body.png` | hanoracul + umerii, **fără** cap și fără gât |
| `hair_back.png` | părul din spate (partea care se vede când capul se întoarce) |

Cu ele capul se rotește ±10°, se înclină pe buză, iar corpul respiră separat. **Ăsta e nivelul de la care modelul se poate riga în Live2D** (Ayatsuri2D gratuit, exportă `.moc3`, sau Live2D Cubism) → apoi se încarcă în VTube Studio și ai tracking complet de cap.

## Nivel 4 — expresii și stări care lipsesc

| fișier | de ce |
| --- | --- |
| `angry.png` | **nu există** — ai laugh, love, sad, shocked, sus, dar nu ai furie |
| `focus.png` | concentrare la gameplay (Minecraft) — mult mai folosită decât `love` în timpul jocului |
| `thinking.png` | „hmm”, pentru momentele în care citești chatul |

Fiecare e o poză întreagă, ca cele 5 de acum.

## Nivel 5 — fizică și detalii (opțional, dacă mergi pe Live2D)

| fișier | ce face |
| --- | --- |
| `hair_front.png` | șuvițele din față, separat de cap, cu 2–3 segmente |
| `horn_left.png`, `horn_right.png` | cornițele separat — fizică la mișcarea capului |
| `hoodie_strings.png` | șnururile de la glugă — fizica cea mai vizibilă la un bust |
| `hands.png` | mâinile, dacă vrei gesturi |

## Ordinea în care le-aș cere

1. `eyes_half.png` — 30 min, efect imediat.
2. `angry.png` + `focus.png` — 2 poze, îți completează vocabularul de reacții.
3. `eye_L_white.png`, `eye_R_white.png`, `iris.png` — ochii care se uită.
4. `head.png`, `body.png`, `hair_back.png` — deblochează Live2D + VTube Studio.

## Cum mi le trimiți

Urcă-le pe GitHub în `vtuber/assets/raw/` (Add file → Upload files) cu numele exacte de mai sus și scrie-mi „gata”. Le măsor (canvas, ancoră, alfa), îți spun dacă se aliniază cu pozele existente, apoi le leg în păpușă și îți arăt randarea înainte să intrăm pe live.

## Dacă le comandă un desenator

Text de copiat în mesaj:

> Am nevoie de straturi separate pentru un avatar 2D, stil chibi, desenat deja (atașez pozele). Fiecare fișier: PNG 1024×1024 cu fundal transparent, personajul încadrat exact ca în `idle.png`, fără redimensionare. Straturi cerute: cap (fără corp), corp (fără cap), albul ochilor fără iris, iris separat (mai mare decât ochiul, ca să alunece sub pleoapă), pleoape pe jumătate, sprâncene separat, păr față/spate, cornițe separat. Fiecare strat care acoperă altul are 6–10 px în plus sub margine. Fără umbre de contact între straturi. Nu redesena personajul: aceleași culori, aceeași proporție, aceeași poziție.

## Ce NU ajută

- poze generate de AI după personaj — ies aproape, dar nu se aliniază la pixel și se vede la fiecare clipit;
- poze redimensionate sau „curățate” de fundal cu margini tăiate;
- format WebP sau JPG — pierd canalul alfa;
- alt unghi de cameră sau altă expresie a feței în afara zonei cerute.
