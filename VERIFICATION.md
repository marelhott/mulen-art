# Ověření nasazení na Modal

Datum: 19. 10. 2026

## Skutečné generování na NVIDIA L4

Všechny následující běhy dokončily skutečnou CUDA inferenci (`demo_mode: false`),
uložily PNG do cloudové galerie a výstup šel stáhnout přes autentizované HTTP.
Test: syntetické zátiší, 25 kroků, denoise 0.45, CFG 5, LoRA strength 0.8.
Časy níže jsou čas pracovní funkce; nezahrnují čekání ve frontě ani celý start kontejneru.

| Checkpoint / základ | LoRA | Čas pracovní funkce | Rozlišení |
|---|---|---:|---|
| tuymans_sdxl | none | 32.31 s | 1024 × 1024 |
| tuy_small | none | 19.15 s | 1024 × 1024 |
| hofmann_sdxl | none | 15.73 s | 1024 × 1024 |
| sdxl_base | lora_tuymans_sdxl | 31.48 s | 1024 × 1024 |
| sdxl_base | lora_hofmann_sdxl | 12.14 s | 1024 × 1024 |

Aktuální dva režimy: tři vlastní checkpointy bez LoRA, nebo SDXL Base 1.0
s Tuymans/Hofmann LoRA. Obojí ověřeno skutečnou inferencí. Smíšené kombinace
vlastního checkpointu a LoRA API odmítá ještě před spuštěním GPU.
V prohlížeči bylo ověřeno přepnutí režimu a odpovídající nabídky.
Nejde o posouzení výtvarné kvality na vlastních fotografiích.
Jednotlivé JSON záznamy a PNG jsou v `outputs/verification/` (ignorováno Gitem).

## Přenos modelů

Všech pět souborů bylo znovu ověřeno plným SHA-256 přímo na Modalu proti místním
souborům v `/Users/mulenmara/CODE_DISK/models`. Celkem přibližně 20.23 GiB.
Přenos použil existující R2 kopie tensorů a místní metadata hlavičky; výsledné
soubory jsou bajtově shodné s místními originály. Zálohy `.bak` se nepřenášely.

## Další kontroly

- 19 automatizovaných testů prošlo; frontend se úspěšně sestavil.
- Chráněné API odmítá nepřihlášené požadavky (401).
- Nové otevření aplikace načetlo trvalou cloudovou galerii.
- LoRA test odhalil chybějící PEFT; po doplnění peft==0.14.0 a nasazení oba testy prošly.
- Výpočet běží na Modalu, místní Mac slouží jen pro správu a prohlížeč.
- GPU má min_containers=0 a vypíná se po 20 s nečinnosti.
- Měsíční aplikační strop byl odstraněn; produkční `/api/usage` ověřeno s `limit: null`.
- Per-model workery (2026-10-21): 12 úloh ve dvou modelech běželo nejvýš po 10 (špička 10 slotů), zrušená
  čekající úloha se nespustila, fronta i sloty skončily prázdné; Atelier foto a 1536 detail po jiném
  modelu doběhly. Volitelný rozpočet: `MONTHLY_BUDGET_USD` (viz README).

Zkušební výsledky jsou ponechány v galerii.

## Oficiální SDXL Base 1.0

Stažen přímo do Modalu, na Mac se neukládal. Velikost 6 938 078 334 bajtů.
SHA-256 ověřeno proti oficiálnímu repozitáři Stability AI:
`31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b`.

Zdroj: https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/sd_xl_base_1.0.safetensors
Stažení lze zopakovat pomocí `scripts/download_sdxl_base.py`.
Celkem šest modelových souborů, přibližně 26.69 GiB.

## Původní ověření dávek před změnou designu

- Skutečný UI test: 10 různých samostatných PNG vstupů, 2 varianty na vstup,
  všech 10 úloh dokončeno, 20 jedinečných výstupů. Testovací rozlišení 512 × 512,
  15 kroků. Všech 20 souborů šlo stáhnout; pixelová kontrola nepotvrdila prázdné výstupy.
