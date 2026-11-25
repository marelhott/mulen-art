# Atelier Lab: nový rámec (stav 2026-11-25, rozpracováno)

**Účel tohoto souboru:** kompletní předání práce. Kdo ho čte později (jiná session, jiný model), najde tu cíl, to, co už se ví, zdroje, plán testů a další kroky. Navazuje na `docs/atelier-smer.md` (všechny uživatelovy texty, výsledky A/B, diagnóza) a na paměť `atelier-smer`.

## 1. Zadání uživatele
Vzít všechno, co uživatel poslal (texty o Ateliéru, rozhovory s Klingemannem), vytvořit **nový rámec přístupu**, udělat **sérii testů** a teprve potom přidat do aplikace jako **úplně novou záložku**. Důraz: nejdřív do hloubky nastudovat. Uživatel je malíř, chce redukci, rozbití, špínu, ne fotorealismus (viz paměť `artistic-intent-imperfection`). Systém je křehký: nové věci jen jako volby, výchozí chování nezměnit.

## 2. Co už se ví (potvrzené testy)
- Kolize výřezů z archivů (denoise 0,9-0,95) = checkpoint domaluje figuru (tvář, ruka); uživatele se výsledky vůbec nelíbí. **Mrtvé.**
- Druhý průchod 1536 px (denoise 0,28) nic viditelného nepřidal.
- Prostorová slova z titulků v 1. fázi: 2x plnější, 2x zvrhnutí; nerozhodnuto.
- Přepínač "Záběr: celek" (nasazený): u Mulen Mara dramaticky mění stavbu (celé rámy, okna, figury), u Tuymanse jemně; u krajiny nepomohl.
- V Ateliéru nejsou smazané záznamy; 10 uložených vs 43 neuložených. Slabý náznak: uložené jsou tmavší (podíl tmy AUC 0,69). Sběr dávek přes `batch_id` je nasazený.
- Slova ("dramatičtější", "bohatší") dávají generátoru volnou ruku k efektu; SDXL checkpointy s CFG ~0,5 navíc pokyny neplní. Kompozici určuje prvních 20-30 % kroků.

## 3. Hlavní myšlenka rámce
Místo **psaní promptů** zasahovat přímo do mechanismu, kterým model přiděluje význam (Klingemann: Neural Glitch, Weapons of Mass Distraction). Poškodit síť **jen v první fázi běhu** (kde se rozhoduje stavba), druhou fázi nechat doběhnout zdravým checkpointem, který obraz "vyléčí" vaším rukopisem. To je Klingemannovo řetězení (poškozený model -> opravující model) v dvoufázovém mechanismu, který aplikace už má (`denoising_end`/`denoising_start`, `atelier_color_until`).

Os rámce (každý pokus = jedna kombinace):
1. **Kdy** (fáze): prvních ~30 % kroků / celý běh (kontrast "bez léčení").
2. **Kde** v UNetu: down / mid / up bloky; self-attention vs. cross-attention vs. výstup bloku; hrubé vs. jemné rozlišení.
3. **Co** (operace): šum do aktivací; potlačení nejsilnějších aktivací (top-k); vynulování části kanálů; hlavy self-attention -> identita (SoftPAG); vynulování cross-attention; šum ve vahách (se zálohou a obnovou).
4. **Léčení**: zdravý checkpoint po zbytek kroků (stejný nebo jiný checkpoint).
5. **Výběr**: kurátor z více seedů (z dat `batch_id`, vlastní volby uživatele).
Kritéria úspěchu (hodnotí uživatel i Claude pohledem): rozbitý význam (žádná rozpoznatelná tvář, předmět, druh), zachovaný rukopis (tah, hmota, špína), bohatší stavba (asymetrie, hloubka), bez kýče a bez neonových glitch artefaktů.

## 4. Zdroje, které je dobré znát
- Klingemann, Neural Glitch (2018): https://www.quasimondo.com/2018/10/28/neural-glitch/ (náhodné změny, mazání a prohazování vah natrénovaných GANů, řetězení, "léčení" dalším modelem; žádná čísla).
- Verse rozhovor o Teratoma (2023): vlastní datasety, černobílost kvůli kapacitě, 1-5 % dobrých výsledků -> estetický klasifikátor.
- art-magazine.ai, duben 2026: Weapons of Mass Distraction = potlačení zjevných aktivací, model se "opravuje"; bez metody.
- Network Bending (Broad, Leymarie, Grierson, 2020/21): pevné deterministické transformace (ablace, inverze, ...) vkládané do hotové sítě za běhu, bez změny vah; seskupování features podle prostorové podobnosti. https://arxiv.org/abs/2005.12420, kód https://github.com/terrybroad/network-bending
- Perturbed-Attention Guidance (ECCV 2024) a studie hlav attention v SDXL ("Rethinking attention modules of SDXL in a flow perspective", SoftPAG): konkrétní hlavy řídí odděleně strukturu, styl, texturu; self-attention mapa -> identita. Diffusers dokumentace PAG: pag_scale ~3, velké hodnoty vyhlazují texturu.
- AttnMod (arXiv 2409.10028): modulace cross-attention v SDXL bez změny vah. DICE (arXiv 2602.08059): Q drží obsah, K/V styl.
- Klingemann GitHub (Quasimondo): ComfyUI-QuasimondoNodes (WIP); o poškozování vah nic.
- Neověřeno: tvrzení o jeho konkrétním dnešním setupu a o parametrech glitche; veřejně nejsou.

