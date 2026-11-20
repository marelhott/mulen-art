import React, { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { useModal } from "../useModal";
import { ImageCard } from "./ImageCard";
import { IconButton } from "./controls";

const PAGE = 120;

// The saved-image library as a modal. Renders PAGE cards at a time so a large library stays light.
export function LibraryDialog({ open, onClose, suspended, items, models, actions }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(PAGE);
  useModal(ref, open, onClose, suspended);
  useEffect(() => { if (open) setVisible(PAGE); }, [open]);
  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="library-dialog" ref={ref} role="dialog" aria-modal="true" aria-label="Knihovna obrázků" onClick={(event) => event.stopPropagation()}>
        <header>
          <div>
            <h2>Knihovna</h2>
            <p>{items.length} výsledků · přetáhni nebo přidej do vstupů</p>
          </div>
          <IconButton label="Zavřít knihovnu" onClick={onClose}><X /></IconButton>
        </header>
        <div className="library-dialog-grid">
          {items.slice(0, visible).map((item, index) => (
            <ImageCard
              key={item.id}
              item={item}
              modelName={models.find((model) => model.id === (item?.model_id || item?.settings?.model_id))?.name}
              index={index}
              actions={actions}
              canDelete={true}
            />
          ))}
        </div>
        {items.length > visible && (
          <button className="toolbar-button library-more" onClick={() => setVisible((n) => n + PAGE)}>
            Zobrazit další ({items.length - visible})
          </button>
        )}
      </section>
    </div>
  );
}
