import React from "react";
import { Shuffle } from "lucide-react";
import { Label, Range } from "./controls";
import { REIMAGINE_PRESETS } from "../reimagineTools";

// unCLIP (formerly Clipdrop Reimagine): variations of one picture with Stable Diffusion 2.1 unCLIP. The model reads the picture, not a prompt.
export function ReimagineControls({value: r, update, inputCount, generating, onGenerate, inputBlock}) {
  const presets = Boolean(r.usePresets);
  const total = inputCount * (presets ? REIMAGINE_PRESETS.length : Number(r.count || 0));
  return <>
    <button className="primary-button generate" disabled={!inputCount} onClick={onGenerate}>
      <Shuffle size={16} />{generating ? "PŘIDAT DO FRONTY" : "VYTVOŘIT VARIANTY"}
    </button>
    {inputBlock}
    <label className="variants-toggle realsr-toggle">
      <input type="checkbox" checked={presets} onChange={event => update({usePresets: event.target.checked})} />
      <span><b>Sada přednastavení</b><small>Každý obrázek vznikne najednou ve {REIMAGINE_PRESETS.length} verzích, které se liší silou přepracování a odchylkou. Stejný seed, takže je lze porovnat. Vypnuto = vlastní nastavení níže.</small></span>
    </label>
    {presets && <ul className="help-text" aria-label="Přednastavení">{REIMAGINE_PRESETS.map(preset => <li key={preset.id}>{preset.name} · síla {String(preset.denoise).replace(".", ",")}{preset.noise ? ` · odchylka ${preset.noise}` : ""}</li>)}</ul>}
    {presets && <p className="help-text">{inputCount ? `${inputCount} × ${REIMAGINE_PRESETS.length} = ${total} výstupů` : "Přidej obrázek, ze kterého se verze odvodí."}</p>}
    {!presets && <Range label="POČET VARIANT NA OBRÁZEK" min={1} max={16} step={1} value={r.count} onChange={count => update({count})}
      hint={inputCount ? `${inputCount} × ${r.count} = ${total} výstupů` : "Přidej obrázek, ze kterého se varianty odvodí."} />}
    {!presets && <Range label="SÍLA PŘEPRACOVÁNÍ" min={0.3} max={1} step={0.05} value={r.strength} onChange={strength => update({strength})}
      hint={r.strength >= 0.99 ? "1 · nová kompozice z šumu, drží se jen obsah a styl" : r.strength <= 0.6 ? "Nižší · zachová rozložení, tahy štětce a barevné plochy předlohy" : "Střední · drží kompozici předlohy, mění tvary a detaily"} />}
    {!presets && <Range label="ODCHYLKA OD PŘEDLOHY" min={0} max={500} step={10} value={r.noise} onChange={noise => update({noise})}
      hint={r.noise === 0 ? "0 · věrné varianty se stejným námětem a barvami" : r.noise < 200 ? "Mírné odchylky v detailech a kompozici" : "Volná interpretace · výsledek se od předlohy výrazně liší"} />}
    <Range label="KROKY" min={10} max={50} step={1} value={r.steps} onChange={steps => update({steps})} />
    <Range label="CFG" min={1} max={20} step={0.5} value={r.cfg} onChange={cfg => update({cfg})}
      hint="Výchozí 10 odpovídá původnímu Reimagine." />
    <label className="control-block">
      <Label>SEED</Label>
      <input type="number" aria-label="Seed" min={-1} max={4294967295} step={1} value={r.seed} onChange={event => update({seed: event.target.value})} />
      <span className="help-text">−1 = náhodný. Další varianty používají po sobě jdoucí seedy.</span>
    </label>
    <p className="help-text">SD 2.1 unCLIP, výstup do 768 px na delší straně. Model bere obrázek, ne text, takže se nepíše žádný prompt. Obnova původního nástroje Clipdrop Reimagine z roku 2023, bez zvětšení.</p>
  </>;
}
