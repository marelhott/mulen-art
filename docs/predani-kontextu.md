# Mulen Art: předání kontextu (stav 28. 11. 2026)

Pro pokračování z jiného účtu nebo v nové session. Napiš na začátku: **„Přečti `docs/predani-kontextu.md` a navaž."**

Paměť Claude a přepisy konverzací leží jen na tomto Macu pod uživatelem `mulenmara`. Podstatné z nich je proto zapsané tady.

## 0. Kam sáhnout pro detaily
| Soubor | Obsah |
|---|---|
| `README.md` | architektura, nasazení, funkce (části o frontě Ateliéru a o synchronizaci jen dvou složek jsou zastaralé) |
| `docs/atelier-smer.md` | uživatelovy texty o Ateliéru, Claudovy návrhy, výsledky A/B, diagnóza, Klingemann |
| `docs/atelier-lab-ramec.md` | rámec Atelier Lab, zdroje, plán a výsledky testů, Rozpad modelu |
| `docs/vari-zadani.md`, `docs/vari-posun-testy.md`, `docs/vari-testy/` | zadání Vari a testy režimu Posun |
| `~/.claude/projects/-Users-mulenmara-CODE-DISK-apps-Mulen-art/memory/` | paměť (jen na tomto Macu) |
| `~/.claude/projects/-Users-mulenmara-CODE-DISK-apps-Mulen-art/*.jsonl` | úplné přepisy; hlavní je `e8e2ce02-be8b-419f-8eae-fbef746de21f.jsonl` (část práce vznikla v jiných session) |

## 1. Uživatel a jak s ním pracovat
- Malíř. Odpovídat **česky**.
- Záměr: žádný realismus ani fotografická uhlazenost, nedokonalost je hodnota. U Vari nejde jen o „špínu a rozklad" (to byl chybný první výklad). Cílem je **posunuté, neexistující místo**: zachovat kostru předlohy (kompozice, barvy, polohy gest) a posunout, čím věci jsou. Nepřítelem je prototyp, tedy nejpravděpodobnější rozpoznatelný předmět. Metodu posuzovat podle toho, na vlastních zdrojích uživatele.
- **Systém je křehký.** Výsledky stojí na náhodných vlastnostech (např. nulový negativní embedding při `negative_prompt=None`). „Čistší" kód neznamená lepší obraz. Nové věci přidávat jen jako volby, výchozí chování neměnit, změny ověřovat srovnáním vedle sebe na vzorcích.
- **Commit, push a nasazení** dosud jen po výslovném souhlasu.
- „Ukládej / nic zatím nedělej / jenom se bavíme" brát doslova.
- Globální pravidla (`~/.claude/CLAUDE.md`): pro UI `frontend-design`, design critique a accessibility review, vizuální ověření na mobilu i desktopu.

## 2. Aplikace a provoz
SDXL studio: FastAPI brána a GPU workery na Modalu, React frontend. Záložky Vari, unCLIP, Ateliér, Plátno, Koláž a Knihovna.

- Repo `github.com/marelhott/mulen-art`, aktivní větev **`feat/vari`**. Lokální `main` je o 1 commit před originem a práce se na ní nedělá. `.claude/` je mimo git.
- **Modal profil musí být `img2img`.** Aktivní profil Macu je `marelhott`, starý workspace s vlastním `img2img-outputs`.
- Nasazení (nejdřív build):
  ```bash
  cd frontend && npm run build
  ```
  ```bash
  MODAL_PROFILE=img2img uv run -q --python 3.12 --with modal python -m modal deploy modal_app.py
  ```
  URL vypíše deploy. Ověření: název `assets/index-*.js` na živém webu = ten ve `frontend/dist/index.html`.
- Přihlášení je v ignorovaném `.modal-app-credentials.json`. Hodnoty nevypisovat; používal se jen k ověřovacím dotazům na vlastní aplikaci.
- Testy 28. 11.: backend `.venv/bin/python -m unittest discover -s tests` **197 OK**, frontend `node --test frontend/src/*.test.js` **59 OK**, lint i build OK.
- Lokální náhled: server `mulen-nano-ui` z `.claude/launch.json` (port 8002, demo režim). Po změně šířky okna stránku obnovit, otevření pravého panelu se počítá jen při načtení (hranice 900 px).
- Start GPU: teplý asi 2 s, studený 17–40 s, hned po nasazení i kolem 4 min.

