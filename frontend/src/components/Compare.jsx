import React, { useEffect } from "react";
import { X } from "lucide-react";
import { IconButton } from "./controls";
import { buildImageUrl } from "../api";
import { TEXT } from "../texts";

// Side-by-side view of selected outputs; with one input and one seed this is a checkpoint comparison.
export function Compare({ items, modelName, onClose }) {
  useEffect(() => {
    const key = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="compare-dialog" role="dialog" aria-modal="true" aria-label={TEXT.compareTitle}
        onClick={(event) => event.stopPropagation()}>
        <header>
          <div>
            <h2>{TEXT.compareTitle}</h2>
            <p>{TEXT.compareHelp}</p>
          </div>
          <IconButton label="Zavřít porovnání" onClick={onClose}><X /></IconButton>
        </header>
        <div className="compare-grid" style={{ "--compare-columns": Math.min(items.length, 4) }}>
          {items.map((item) => {
            const settings = item.settings || {};
            return (
              <figure key={item.id}>
                <img src={buildImageUrl(item.url)} alt={`${modelName(item) || "Výstup"}, seed ${settings.seed ?? "?"}`} loading="lazy" />
                <figcaption>
                  <strong>{modelName(item) || item.model_id || "—"}</strong>
                  <span>seed {settings.seed ?? "—"} · denoise {settings.denoise ?? "—"} · CFG {settings.cfg ?? settings.guidance_scale ?? "—"}</span>
                </figcaption>
              </figure>
            );
          })}
        </div>
      </section>
    </div>
  );
}
