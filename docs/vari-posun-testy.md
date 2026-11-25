# Posun: testy a poznatky (stav k 23. 11. 2026)

Navazuje na `docs/vari-zadani.md` / `.html` (zadání) a `docs/vari-srovnani.jpg` (vlevo zdroj, vpravo cíl od starého modelu).
Obrázky všech testů jsou v `docs/vari-testy/`, přehledové tabulky jsou `vari-testy-kolo1.jpg`, `…kolo2-fal.jpg`, `…kolo3-nano.jpg`.

## Cíl (jak ho uživatel chápe)
Z obrazu udělat **posunutou verzi**: kostra zůstane (kompozice, váha velkých tvarů, horizont, paleta, médium malba/tisk), ale **každá věc se přečte jako jiná**, z jiné hmoty. Místo nesmí být rozpoznatelné. Prompt musí být **univerzální a stručný**: žádné slovo z konkrétního obrazu (parník apod.). Pracovní postup: mnoho testů, vždy aspoň 2 verze od každého promptu, hodnotit kriticky.

Zdroje: `zdroje/A_source.jpg` (tisk s parníkem, přemalovaný růžovými a černými tahy), `zdroje/B_target.jpg` (cíl), `zdroje/N_les.jpg` (druhý testovací obraz: les s bílou postavou), `C_blur32`, `D_blur64`, `E_poster8` (rozostřené a posterizované kostry zdroje).

## Co uživatel řekl o hodnocení
- Seedream: **vůbec ne** (vynechat).
- Zatím „katastrofa“; nejvíc zaujaly výsledky **A v1, A v2 a D v2** v Nano Pro (nenápadné, skoro nezměněné, s lehkým přemalováním/odrazem). Je to směr, který chce zkoumat dál.
- Prompty „4 a 5“ z mé první české sady (mimo „Zhmotnění gesta“) nechtěl.
- Další krok, který žádal: otestovat na **dalších zdrojích** (aspoň 5, z jeho disku, `~/Pictures`) na fal. Příprava přehledu zdrojů běžela na pozadí a nebyla dokončena.

## Prompty (angličtina, tak šly do modelů)
**A (spojení gesta a výjevu):** Remove the boundary between what the picture depicts and the traces of paint on its surface. Merge them into one place that does not exist: strokes and blotches become things in space, and the landscape around them is rebuilt according to them. Keep the composition, the weight of the masses, the horizon and the colours. Of the small details of the original let only a few remnants survive, with large quiet areas between them. It is still a painting or a print.

**B (po paměti):** Paint this picture from memory. You remember exactly the spacing, heights, the weight of dark and light masses, and the colours, but you no longer recall what stood there. So complete every shape with something else that fits its place. Leave sharp edges, soft blotches and wiped-out areas next to each other. The place should feel familiar but cannot be named.

**C (výměna povrchů):** Keep the composition and colours, but let the parts of the picture exchange surfaces: the texture of one area passes onto another, drawing becomes mass, mass becomes drawing. Let vertical and horizontal shapes pass through layers other than those they belonged to. The original scene withdraws into a narrow band or a few remnants. A painting stays a painting.

**D (kontrola, uživatelova druhá sada č. 2 „Zhmotnění gesta“):** Abolish the difference between what is depicted in the picture and what is on its surface as stroke, blot or texture. Merge both into one single really existing but foreign space. Keep the composition, the placement of the main vertical and planar masses and the original muted palette. Turn every prominent shape and trace into a new, physically present but unknown matter (for example bleached, charred, weathered, organic or mineral), simplify the background into nameless empty structures, heavy atmosphere or a finely grooved surface, and if the composition allows, anchor the bottom edge with a calm dark water surface with a blurred vertical reflection. Keep raw, unsmoothed transitions, little fine detail, a matte analog character and natural imperfection.

Starší krátké prompty z kola 2: **prompt A (starý)** „Keep the composition, layout and palette. Reread every shape as something else, of a different material, so it becomes a place that does not exist. Flat cut-paper planes, hard edges, visible seams, soft grain. Not realistic, not glossy.“ a **prompt B (starý)** „Keep only where things are and what colour they are. Change what every shape is: each becomes a different, unrecognisable thing of another material, in the same spot. A place that does not exist. Flat, hard-edged, grainy print.“ (v tabulkách kola 2 značené A a B; nepleť s novými A až D výše).

