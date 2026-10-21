import React from "react";
import { Check, X } from "lucide-react";
import { Label } from "./controls";
import { MixBuilder } from "./MixBuilder";
import { idsForSource } from "../studioTools";

// Model choice with two mutually exclusive sources: individual checkpoints OR fusions.
// The inactive source is hidden and ignored by generation, so the two can never be on together.
export function CheckpointPicker({ label, items, selectedIds, onChange, source, onSourceChange, onAddMix, onRemoveMix, mixCandidates, hint }) {
  const singles = items.filter((item) => item.kind !== "mix");
  const mixes = items.filter((item) => item.kind === "mix");
  const shown = source === "mix" ? mixes : singles;
  const active = idsForSource(selectedIds, source);
  const others = selectedIds.filter((id) => !active.includes(id));

  function toggle(id) {
    const next = active.includes(id) ? active.filter((item) => item !== id) : [...active, id];
    if (source === "single" && !next.length) return; // a plain list always keeps one checkpoint
    onChange([...others, ...next]);
  }
  function switchTo(next) {
    if (next === source) return;
    onSourceChange(next);
    if (next === "single" && !idsForSource(selectedIds, "single").length && singles[0]) onChange([...selectedIds, singles[0].id]);
  }

  return (
    <div className="control-block">
      <Label>{label}</Label>
      <div className="source-switch" role="group" aria-label="Zdroj modelů">
        <button type="button" aria-pressed={source === "single"} onClick={() => switchTo("single")}>Jednotlivé</button>
        <button type="button" aria-pressed={source === "mix"} onClick={() => switchTo("mix")}>Fúze</button>
      </div>
      <div className="checkpoint-options" role="group" aria-label={source === "mix" ? "Fúze checkpointů" : "Checkpointy"}>
        {shown.map((item) => (
          <div key={item.id} className={`checkpoint-row ${item.kind === "mix" ? "is-mix" : ""}`}>
            <button aria-pressed={active.includes(item.id)} onClick={() => toggle(item.id)}>
              <span>{item.kind === "mix" && <i className="mix-tag">FÚZE</i>}{item.kind === "mix" ? item.name.replace(/^Fúze: /, "") : item.name}</span>
              {active.includes(item.id) && <Check size={14} />}
            </button>
            {item.kind === "mix" && (
              <button type="button" className="mix-remove" aria-label={`Odebrat fúzi ${item.name}`} title="Odebrat fúzi" onClick={() => onRemoveMix(item.id)}><X size={12} /></button>
            )}
          </div>
        ))}
        {source === "mix" && !mixes.length && <p className="help-text mix-empty">Zatím žádná fúze. Vytvoř ji níže.</p>}
      </div>
      {source === "mix" && <MixBuilder candidates={mixCandidates} onAdd={onAddMix} defaultOpen={!mixes.length} />}
      {source === "mix" && mixes.length > 0 && !active.length && <p className="help-text">Vyber alespoň jednu fúzi, jinak není co generovat.</p>}
      {hint && <p className="help-text">{hint}</p>}
    </div>
  );
}
