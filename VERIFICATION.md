# Ověření nasazení na Modal

Datum: 19. 10. 2026

Živá aplikace: https://mailhospodarsky--img2img-studio-web.us-east.modal.run

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

- 15 automatizovaných testů prošlo; frontend se úspěšně sestavil.
- Chráněné API odmítá nepřihlášené požadavky (401).
- Nové otevření aplikace načetlo trvalou cloudovou galerii.
- LoRA test odhalil chybějící PEFT; po doplnění peft==0.14.0 a nasazení oba testy prošly.
- Výpočet běží na Modalu, místní Mac slouží jen pro správu a prohlížeč.
- GPU má min_containers=0 a vypíná se po 20 s nečinnosti.
- Aplikační limit je 200 objednaných obrázků měsíčně; není to finanční strop Modalu.

Přihlášení: uživatel `studio`, heslo v místním souboru `.modal-app-credentials.json`.
Soubor není součástí Gitu. Zkušební výsledky jsou ponechány v galerii.

## Oficiální SDXL Base 1.0

Stažen přímo do Modalu, na Mac se neukládal. Velikost 6 938 078 334 bajtů.
SHA-256 ověřeno proti oficiálnímu repozitáři Stability AI:
`31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b`.

Zdroj: https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/sd_xl_base_1.0.safetensors
Stažení lze zopakovat pomocí `scripts/download_sdxl_base.py`.
Celkem šest modelových souborů, přibližně 26.69 GiB.

## Dávky, mřížka a průběh

- Skutečný UI test: 10 různých samostatných PNG vstupů, 2 varianty na vstup,
  všech 10 úloh dokončeno, 20 jedinečných výstupů. Testovací rozlišení 512 × 512,
  15 kroků. Všech 20 souborů šlo stáhnout; pixelová kontrola nepotvrdila prázdné výstupy.
- Podle časových intervalů pracovních úloh běžely v testu souběžně 4 GPU úlohy.
  Horní limit aplikace je 10 kontejnerů; skutečný souběh určuje i účet a kapacita Modalu.
- Každá úloha dostává právě jeden originální vstup, společné parametry a vlastní výstupy.
  Testy kontrolují limit 10 vstupů, odmítnutí vadné dávky před GPU, celkovou kvótu
  a vrácení rezervace při částečném selhání odeslání.
- Výstupy se ukládají a objevují jednotlivě za běhu. Centrální mřížka pro 20 výsledků
  používá na desktopu 5 sloupců; velikost náhledů se mění podle počtu výsledků.
- Pravý grafický pruh byl ověřen za skutečného běhu (33–45 % při částečných výsledcích).
  Dílčí kroky používají skutečný počet img2img kroků, nikoliv počet před omezením denoise.
- Po obnově stránky se obnoví aktivní/poslední dávka. Když není uložená, zobrazí
  centrální mřížka posledních 20 obrázků z trvalé galerie.
- Srovnání stejného syntetického vstupu 1024 × 1024 a 2 variant: standard 25 kroků
  měl fázi generování a ukládání 16.20 s; náhled 15 kroků 10.82 s.
  Celkové časy nejsou přímo srovnatelné: standard začínal se studeným modelem,
  náhled navázal na zahřátý kontejner. Méně kroků může změnit kvalitu.

Podrobnosti: `outputs/verification/batch-10-inputs-20-outputs.json`,
`batch-20-pixel-check.json`, `speed_25_two_images.json`, `speed_15_two_images.json`.