## 3. Postup chronologicky
**Do 20. 11. (větev `codex/mulen-nano-studio`)**
- Audit, úklid, fotoknihovna Ateliéru, sdílený repaint krok.
- Analýza 555 obrázků galerie. Z návrhů druhého modelu (Fable) zavedeno tak, aby se výchozí chování nezměnilo: zápis „receptu" (verze knihoven, GPU) do metadat a přepínače `repaint_cfg_floor` a `vae_tiling`. Test bez guidance na vzorcích zlepšení neprokázal.
- Oprava smyčky „Job expired", refaktor a vyladění frontendu.

**21.–22. 11.**
- Záložka unCLIP (SD 2.1 unCLIP, Metamorfóza, presety se seedy).
- Vari: nejdřív port Next.js aplikace Variants, ten byl **celý odstraněn** a nahrazen Vari a Koláží z Mulen Nano (OpenRouter, Venice). Přibyl režim Posun a volitelný unCLIP předstupeň.
- Testy univerzálního promptu pro Posun (ChatGPT, Gemini, fal). Zaujaly výsledky Nano Pro s prompty A a D. „flat/cut-paper/another material" model čte jako změnu stylu, seznam hmot je zakódovaný cíl, posterizovaná kostra je past. Seedream uživatel odmítl. Možné pokračování: dalších aspoň 5 zdrojů z `~/Pictures`, A a D na `fal-ai/nano-banana-pro/edit`, po 2 verzích; předem zkontrolovat zůstatek.

**23. 11.**
- Zrychlení brány (zápisy na Volume na pozadí, útrata z paměti, šetrné zahřátí galerie).
- Přejmenování na Mulen Art, logo, favicon, instalovatelná web aplikace s kontrolou nové verze.
- Koláž ukazovala 0: 16 záznamů bylo hromadně smazaných. Obnoveny; opraveno i to, že je prohlížeč dál skrýval ze své paměti smazaných.

**24. 11.** Konzultace: analýza displacement promptu a nabídka obrazových modelů Googlu (aplikace volá `google/gemini-3-pro-image` a `google/gemini-nano-banana-2.1`).

**25. 11.: Ateliér k plnějším obrazům** (podrobně v `docs/atelier-smer.md`)
- Diagnóza potvrzená uživatelem: `SUBJECTS` jsou záměrně ploché; Volná studie (šum, prázdný prompt) padá do průměrné kompozice; kompozici určuje prvních 20–30 % kroků.
- **Slepé cesty:** kolize výřezů z archivů (checkpoint domaluje figury, uživateli se vůbec nelíbilo); druhý průchod 1536 px nic viditelného nepřidal. Prostorová slova v 1. fázi: nerozhodnuto. Test „malířských rozhodnutí" přes Nano Pro neproběhl (OpenRouter 402, bez kreditu).
- Kurátor: 10 uložených proti 43 neuloženým, jen slabý signál (uložené jsou tmavší, AUC 0,69). Dat je málo.
- Nasazeno: `batch_id` ke sběru sourozenců; odstraněn panel Fronta Ateliéru; přepínač **Záběr: výřez / celek** (výchozí výřez; ve Volné studii jde pokyn jen do 1. fáze; u Mulen Mara účinek silný, u Tuymanse jemný); zahřátí GPU při otevření Ateliéru a worker běží 60 s po úloze.
- Klingemann: rozhovory **žádnou konkrétní metodu zásahu nepotvrzují**. Atelier Lab je naše interpretace.
- Atelier Lab, 2 kola testů: znatelně působí `top_suppress`, `chan_drop` a slaběji `sa_identity`; šum do mid bloku, šum ve vahách a vynulování cross-attention nic viditelného. V img2img rozhoduje vstup víc než zásah, ale **rozmazání a dlaždice uživateli nic neříkají**, chtěl jen rozbití modelu.
- Z toho **Rozpad modelu** v Ateliéru a v unCLIP předstupni Vari (`app_runtime/glitch.py`, výchozí vypnuto). Commit `e3c8f62`.

