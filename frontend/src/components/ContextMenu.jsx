import React, { useEffect, useRef } from "react";
import { ArrowDownToLine, ImagePlus, Maximize2, Trash2 } from "lucide-react";

// Right-click menu of an image card. Fully keyboard-operable: the first entry takes focus, arrows /
// Home / End move, Escape closes. It is kept inside the viewport whatever its real size is.
export function ContextMenu({ at, onClose, onOpen, onReuse, onDownload, onDelete }) {
  const ref = useRef(null);
  useEffect(() => {
    const entries = () => [...(ref.current?.querySelectorAll("button:not(:disabled)") || [])];
    const key = (event) => {
      if (event.key === "Escape") { event.preventDefault(); onClose(); return; }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const nodes = entries();
      const index = nodes.indexOf(document.activeElement);
      const next = event.key === "Home" ? 0 : event.key === "End" ? nodes.length - 1
        : (index + (event.key === "ArrowDown" ? 1 : -1) + nodes.length) % nodes.length;
      nodes[next]?.focus();
    };
    const box = ref.current?.getBoundingClientRect();
    if (box) {
      ref.current.style.left = `${Math.max(8, Math.min(at.x, window.innerWidth - box.width - 8))}px`;
      ref.current.style.top = `${Math.max(8, Math.min(at.y, window.innerHeight - box.height - 8))}px`;
    }
    entries()[0]?.focus();
    window.addEventListener("click", onClose);
    window.addEventListener("blur", onClose);
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("click", onClose);
      window.removeEventListener("blur", onClose);
      window.removeEventListener("keydown", key);
    };
  }, [at]);
  return (
    <div className="context-menu" ref={ref} role="menu" style={{ left: at.x, top: at.y }}>
      <button role="menuitem" onClick={onOpen}><Maximize2 />Zvětšit</button>
      <button role="menuitem" onClick={onReuse}><ImagePlus />Použít jako vstup</button>
      <button role="menuitem" onClick={onDownload}><ArrowDownToLine />Stáhnout</button>
      <button role="menuitem" onClick={onDelete}><Trash2 />Smazat obrázek</button>
    </div>
  );
}