- Podle časových intervalů pracovních úloh běžely v testu souběžně 4 GPU úlohy.
  Horní limit aplikace je 10 kontejnerů; skutečný souběh určuje i účet a kapacita Modalu.
- Každá úloha dostává právě jeden originální vstup, společné parametry a vlastní výstupy.
  Nové testy ověřují 12 vstupů × 21 variant = 252 samostatných GPU objednávek bez
  měsíčního stropu, odmítnutí vadného vstupu a vrácení rezervace při selhání odeslání.
- Výstupy se ukládají a objevují jednotlivě za běhu. Centrální mřížka pro 20 výsledků
  používá na desktopu 5 sloupců; velikost náhledů se mění podle počtu výsledků.
- Pravý grafický pruh byl ověřen za skutečného běhu (33–45 % při částečných výsledcích).
  Dílčí kroky používají skutečný počet img2img kroků, nikoliv počet před omezením denoise.
- Po obnově stránky se obnoví aktivní/poslední dávka. Když není uložená, zobrazí
  aktuální centrální mřížka celou trvalou galerii, postupně při posouvání.
- Srovnání stejného syntetického vstupu 1024 × 1024 a 2 variant: standard 25 kroků
  měl fázi generování a ukládání 16.20 s; náhled 15 kroků 10.82 s.
  Celkové časy nejsou přímo srovnatelné: standard začínal se studeným modelem,
  náhled navázal na zahřátý kontejner. Méně kroků může změnit kvalitu.

Podrobnosti: `outputs/verification/batch-10-inputs-20-outputs.json`,
`batch-20-pixel-check.json`, `speed_25_two_images.json`, `speed_15_two_images.json`.

## Mulen Nano design a odstranění počtových limitů

- Před změnou uložen commit `d292249` a anotovaný tag
  `studio-before-mulen-nano-2026-10-19`. Nová větev: `codex/mulen-nano-studio`.
- Produkční `/api/usage` vrací `limit: null`. Počet vstupů, variant a měsíčních
  výstupů nemá aplikační strop. Souběh workerů zůstává řízený kapacitou Modalu.
- Automatizovaný test 12 vstupů × 21 variant ověřil 252 samostatných objednávek
  bez spuštění placené inference; varianty se neomezují na původní čtyři.
- Skutečný test v novém UI: 12 různých syntetických vstupů, 512 × 512, 15 kroků,
  Tuymans SDXL bez LoRA, všech 12 výsledků dokončeno. UI zobrazilo 100 % / 12 z 12.
- V živém detailu ověřen zoom 100 → 150 %, přechod na další obrázek, Escape,
  zdrojový obrázek a porovnání posuvníkem 50 → 51 %. Zdroj je chráněný stejným
  přihlášením; test potvrzuje dostupnost po restartu gatewaye a vyloučení z galerie.
- Test čekající fronty potvrzuje, že úloha neexpiruje pouze kvůli stáří objednávky.
- Vizuální vzor ověřen v nasazeném Mulen Nano a ve zdrojových komponentách
  ImageDetailModal, ImageGalleryPanel, LoadingProgress a src/index.css.
- Druhý skutečný UI test vytvořil 5 variant z jednoho vstupu (512 × 512, 15 kroků),
  všech 5 dokončeno. Tím ověřeno překročení původní hranice 4 variant.
- Vybrány dvě miniatury a skutečně stažen ZIP; kontrola `ZipFile.testzip()` bez chyby,
  v archivu právě 2 obrázky. Ověřen posuvník miniatur na 100 px a světlý režim.
- Prohlížeč po ověření nehlásil chyby v konzoli. Souhrn ověření 12 vstupů a jejich
  uložených zdrojů je v `outputs/verification/mulen-nano-design-live.json`.
