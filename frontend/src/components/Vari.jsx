import React from "react";
import { Layers3 } from "lucide-react";
import { Label, Range } from "./controls";
import { VARI_DISTANCES, availableEngines, plannedVariImages, planVari } from "../variTools";

// Vari: variations of one picture through fal, Replicate, OpenAI and Gemini (formerly the standalone Vari app).
export function VariControls({value: v, update, engines, inputCount, generating, onGenerate, inputBlock}) {
  const usable = availableEngines(engines);
  const selected = engines.find(engine => engine.id === v.engineId);
  const plan = planVari(v, engines);
  const perInput = plannedVariImages(plan);
  const engineCount = v.allEngines ? usable.length : selected?.available ? 1 : 0;
  const distanceCount = v.allDistances ? VARI_DISTANCES.length : 1;
  const setTuning = (key, value) => update({tuning: {...v.tuning, [key]: value}});
  return <>
    <button className="primary-button generate" disabled={!inputCount || !plan.length} onClick={onGenerate}>
      <Layers3 size={16} />{generating ? "PŘIDAT DO FRONTY" : "VYTVOŘIT VARIANTY"}
    </button>
    {inputBlock}
    <div className="control-block">
      <Label>ENGINE</Label>
      {engines.length === 0 && <p className="help-text">Seznam enginů se načítá…</p>}
      {engines.map(engine => <button key={engine.id} className="atelier-mode" aria-pressed={!v.allEngines && v.engineId === engine.id}
        disabled={!engine.available || v.allEngines} onClick={() => update({engineId: engine.id})}>
        <span>{engine.name}</span>
        <small>{engine.available ? engine.provider : `nedostupný · chybí ${engine.missing.join(", ")}`}</small>
      </button>)}
    </div>
    <label className="variants-toggle realsr-toggle">
      <input type="checkbox" checked={v.allEngines} onChange={event => update({allEngines: event.target.checked})} />
      <span><b>Všechny dostupné enginy</b><small>{usable.length} enginů najednou. Každý dostane stejný zdroj a stejnou vzdálenost, takže je lze porovnat.</small></span>
    </label>
    <div className="control-block">
      <Label>VZDÁLENOST OD PŘEDLOHY</Label>
      <div className="segmented" role="group" aria-label="Vzdálenost od předlohy">
        {VARI_DISTANCES.map(item => <button key={item.id} aria-pressed={!v.allDistances && v.distance === item.id} disabled={v.allDistances} onClick={() => update({distance: item.id})}>{item.name}</button>)}
      </div>
      <span className="help-text">{v.allDistances ? "Všechny čtyři vzdálenosti najednou." : VARI_DISTANCES.find(item => item.id === v.distance)?.hint}</span>
    </div>
    <label className="variants-toggle realsr-toggle">
      <input type="checkbox" checked={v.allDistances} onChange={event => update({allDistances: event.target.checked})} />
      <span><b>Všechny 4 vzdálenosti</b><small>Od těsné variace po nový záběr stejného světa.</small></span>
    </label>
    <Range label="POČET OBRÁZKŮ" min={1} max={12} step={1} value={v.count} onChange={count => update({count})}
      hint={inputCount ? `${inputCount} × ${engineCount} enginů × ${distanceCount} vzdáleností × ${v.count} = ${inputCount * perInput} obrázků` : "Přidej obrázek, ze kterého se varianty odvodí."} />
    {!v.allEngines && selected?.available && selected.tuning.length > 0 && <details className="control-block">
      <summary><Label>LADĚNÍ ENGINU</Label></summary>
      {selected.tuning.map(item => <Range key={item.key} label={item.label.toUpperCase()} min={item.min} max={item.max} step={item.step}
        value={Number.isFinite(v.tuning[item.key]) ? v.tuning[item.key] : item.min} onChange={value => setTuning(item.key, value)} />)}
      <p className="help-text">{Object.keys(v.tuning).length ? "Vlastní hodnoty se pošlou místo výchozích." : "Dokud nic nepohneš, platí výchozí hodnoty podle vzdálenosti."}</p>
      {Object.keys(v.tuning).length > 0 && <button className="text-button" onClick={() => update({tuning: {}})}>Vrátit výchozí hodnoty</button>}
    </details>}
    <p className="help-text">Výsledky se ukládají do knihovny studia. Volání poskytovatelů se účtují na tvých klíčích (fal, Replicate, OpenAI, Gemini).</p>
  </>;
}
