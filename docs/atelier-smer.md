# Ateliér: směr k plnějším, dramatičtějším obrazům (bez ztráty rukopisu)

Stav k 2026-11-25. Uživatel nechal postup plně na Claudovi, ale chce, aby se všechny tři zdroje níže pamatovaly.

## Výchozí diagnóza (ověřeno v kódu)
- `SUBJECTS` v `app_runtime/atelier.py` jsou záměrně ploché: "cropped", "plain background", "flat light", "no surrounding context".
- Foto-předloha má natvrdo `"Flat light, no dramatic lighting."` (atelier.py, generovaná předloha SDXL Base).
- Volná studie = prázdný prompt, nízké CFG (~0.5) -> statistický průměr (barva i kompozice).
- Dvoufázový běh (`denoising_end`/`denoising_start`, `atelier_color_until`) dnes nese jen barevnou nápovědu.
- Kompozici rozhoduje prvních ~20-30 % kroků; řídí ji hrubé masy, ne slova.

## Zdroj A: Claudovy návrhy
1. Kurátor: generovat víc, ponechat bohaté (nulové riziko).
2. Tonální kostra (2-5 hrubých hmot) jako init, img2img denoise ~0.85-0.9.
3. Kostra z cizí malby (rozmazaná tonální mapa).
4. Druhý průchod (hires fix) denoise ~0.4-0.55 -> hustší povrch.
5. Dvoufázový prompt i pro kompozici (stavba v 1. fázi, tichý prompt ve 2.).
6. Druhá sada námětů "napětí" (deadpan, ale událost ve světle/měřítku) - jen jako volba.
7. Míchání checkpointů rozdělené v čase.
Zásada: vše jako nové volby, výchozí chování netknuté (systém je křehký).

## Zdroj B: první text uživatele (5 cest)
1. Slepá podmalba: kolize 2-3 výřezů z vlastních archivů (mulen, hofmann, tuymans, MALBA), pootočit, srazit diagonálou/prolnutím, vytáhnout kontrast, denoise ~0.88-0.93. Přežije jen nízkofrekvenční kostra.
2. Rozšířit dvoufázový běh "Architektura 0-30 % -> Rukopis 30-100 %":
   a) střídání modelů v čase (Hofmann staví, Mulen/Tuymans maluje) místo lineární fúze;
   b) prostorová/světelná slova z vlastních tréninkových titulků (against a black ground, reflected in a dark floor, seen from above, overlapping figures, cut off by the top edge, deep shadows) jen v první fázi.
3. Kombinatorické náměty ze 3 os (těleso/děj, prostorový protihráč, řez a světlo); ve Foto->malba zrušit "Flat light".
4. Druhý malířský průchod vlastním checkpointem na 1536 px, 10-12 kroků, denoise 0.22-0.30, CFG ~0.5, jemné analogové zrno předtím.
5. Kurátor v mezipatře: 3-4 seedy jen do ~25 % kroků, změřit tonální rozpětí, mimostředovost, členitost, domalovat jen nejlepší.
Claudovy výhrady: (2a) latenty různých fine-tunů se mohou rozmazat - testovat; (1) hranice denoise mezi kostrou a útržkem je úzká a per-checkpoint; (3) riziko doslovné přeplněné scény - jen jako volitelné téma; "Flat light" zrušit jen přepínačem; tvrzení o 128x128 latentech přehnané.

## Zdroj C: druhý text uživatele (konkrétní malířské rozhodnutí)
- Ne přívlastky ("dramatičtější", "bohatší") - ty dají generátoru volnou ruku k efektu, dramatické obloze, všudypřítomné textuře.
- Drama vzniká ze vztahů: jeden zásah mění siluetu, měřítko i hloubku (černý útvar vytažený k hornímu okraji, otevřená mezera do hloubky).
- Bohatost z kontrastu: dlouhá hladká plocha + jediné místo neklidu (vlákna, šmouhy u paty tvaru).
- Ateliér si u každé předlohy najde, co jí dává charakter a kde je prostor ke změně, a pro každou variantu napíše jiný konkrétní pokyn ukotvený v obraze (příklady: "Otevři průhled", "Soustřeď všechen neklid do jednoho místa", "Dej jednomu povrchu dvě měřítka"). Médium, barvy, míra neurčitosti zůstávají z předlohy; mění se kompoziční rozhodnutí.
- Paměť výběru: ukládat celou čtveřici sourozenců + předlohu + kterou uživatel ponechal; učit se z voleb mezi sourozenci (vztahy), ne z jednotlivého uloženého obrazu.
- První pokus: 1 předloha, 1 generátor, běžná série vs. série s rozdílnými konkrétními rozhodnutími.
Claudova poznámka: SDXL checkpointy (trigger + CFG ~0.5) pokyny neplní. Most: čtenář obrazu (VLM) plánuje -> kód provede rozhodnutí jako úpravu podmalby/masky (posun/zúžení hmot, regionální denoise, přenos textury v jiném měřítku) -> checkpoint maluje.