## Výsledky
**Kolo 1 (webový ChatGPT a Gemini, dlouhý konkrétní prompt ze zadání):** ChatGPT s ostrým zdrojem (C1) se cíli přiblížil nejvíc (rytinové nebe, kůlny, odraz, kosti). Gemini s ostrým zdrojem se vrací k původnímu tisku (G1). Rozostřená kostra (32 px) pomáhá plochosti u ChatGPT (C2). **Posterizace je past** (G3: z barevných skvrn vzniklo rozpoznatelné místo, mrtvé stromy v bažině).

**Kolo 2 (fal, krátké obecné prompty, starý A a B):** Nano Pro s „cut-paper“ promptem změní jen materiál (koláž), s promptem „keep only where/what colour“ udělá abstraktní posun, ale s lesem selže. Kontext spadne do akvarelu a stromu. Recraft (illustration, strength 0,75) dává silný, ale vlastní prototyp (koule, kvádry, jehlany). GPT-Image 1.5 dává zářící fantasy kýč (0,20 USD za běh). Seedream ztratil kostru.

**Kolo 3 (fal, Nano Pro, nové A až D, základní obraz, po dvou verzích):** A: skoro původní obraz s přemalovanou vodou (**uživatele zaujalo**). B: v1 kotva s řetězem a vrtná věž (konkrétní předměty), v2 změť tahů. C: v1 koláž z gest, v2 úzký pás originálu. D: v1 vybělené kmeny, ohořelý sloup a odraz (nejblíž cíli), v2 skoro původní obraz s odrazem (**uživatele zaujalo**). Variace mezi běhy je velká.

## Poznatky
- Slova „flat“, „cut-paper“, „another material“ model čte jako změnu stylu (koláž, sítotisk), ne jako změnu toho, čím věci jsou.
- Seznam hmot („bleached, charred, weathered“) funguje nejlíp, ale je to zakódovaný cíl a na jiném obraze by vedl ke stejným kostem a uhlí.
- Nano Pro je na fal nejlepší základ (0,15 USD za 1K). Gemini/ChatGPT na webu se hodí k rychlým pokusům, ale chovají se jinak než fal.
- Les (hotové stromy, žádná přemalba) je těžší, protože chybí „gesto“, které se má přečíst jinak.

## Fal: jak se s tím pracovalo (Chrome, přihlášený účet uživatele)
- Modely: `fal-ai/nano-banana-pro/edit`, `fal-ai/flux-pro/kontext`, `fal-ai/recraft/v3/image-to-image` (styl vybrat klikem v rozbalovači, `strength` v „See more“), `fal-ai/gpt-image-1.5/edit`, `fal-ai/bytedance/seedream/v4/edit` (nepoužívat).
- Ceny za běh: Nano Pro 0,15 USD, Kontext 0,04, Recraft 0,04, GPT-Image 1.5 0,20, Seedream 0,03. Zůstatek 4,78 USD na začátku, kolem 2,88 USD po kole 3.
- Pole obrázku u Nano Pro a Seedreamu přijímá víc obrázků (nahrání přidává, neodebírá), u Kontextu jeden. Předvyplněné ukázky je třeba odstranit.
- Rychlý druhý klik na Run se někdy nezapočítá. Mezi běhy dát pár vteřin pauzu a počet ověřit v historii (režim „List“ ukazuje u každého prompt).

## Co zbývá
1. Vybrat aspoň 5 různých zdrojů z `~/Pictures` (obrazy, ne osobní fotky) a pustit na ně A a D (po dvou verzích) na Nano Pro, asi 1,50 až 3 USD.
2. Pustit A a D na lese (`N_les.jpg`) a zjistit, zda D vydrží bez přemalby.
3. Recraft illustration s nižším `strength` (0,4 až 0,6).
4. Z toho vybrat jeden krátký obecný prompt pro `app_runtime/nano/plans.py` (`DISPLACE_PROMPT`) a případně pre-stage rozostření zdroje.
