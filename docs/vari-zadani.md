# Co hledám (zadání pro nejvýkonnější modely)

Srovnání: `docs/vari-srovnani.jpg` (vlevo zdroj, vpravo cíl, vznikl z levého starým modelem).

## 1. Krátké zadání pro model, který má pomoct najít cestu

Vlož spolu s oběma obrázky.

> Jsem malíř. Nehledám realismus ani dokonalost; tou se generátory obrazu honí a mě nezajímá. Hledám něco, co jsem nazval **posun**: z obrazu, který mu dám, udělat jeho verzi, která zachová **kostru** (kompozici, rozložení velkých tvarů, horizont, paletu a médium) a změní **to, čím věci jsou**. Výsledek nesmí být rozpoznatelné místo, les, zvíře ani člověk. Je to věrohodné nikde.
>
> Na přiložených dvou obrázcích je příklad. Obraz 1 je zdroj: starý tisk říčního parníku, přemalovaný růžovými a černými tahy štětcem. Obraz 2 je výsledek starého modelu. Všimni si, co se stalo: růžové tahy se staly vybělenými kmeny podobnými kosti nebo naplaveninám, černý tah ohořelým sloupem s chlupatým okrajem, parník a kouř nízkými dřevěnými kůlnami s mostem a tmavou hmotou oblaka, obloha dostala jemné vodorovné čárkování jako rytina nebo vodní vlnky, dole přibyla tmavá hladina se svislým rozmazaným odrazem. Povrch je plochý, redukovaný, s tvrdými hranami jako vystřižené kusy papíru položené na tisk, s viditelnými švy, málo detailu, měkký a lehce zrnitý jako zvětšený sken tisku.
>
> Nechci kopii tohoto příkladu. Chci pochopit logiku a umět ji znovu vyvolat na jiných zdrojích.
>
> Úkol: (1) Popiš pravidlo, kterým se zdroj proměnil, obecně, ne pro tenhle obraz. (2) Napiš prompt pro nejvýkonnější generátory obrazu (Nano Banana Pro, GPT Image, Seedream, FLUX a další), který to dá. (3) Napiš variantu pro modely, které umí víc referenčních obrázků: obraz 1 před, obraz 2 po, obraz 3 nový zdroj. (4) Řekni, kde se generátory vrátí k rozpoznatelnému prototypu a lesku, a jak tomu v promptu zabránit.

## 2. Prompt pro generátor obrazu (jeden zdrojový obrázek)

Přilož jen zdroj.

```
Make a displaced version of this picture: the same picture, but in a place that does not exist.

KEEP: the composition and the placement of the large masses (two tall upright shapes, one heavy dark mass low in the centre, the horizon, water along the bottom), the colour palette (desaturated grey-green and teal, black, bleached pink), and the medium: an old printed image with a painted gesture on it.

CHANGE WHAT EVERYTHING IS. Read every object and every brush mark as something else, of another material:
- the pink brush strokes become pale, bleached, bone-like or driftwood-like trunks and limbs with broken tops
- the black brush mass becomes a tall charred black pillar with a rough, furry edge
- one part of the sky becomes a heavy, dark cloud mass, another a flat patch of pink; the lighter sky carries fine horizontal striations, like ripples on water or an engraved print
- the steamboat and its smoke become low wooden sheds and a bridge along the horizon, and the smoke a dense dark cloud
- the lower part becomes a dark water surface with vertical, smeared reflections of the shapes above it
Nothing may read as a real, recognisable place, forest, plant, animal or person. A plausible nowhere.

HOW IT LOOKS: flat, reduced, hard-edged areas, like cut-out paper pieces laid on a print, with visible hard seams where the pieces meet. Little fine detail. Soft, low-resolution, slightly grainy, like a magazine print scanned and enlarged. NOT photorealistic, NOT glossy, NOT hyper-detailed, NOT symmetrical, NOT polished digital painting, NOT fantasy or horror art, NOT beautiful in the usual AI way. Imperfection is wanted. No text, no frame. Output one image in the aspect ratio of the source.
```

## 3. Obecná šablona (pro jiné zdroje)

Doplň místo ukázek vlastní. Princip: **tahy a předměty se přečtou jako jiná hmota, obloha jako jiný povrch, stroje a stavby jako jiné stavby, přibude odraz.**

```
Make a displaced version of this picture: the same picture, but in a place that does not exist.
KEEP the composition, the placement of the large masses, the horizon, the proportions, the palette and the medium.
CHANGE WHAT EVERYTHING IS: read every object, figure and mark as something else, of another material (e.g. {marks} become {matter}; the sky becomes {another surface}; {machines or buildings} become {other structures}). Add a dark water surface or another reflecting plane with smeared reflections if the layout allows it.
Nothing may read as a real, recognisable place, plant, animal or person.
LOOK: flat, reduced, hard-edged areas like cut-out paper on a print, visible seams, little detail, soft, low-resolution, slightly grainy. NOT photorealistic, NOT glossy, NOT hyper-detailed, NOT symmetrical, NOT polished digital painting, NOT fantasy or horror art. Imperfection is wanted. One image, same aspect ratio.
```

## 4. Varianta pro modely s více referencemi (příklad před a po)

Přilož tři obrázky: 1 příklad před, 2 příklad po, 3 nový zdroj.

```
Image 1 is a source picture. Image 2 is what was done to it: the same picture displaced into a place that does not exist. Study the logic of the change, not the objects: the composition, masses and palette were kept; every object and mark was reread as something else of another material; the sky became another surface; machines became other structures; a reflection appeared; the surface became flat, reduced and hard-edged like cut-out paper on a print, with visible seams, little detail, soft and slightly grainy.
Do the same kind of transformation to image 3. Do NOT copy the objects of image 2 (no bones, sheds or pillars unless image 3 suggests them); invent new rereadings that fit image 3's own shapes. Nothing may be a recognisable real place, plant, animal or person. Not photorealistic, not glossy, not hyper-detailed. One image, same aspect ratio as image 3.
```

## 5. Dvě cesty

1. **Správný model, váhy a nastavení.** Výchozí obraz „sourozence“ nestačí: modely sáhnou po nejpravděpodobnější věci. Zkoušel jsem unCLIP, Metamorfózu a modely z Vari. Nejlépe vyšel Posun s Nano Pro a Gemini, případně po mezikroku unCLIP. Nepodařilo se plochost, tvrdé hrany a posun celého místa.
2. **Nejlepší generátory s dobrým promptem.** Výše uvedené prompty. Kde to padá: Grok a Seedream jdou do hyperdetailu a fotorealismu, Qwen do fotorealistického dřeva a moře, Nano Pro do lesklé „AI“ malby. Proto je v promptu seznam toho, co nechceš, a požadavek na plochost, švy a nízké rozlišení.