## Zvolený postup
1. Levný test samotné myšlenky rozhodnutí přes Nano Pro (1 předloha, běžná vs. 3 rozhodnutí).
2. A/B v Ateliéru: kontrola / kolizní podmalba / prostorová slova v 1. fázi (po ověření titulků) / kolize + 2. průchod. Stejné seedy, 3 checkpointy x 4 seedy.
3. Rozhodnutí -> úprava podmalby + maska; kurátor v mezipatře; střídání modelů v čase jako samostatný experiment.
4. Ukládání sourozenců (dávka + výběr) co nejdřív, ať se sbírají data.

## Výsledky pokusů (2026-11-25)
- **Kolize výřezů z archivů (denoise 0,9, pak 0,93-0,95 s rozmazanými výřezy / tonálními masami):** uživatel se výsledky vůbec nelíbí. Checkpointy z jakýchkoli hmot domalují figuru (tvář, ruka se štětcem), obsah je z archivu. **Mrtvá cesta.** Skripty: `scripts/experiments/ab_atelier.py`, `ab_atelier2.py`, výstupy `outputs/verification/ab-atelier*/` (mimo git).
- **Druhý průchod 1536 px (denoise 0,28):** viditelně nic nepřidal. Odloženo.
- **Prostorová slova v 1. fázi (30 %):** u Mulen Mara a Hofmanna 2x výrazně plnější a tmavší obraz, 2x zvrhnutí (cihlová stěna, plochá zelená). Vzorek 4 seedy, nerozhodnuto.
- **Test rozhodnutí přes Nano Pro:** blokováno OpenRouter 402 (bez kreditu). Skript: scratchpad `decisions/run.py` (není v repu).
- **Kurátor, data:** v Ateliéru nejsou žádné smazané záznamy; 10 uložených do knihovny vs 43 ostatních. Měření (`scripts/experiments/curator_measures.py`) ukázala jen slabý náznak: uložené jsou tmavší (podíl tmy AUC 0,69, v režimu noise 0,74). 10 kladných příkladů je příliš málo na rozhodnutí.
- **batch_id** (commit bc273f4): každá studie dostane id dávky, aby se mohly sbírat sourozenecké sady (co z dávky uživatel uložil). Zatím nenasazeno.

## Diagnóza, kterou držet (potvrdil uživatel)
- `SUBJECTS` jsou záměrně ploché ("cropped", "plain background", "flat light", "no surrounding context", "even daylight") -> model poslušně redukuje.
- Volná studie = čistý šum + prázdný prompt -> kompozice padá do průměru (jako dřív barva, 98 % jeden odstín).
- Kompozici určuje prvních 20-30 % kroků (hrubé masy, ne slova); na tu fázi teď nic cíleně nepůsobí.

## Zdroj D: Mario Klingemann, Neural Glitch (text od uživatele 2026-11-25 + ověřeno na quasimondo.com)
- Vlastní popis (2018): plně natrénované GANy (vlastní architektury z pix2pix/pix2pixHD) mění náhodným pozměněním, smazáním nebo prohozením vah. Glitch působí na úrovni textury i významu. Řetězí několik GANů; následující modely se poškození snaží "vyléčit" ("Neurealism"). Žádná čísla, vrstvy ani výběr výsledků v textu nejsou.
- GitHub Quasimondo: dnes hlavně ComfyUI nodes (WIP); nic o poškozování vah v diffusion. Tvrzení o sérii z roku 2026 (potlačení silných aktivací) jsem neověřil.
- Claudův převod pro aplikaci: poškodit UNet vlastního checkpointu jen v první fázi běhu (architektura), druhou fázi doběhne zdravý checkpoint (léčení = rukopis). Využije existující dvoufázový mechanismus, nepotřebuje prompty. Varianty: šum ve vahách mid bloku, prohození hlav attention, vynulování části cross-attention, potlačení nejsilnějších aktivací. GANy (pix2pix, StyleGAN) znovu stavět nedává smysl, checkpointy jsou SDXL; laboratoř na Macu není potřeba, GPU pipeline na Modalu už je.
- Verse rozhovor (2023-11-02, Teratoma): konkrétní modely ani frameworky záměrně neuvádí. Vlastní datasety ze scraperů, nejdřív ručně tříděné, pak klasifikátory na hledání dalších. Černobílost kvůli kapacitě modelu (víc textur). Dobrých výsledků bývá 1-5 %, proto chtěl stroj naučit "vidět jako já" (estetický klasifikátor, bez detailů) -> potvrzuje směr kurátor + batch_id.
- art-magazine.ai rozhovor (2026-04-25, výstava Conflict of Interest): Weapons of Mass Distraction (2026) = potlačení nebo odstranění zjevných aktivací, model se "opravuje" a znovu skládá význam z mála, co zbylo. Bez metody, vrstvy a kódu. Nástroje upravuje, aby nevznikla "vizuální monokultura" a kýč průměru. ComfyUI ani diffusion nezmiňuje; aktuální Landscapes dělá z nalezených fotografií bez AI.
- Pro aplikaci z toho: (1) potlačení nejsilnějších aktivací v první fázi běhu, druhou fázi léčí zdravý checkpoint; (2) estetický kurátor učený z vlastních voleb (batch_id už sbírá data).
