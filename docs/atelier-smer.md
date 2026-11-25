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
