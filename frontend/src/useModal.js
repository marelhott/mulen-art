import { useEffect } from "react";

const FOCUSABLE = 'button:not(:disabled),[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex]:not([tabindex="-1"])';

// Modal behaviour shared by dialogs: page scroll lock, focus moved in and restored afterwards, Tab kept
// inside, Escape closes. `suspended` pauses the keys while another layer (a viewer opened over a dialog)
// is on top, so one Escape closes only the topmost layer.
export function useModal(ref, active, onClose, suspended = false) {
  useEffect(() => {
    if (!active) return undefined;
    const previous = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    ref.current?.querySelector(FOCUSABLE)?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      previous?.focus?.();
    };
  }, [active, ref]);
  useEffect(() => {
    if (!active || suspended) return undefined;
    const key = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      } else if (event.key === "Tab" && ref.current) {
        const nodes = [...ref.current.querySelectorAll(FOCUSABLE)].filter((node) => node.getClientRects().length);
        if (!nodes.length) return;
        if (event.shiftKey && document.activeElement === nodes[0]) {
          event.preventDefault();
          nodes.at(-1).focus();
        } else if (!event.shiftKey && document.activeElement === nodes.at(-1)) {
          event.preventDefault();
          nodes[0].focus();
        }
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [active, suspended, onClose, ref]);
}
