import React, { useState } from "react";
import { Layers3 } from "lucide-react";
import { MIX_MAX, MIX_MIN, buildMixId, normalizeWeights } from "../studioTools";

// Builds a checkpoint mix: pick 2-4 checkpoints, set how much of each, add it to the model list.
export function MixBuilder({ candidates, onAdd, defaultOpen = false }) {
  const [picked, setPicked] = useState({}); // id -> raw slider value
  const ids = candidates.map((item) => item.id).filter((id) => picked[id] !== undefined);
  const percents = normalizeWeights(ids.map((id) => picked[id]));
  const percentOf = (id) => percents[ids.indexOf(id)];
  const ready = ids.length >= MIX_MIN;

  function toggle(id) {
    setPicked((current) => {
      if (current[id] !== undefined) {
        const rest = { ...current };
        delete rest[id];
        return rest;
      }
      return Object.keys(current).length >= MIX_MAX ? current : { ...current, [id]: 50 };
    });
  }
  function add() {
    onAdd(buildMixId(ids.map((id) => ({ id, weight: picked[id] }))));
    setPicked({});
  }

  return (
    <details className="mix-builder" open={defaultOpen || undefined}>
      <summary><Layers3 size={13} aria-hidden="true" /> Fúze checkpointů</summary>
      <p className="help-text">Smíchá váhy 2–4 checkpointů do jednoho nového modelu. Vznikne položka FÚZE v seznamu výše, použitelná ve všech režimech a srovnatelná s ostatními.</p>
      <div className="mix-rows" role="group" aria-label="Checkpointy do fúze">
        {candidates.map((item) => {
          const on = picked[item.id] !== undefined;
          return (
            <div key={item.id} className={`mix-row ${on ? "on" : ""}`}>
              <button type="button" aria-pressed={on} onClick={() => toggle(item.id)} disabled={!on && ids.length >= MIX_MAX}>
                <span>{item.name}</span>
                {on && <b>{percentOf(item.id)} %</b>}
              </button>
              {on && (
                <input type="range" min="1" max="100" value={picked[item.id]} aria-label={`Podíl ${item.name}`}
                  onChange={(event) => setPicked((current) => ({ ...current, [item.id]: Number(event.target.value) }))} />
              )}
            </div>
          );
        })}
      </div>
      <button type="button" className="toolbar-button mix-add" disabled={!ready} onClick={add}>
        {ready ? "PŘIDAT FÚZI" : `VYBER ALESPOŇ ${MIX_MIN} CHECKPOINTY`}
      </button>
    </details>
  );
}
