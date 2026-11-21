import React from "react";
import { Shuffle } from "lucide-react";
import { Label, Range, Select } from "./controls";
import { presetLabel, REIMAGINE_MODES, REIMAGINE_PRESETS } from "../reimagineTools";

// unCLIP tab: "Varianta" (SD 2.1 unCLIP, faithful) or "Metamorfóza" (SDXL + IP-Adapter, the old Reimagine XL behaviour).
export function ReimagineControls({value: r, update, inputCount, generating, onGenerate, inputBlock}) {
  const metamorph = r.mode === "metamorph";
  const presets = Boolean(r.usePresets);
  const presetList = REIMAGINE_PRESETS[r.mode] || REIMAGINE_PRESETS.unclip;
  const total = inputCount * (presets ? presetList.length : Number(r.count || 0));
  const mode = REIMAGINE_MODES.find(item => item.id === r.mode) || REIMAGINE_MODES[0];
  return <>
    <button className="primary-button generate" disabled={!inputCount} onClick={onGenerate}>
      <Shuffle size={16} />{generating ? "PŘIDAT DO FRONTY" : metamorph ? "VYTVOŘIT METAMORFÓZY" : "VYTVOŘIT VARIANTY"}
    </button>
    <div className="control-block">
      <Label>REŽIM</Label>
      <div className="segmented" role="group" aria-label="Režim unCLIP">
        {REIMAGINE_MODES.map(item => <button key={item.id} aria-pressed={r.mode === item.id} onClick={() => update({mode: item.id})}>{item.name}</button>)}
      </div>
      <span className="help-text">{mode.description}</span>
    </div>
    {inputBlock}
    <label className="variants-toggle realsr-toggle">
      <input type="checkbox" checked={presets} onChange={event => update({usePresets: event.target.checked})} />
      <span><b>Sada přednastavení</b><small>Každý obrázek vznikne najednou ve {presetList.length} verzích se stejným seedem, takže je lze porovnat. Vypnuto = vlastní nastavení níže.</small></span>
    </label>
    {presets && <ul className="help-text" aria-label="Přednastavení">{presetList.map(preset => <li key={preset.id}>{presetLabel(preset)}</li>)}</ul>}
    {presets && <p className="help-text">{inputCount ? `${inputCount} × ${presetList.length} = ${total} výstupů` : "Přidej obrázek, ze kterého se verze odvodí."}</p>}
    {!presets && <Range label="POČET VARIANT NA OBRÁZEK" min={1} max={16} step={1} value={r.count} onChange={count => update({count})}
      hint={inputCount ? `${inputCount} × ${r.count} = ${total} výstupů` : "Přidej obrázek, ze kterého se varianty odvodí."} />}
    {!presets && !metamorph && <>
      <Range label="SÍLA PŘEPRACOVÁNÍ" min={0.3} max={1} step={0.05} value={r.strength} onChange={strength => update({strength})}
        hint={r.strength >= 0.99 ? "1 · nová kompozice z šumu, drží se jen obsah a styl" : r.strength <= 0.6 ? "Nižší · zachová rozložení, tahy štětce a barevné plochy předlohy" : "Střední · drží kompozici předlohy, mění tvary a detaily"} />
      <Range label="ODCHYLKA OD PŘEDLOHY" min={0} max={500} step={10} value={r.noise} onChange={noise => update({noise})}
        hint={r.noise === 0 ? "0 · model chápe obsah předlohy přesně" : "Volnější výklad obsahu předlohy; kompozici řídí síla přepracování"} />
    </>}
    {!presets && metamorph && <>
      <Range label="SÍLA PROMĚNY" min={0.5} max={0.98} step={0.01} value={r.mStrength} onChange={mStrength => update({mStrength})}
        hint={r.mStrength < 0.8 ? "Nižší · tvary se mění jen málo, blízko předloze" : r.mStrength < 0.9 ? "Střední · předměty se mění v jiné, kompozice a paleta drží" : "Vysoká · odvážná proměna, z předlohy zbývá hlavně rozložení a barvy"} />
      <Range label="VLIV OBRAZU" min={0.2} max={1} step={0.05} value={r.ipScale} onChange={ipScale => update({ipScale})}
        hint="Jak silně obsah a styl předlohy řídí nové tvary. Vyšší = víc z předlohy, nižší = víc fantazie modelu." />
      <Select label="IP-ADAPTER" value={r.ipVariant} onChange={ipVariant => update({ipVariant})}
        items={[{id: "plain", name: "Základní · skutečná proměna"}, {id: "plus", name: "Plus · drží předlohu téměř doslova"}]} />
    </>}
    {!metamorph && <Select label="ROZLIŠENÍ" value={String(r.longSide)} onChange={value => update({longSide: Number(value)})}
      items={[{id: "1024", name: "1024 px na delší straně · víc detailu"}, {id: "768", name: "768 px · nativní velikost modelu"}]} />}
    <Range label="KROKY" min={10} max={50} step={1} value={metamorph ? r.mSteps : r.steps} onChange={value => update(metamorph ? {mSteps: value} : {steps: value})} />
    <Range label="CFG" min={1} max={metamorph ? 12 : 20} step={0.5} value={metamorph ? r.mCfg : r.cfg} onChange={value => update(metamorph ? {mCfg: value} : {cfg: value})}
      hint={metamorph ? "Výchozí 5,5. Vyšší hodnoty přidávají kontrast a ostrost." : "Výchozí 5. Hodnoty nad 7 zjednodušují plochy a přidávají nesmyslné figury."} />
    <label className="control-block">
      <Label>SEED</Label>
      <input type="number" aria-label="Seed" min={-1} max={4294967295} step={1} value={r.seed} onChange={event => update({seed: event.target.value})} />
      <span className="help-text">−1 = náhodný. Další varianty používají po sobě jdoucí seedy.</span>
    </label>
    <p className="help-text">{metamorph
      ? "SDXL Base, kolem 1 megapixelu v poměru stran předlohy. Bez promptu: proměnu řídí sama předloha. Nejbližší veřejná náhrada Clipdrop Reimagine XL, jehož model nebyl zveřejněn."
      : "SD 2.1 unCLIP, model původního Clipdrop Reimagine z roku 2023. Bere obrázek, ne text, takže se nepíše žádný prompt."}</p>
  </>;
}