## 5. Technické poznámky o aplikaci
- Pipeline: diffusers `StableDiffusionXLImg2ImgPipeline`/`StableDiffusionXLPipeline` z jednoho souboru (`app_runtime/core.py: ensure_pipeline`), fp16, xformers (pokud selže, `_studio_xformers=False`). Rozhodnutí o dvou fázích: `app_runtime/atelier.py: generate_study`.
- Zásahy: forward hooky na výstupy bloků fungují i s xformers; zásah do self-attention hlav vyžaduje vlastní attention processor (xformers pak pro daný běh vypnout). Hooky řízené příznakem aktivovaným v `callback_on_step_end` (aktivní jen v prvních N krocích).
- Experimenty běží jako Modal skripty v `scripts/experiments/` (profil `MODAL_PROFILE=img2img`, `uv run --python 3.12 --with modal python -m modal run ...`), obrázky v `outputs/verification/` (mimo git). Vzor: `ab_atelier.py`.
- Nasazení: `MODAL_PROFILE=img2img uv run -q --python 3.12 --with modal python -m modal deploy modal_app.py`. Nasazuje se a pushuje jen po výslovném souhlasu uživatele.

## 6. Plán série testů (zatím nespuštěno)
Skript `scripts/experiments/glitch_lab.py` (ještě neexistuje): 3 checkpointy (mulen_mara, hofmann_sdxl, tuymans_modal_2400) x 4 seedy (11, 2024, 70707, 913) x operace, 1024 px, 28 kroků, dpmpp_2m karras, cfg 0,5, prompt prázdný (Volná studie), bez barevné nápovědy (čistá izolace efektu). Operace v prvních 30 % kroků:
0. control
1. šum do výstupu mid bloku (0,3 x std)
2. potlačení top 5 % aktivací (mid + první up blok)
3. vynulování 25 % kanálů (down blok 2)
4. self-attention v mid bloku -> identita (jen V)
5. vynulování cross-attention v up blocích
6. šum ve vahách mid bloku (5 % std, záloha a obnova)
7. jedna z operací v celém běhu (bez léčení) pro kontrast
Výstup: kontaktní archy po checkpointech (řádky seedy, sloupce operace). Cena do ~1 USD. Po prvním pohledu zjemnit síly a typy a udělat druhé kolo.

## 7. Další kroky
1. Napsat a spustit `glitch_lab.py`, vyhodnotit archy společně s uživatelem.
2. Druhé kolo: jemnější síly, kombinace, jiný checkpoint pro léčení, kurátor (batch_id data).
3. Teprve potom: nová záložka v aplikaci (např. "Lab") s ovládáním Kdy/Kde/Co/Léčení, jako samostatný režim; výchozí Ateliér nedotčený.
4. Otevřené: pushnout lokální commity (zrychlení startu, poznámky; ověřit `git log origin/feat/vari..HEAD`).

## 8. Druhé kolo: rozbíjet i vstupní fotky (dohodnuto s uživatelem 2026-11-25)
Nová osa **kam se zasahuje**: do vstupu / do modelu / do obojího; výsledek se přemalovává stejně jako v aplikaci (`repaint`, denoise 0,8).
- **Vstup:** `none`, `blur64` (zmenšení na 64 px a zpět, kostra, která u Posunu fungovala), `tiles` (8x8 dlaždic, 25 % zamíchaných).
- **Model:** `control`, `top_suppress`, `sa_identity`, `chan_drop` (tři operace, které v 1. kole opravdu změnily obraz), v prvních 30 % kroků.
- **Zdroje** (fotky, na kterých se testoval Posun): Thanatos, základní obraz s parníkem, sopečná krajina, rozbitá soška.
- Skript: `scripts/experiments/glitch_lab_img2img.py`, 1 checkpoint (mulen_mara), 4 zdroje x 3 vstupy x 4 operace + kontrola úniku.
- Klingemann tohle nepopisuje; je to naše rozšíření (Network Bending = transformace uvnitř sítě při zpracování vstupu).

