# Format .moc3 — ce e verificat, nu presupus

Toate regulile de mai jos sunt confirmate pe `ellot.moc3` (v4.2, model real care se
încarcă în VTube Studio) și/sau prin Cubism Core 6.0.1 (`live2d-py`), nu din memorie.

## Antet și tabelul de secțiuni
- `0..4` = `MOC3`, `4` = versiune (1=3.0, 2=3.3, 3=4.0, 4=4.2, 5=5.0), `5` = 0 (little-endian), restul zero.
- `64` = tabel de 160 × uint32 cu offset-uri absolute de la începutul fișierului; secțiunile încep la `1984`.
- `SOT[0]` = tabelul de contoare (128 B), `SOT[1]` = canvas info (64 B), `SOT[2..100]` = cele 99 de secțiuni, `SOT[101]` = quad transforms (necesar din 3.3 în sus).
- Offset-urile egale sunt **permise** (secțiuni cu 0 elemente); coada tabelului se umple cu ultimul offset valid.

## Contoare — capcane dovedite
- `counts[10]` (keyform positions) se numără în **floate**, nu în perechi x/y. Core compară
  mărimea secțiunii cu `count × 4` și altfel răspunde `Data section is invalid`.
- `counts[15]` (UV) = tot floate; `counts[16]` (position indices) = numărul de indici (i16).
- `counts[17]` (drawable masks) trebuie să fie **cel puțin 1**; dacă nu există măști se scrie o intrare `-1`.

## Keyform-uri
- Numărul de keyform-uri al unui art mesh = **produsul** numărului de chei ale legăturilor
  din bandă (verificat: 240/240 mesh-uri din ellot).
- Benzile sunt **partajate**: `art_mesh.keyform_binding_band_indices[k]` dă banda mesh-ului `k`,
  iar mai multe mesh-uri pot folosi aceeași bandă (în ellot: 240 mesh-uri, 24 benzi folosite).
- Ordinea keyform-urilor e mixed-radix cu **prima legătură variind cel mai repede**
  (`A` 4 chei × `B` 2 chei → primele 4 au `B`=cheia 0, apoi următoarele 4 au `B`=cheia 1).
- Legăturile se scriu grupate pe parametri (`parameter.keyform_binding_begin_indices/counts`
  trebuie să fie intervale contigue), iar banda adună indicii prin `keyform_binding_index.indices`.

## Măști
- Un mesh e mascat dacă `art_mesh.mask_counts[k] > 0`; intervalul dă indicii de art mesh
  din `drawable_mask.art_mesh_indices` care se folosesc ca mască.
- `drawable_flags` **nu** codifică mascarea (în ellot apare 4 și la mesh-uri mascate, și la cele nemascate).

## Ordine de desenare — capcana care a crăpat VTS (dovedită prin bisecție)
- `draw_order_group.min_draw_orders` = **500** și `max_draw_orders` = **499**, fix.
  Orice altă pereche (inclusiv min/max calculate din ordinele reale ale mesh-urilor)
  face Cubism Core să iasă cu **SIGSEGV** la încărcare — fără mesaj, fără cod de eroare.
- Dovada (fișiere mici, aceleași date, diferă doar câmpul):
  toate ordinele egale → `ok`; `500/510/520` cu `min=500,max=520` → crash;
  același fișier cu `min=500,max=499` → `ok`. Modelul real `ellot.moc3` are tot `500/499`.
- Ordinele per mesh (`art_mesh.draw_order`) și per keyform sunt libere — nu ele crapă.

## Verificare
`python vtuber/check_moc3.py <fisier.moc3>` rulează Cubism Core într-un subproces și
raportează parametrii, canvas-ul și dacă fișierul e acceptat. Un crash al Core = fișier respins.
