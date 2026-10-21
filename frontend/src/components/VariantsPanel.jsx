import React from "react";
import { GitBranch } from "lucide-react";
import { VARIANT_DISTANCES, describeVariant } from "../studioTools";
import { Label } from "./controls";

// "Varianty" (from Mulen Nano): siblings of one input. A checkbox section that works together with the
// checkpoint choice, the settings and the fusion weights above it, and shows exactly what each sibling gets.
export function VariantsPanel({ value, onChange, plan, models }) {
  const update = (patch) => onChange({ ...value, ...patch });
  const distance = VARIANT_DISTANCES.find((item) => item.id === value.distance) || VARIANT_DISTANCES[1];
  return (
    <div className={`control-block variants-panel ${value.enabled ? "on" : ""}`}>
      <label className="variants-toggle">
        <input type="checkbox" checked={value.enabled} onChange={(event) => update({ enabled: event.target.checked })} />
        <GitBranch size={14} aria-hidden="true" />
        <span>
          <b>Varianty · sourozenci</b>
          <small>Každá varianta dostane jiný seed, nastavení, váhy fúze a pokyn.</small>
        </span>
      </label>
      {value.enabled && (
        <>
          <Label>VZDÁLENOST</Label>
          <div className="source-switch four" role="group" aria-label="Vzdálenost variant">
            {VARIANT_DISTANCES.map((item) => (
              <button key={item.id} type="button" aria-pressed={value.distance === item.id} title={item.hint} onClick={() => update({ distance: item.id })}>{item.label}</button>
            ))}
          </div>
          <p className="help-text">{distance.hint}</p>
          <label className="control-block">
            <Label>OBECNÝ PROMPT · VOLITELNÝ</Label>
            <textarea className="variants-prompt" rows={3} maxLength={300} value={value.prompt} aria-label="Obecný prompt variant"
              placeholder="Nic: použije se jen vzdálenost a pokyn varianty"
              onChange={(event) => update({ prompt: event.target.value })} />
          </label>
          <label className="control-block">
            <Label>NEGATIVNÍ PROMPT · VOLITELNÝ</Label>
            <input type="text" className="variants-negative" maxLength={200} value={value.negative} aria-label="Negativní prompt variant"
              onChange={(event) => update({ negative: event.target.value })} />
          </label>
          <label className="control-block range-field">
            <span className="label-row"><Label>ROZPTYL VAH A NASTAVENÍ</Label><output>{Math.round(value.spread * 100)} %</output></span>
            <input type="range" min={0} max={1} step={0.05} value={value.spread} aria-label="Rozptyl vah a nastavení"
              onChange={(event) => update({ spread: Number(event.target.value) })} style={{ "--range-fill": `${value.spread * 100}%` }} />
            <span className="help-text">0 % = stejné nastavení a váhy, mění se jen seed a pokyn. Výš = víc se liší denoise, CFG a váhy fúze.</span>
          </label>
          <Label>AKTIVNÍ VARIANTY · PRVNÍ MODEL</Label>
          <ol className="variants-plan" aria-label="Aktivní varianty">
            {plan.map((variant) => {
              const info = describeVariant(variant, models);
              return (
                <li key={variant.index}>
                  <b>#{variant.index + 1}</b> <span>{info.text}</span>
                  {info.name && <em>{info.name}</em>}
                  <q title={variant.prompt}>{variant.prompt}</q>
                </li>
              );
            })}
          </ol>
        </>
      )}
    </div>
  );
}