## 9. Výsledky kola 1 (2026-11-25, glitch_lab.py; mulen_mara, hofmann_sdxl, tuymans_modal_2400 x 4 seedy x 8 operací)
Archy: `outputs/verification/glitch-lab/sheet-*.jpg` (mimo git). Kontrola úniku (kontrola znovu na konci): 0,000 u všech tří checkpointů, hooky se uklízejí správně. Poznámka: Modal worker jednou spadl při `starmap` bez ošetření chyb (RemoteError); vstupní bod teď ukládá po každém modelu a chybu vypíše.
Průměrná absolutní odchylka od kontroly (0-255): mid_noise 3,1 | xa_zero 2,8 | weight_noise 1,8 | sa_identity 6,4 | chan_drop 13,5 | top_suppress 25,1 | full_suppress 28,7.
- **Nic viditelného:** mid_noise (i při 1,5x std), weight_noise (25 % std) a xa_zero. Zásahy do mid bloku a cross-attention s prázdným promptem se ztratí.
- **top_suppress** (nejsilnějších 5 % aktivací v prvních 8 krocích) rozbije význam: tvary se rozpadnou na hrubé střepy a oblázky, zachová se rozložení, barvy i rukopis (léčení funguje). Riziko: vzniká vlastní uniformní textura "oblázků".
- **chan_drop** podobné, mírnější. **sa_identity** jemné změny stavby.
- **full_suppress** (bez léčení) rozbije i kompozici na rovnoměrnou mozaiku, tedy příliš.
- Zatím vyhodnoceno okem Claude; konečný soud má uživatel.

## 10. Výsledky kola 2 (2026-11-25, glitch_lab_img2img.py, jen Tuymans `tuymans_modal_2400`; mulen_mara spadl na nahodilé Modal chybě RemoteError, zatím nespuštěno znovu)
Archy: `outputs/verification/glitch-lab-img2img/sheet-tuymans_modal_2400-{thanatos,zaklad,sopka,soska}.jpg`. Přemalování denoise 0,8, 28 kroků, poškození v prvních 8. Kontrola úniku 0,000.
- **Vstup rozhoduje víc než zásah do modelu.** Rozdíl mezi `none`, `blur64` a `tiles` je mnohem větší než mezi `control`, `top_suppress`, `sa_identity`, `chan_drop`.
- **blur64:** zdroj ztratí identitu (postava, parník, sloupy zmizí), zůstanou hmoty a barvy; výsledek je měkký, malířský, bez rozpoznatelného předmětu. Nejblíž cíli "posun".
- **tiles:** rozbitá místní identita, ale checkpoint z dlaždic často složí **zvíře** (pták s kloboukem, hlava se zobákem); vzniká prototyp.
- **Tuymans checkpoint sám přečte ostrou fotku jako zvířecí tvar** (slon, pták) i bez poškození; to je jeho prior, ne zásah.
- top_suppress přidává střepy, chan_drop a sa_identity jen jemně; v kombinaci s blur64 mění detail uvnitř již rozpuštěných hmot.

## 11. Nasazeno do kódu (2026-11-25, necommitnuto, nenasazeno na Modal): Rozpad modelu v Ateliéru a ve Vari
Na přání uživatele ("první možnost", tedy rozbití modelu, ne blur ani dlaždice) jako **volba, výchozí chování beze změny**.
- `app_runtime/glitch.py`: kontext `damaged(pipe, op, total_calls, until, seed)`; operace `top_suppress` (Rozpad aktivací), `chan_drop` (Vynechané kanály), `sa_identity` (Chybné čtení pozornosti); hooky na `pipe.unet` jen v prvních `until` (0,1 až 0,6, výchozí 0,3) voláních UNetu, vždy uklizené ve `finally`.
- Ateliér: `GenerationInput.glitch`, `glitch_until`; `core.parse_input` (jen `atelier` a `reimagine`); `atelier.py` (noise/subject běh) a `repaint.py` (photo/archive); meta `glitch`, `glitch_until`; UI `Atelier.jsx` ("ROZPAD MODELU" + posuvník), `App.jsx` posílá pole jen při zapnutí.
- Vari: `pre_unclip_glitch` (jen s `pre_unclip`) se v `modal_app.py: unclip_stage` předá dětskému unCLIP jobu jako `glitch`; `unclip.generate_variations` ho aplikuje na UNet SD 2.1. Nano Pro a Gemini (API) rozbít nejde. UI `Nano.jsx` ("ROZPAD UNCLIPU" jen po zapnutí předstupně), `nanoTools.js`, `glitchTools.js`.
- Testy: `tests/test_glitch.py` (validace, hooky a úklid na falešném UNetu, napojení na Ateliér), `frontend/src/glitchTools.test.js`, doplněk v `nanoTools.test.js`. Celá sada: 191 backend, 52 frontend OK.
- Ověření na GPU (`scripts/experiments/glitch_check.py`): Ateliér s modulem = experiment (střední odchylka 0,13 až 0,17 z 255); unCLIP: top_suppress 9,9, chan_drop 5,6, sa_identity 1,8 odchylky od kontroly, kontrola po poškození 0,0 (žádný únik).
- Zbývá: nasadit (`modal deploy`) a pushnout až na výslovný souhlas; mulen_mara v kole 2 spustit znovu, pokud je potřeba.