**26. 11.**
- Nová ikona (gradientové M); na Macu nastavena i jako vlastní ikona `Mulen Art.app` v `~/Applications/Chrome Apps.localized` (lze odstranit přes Informace ve Finderu).
- Plátno bez lišty „Vybrat více" a bez filtrů (tím tam nejde hromadný výběr).
- Vari: výběr modelů v pravém panelu, se zavřeným panelem vlevo.
- Synchronizace do `~/Pictures/Mulen art`: složky Plátno, Atelier, unCLIP, Vari, Koláž; profil `img2img` je ve skriptu přednastavený. Staženo, stav po doplnění: 265 obrázků (81 / 76 / 44 / 64 / 0). 41 obrázků omylem stažených ze starého workspace je v Koši ve složce „Mulen art - stary ucet".

## 4. Stav teď
- Poslední **nasazený a pushnutý** commit s kódem je `c28b8a3` (nasazeno 28. 11.; živý bundle `index-DqTfNyHe.js` shodný s buildem; `/api/usage` a `/api/library` odpovídají 200). Po tomto nasazení neproběhla žádná GPU úloha, takže rozběhnutí fronty a zrušení Vari naživo ověřené nejsou.
- Opravy z 28. 11. v tomto nasazení: zrušení Vari zastaví i unCLIP mezikrok; Koláž si pamatuje všechny vstupy; Zopakovat umí Ateliér, vrací na správnou záložku a vstupy nahrazuje; mazání čerstvého obrázku; čekající karty zůstávají na své záložce; názvy a filtr modelů v Knihovně; export 2× i pro 3072 px s chybovou hláškou; pokyn k záběru se neukládá jako barva; jméno souboru při chybě nahrávání v Koláži; Rozpad modelu na unCLIP (jen Varianta). Testy po opravách: backend 197, frontend 59, lint i build OK. V prohlížeči ověřen jen ovladač Rozpadu na unCLIP; ostatní jen testy.
- Před tímto nasazením živý web 28. 11. obsahoval Rozpad modelu, přepínač Záběr i `batch_id` (ověřeno v živém JS bundlu `index-BfynjvEB.js`). Samotný Rozpad modelu přes živé rozhraní vyzkoušený v zapsaných záznamech není; ověřen byl na GPU skriptem `glitch_check.py`.
- Synchronizační služba `cz.mulen.art.sync` běží.

## 5. Otevřené a neověřené
Z rozboru chyb (28. 11.) záměrně neopraveno: vracení kvóty po zrušení či pádu a cena API modelů v rozpočtu; `MODAL_PROFILE` a pročišťování stavu v `sync_images.py`; reset zvětšení na 1× při nahrání vstupu (nejdřív se zeptat); polovina kroků u Metamorfózy (oprava by změnila obrazy); sdílený či skrytý unCLIP mezikrok Vari (rozhodnutí o podobě); obsazení VRAM v UnclipWorker (neověřeno).

1. **Koláž, termín:** 16 záznamů je znovu označeno jako smazané (`deleted_at` 23. 11. 15:41, příčina nezjištěná). Kolem **23. 12.** se odstraní natrvalo. Nabídka obnovit je bez odpovědi.
2. Stažení nově vygenerovaného obrázku po opětovném zapnutí synchronizace zatím nebylo potvrzené.
3. Neověřeno, že se `batch_id` skutečně zapisuje do nových záznamů.
4. Uživatel nepotvrdil, že Dock ukazuje novou ikonu.
5. **Atelier Lab:** uživatel chtěl nejdřív důkladné studium, pak sérii testů a teprve potom **úplně novou záložku**. Proběhla 2 kola testů a volba Rozpad modelu v existujících záložkách; nová záložka neexistuje. V kole 2 je jen Tuymans, běh Mulen Mara spadl na chybě Modalu. Výsledky kola 1 hodnotil okem Claude. Další krok: nechat uživatele posoudit, pak jemnější síly, kombinace, jiný léčící checkpoint, kurátor.
6. Další nápady k Ateliéru: konkrétní malířská rozhodnutí jako úpravy podmalby a masky (plánuje VLM, provede kód, SDXL checkpointy pokyny neplní), paměť sourozenců a výběru, střídání checkpointů v čase.
7. OpenRouter byl 25. 11. bez kreditu; aktuální stav neznámý.
