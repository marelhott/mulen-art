// Rozpad modelu: the UNet is damaged only in the first part of a run, a healthy model finishes it (app_runtime/glitch.py).
// Shared by Ateliér and by the Vari unCLIP pre-stage. "" = off, which is the default everywhere.
export const GLITCH_OPS = [
  {id: "", name: "Vypnuto"},
  {id: "top_suppress", name: "Rozpad aktivací", hint: "Nejsilnější aktivace v prvních krocích zmizí: tvary se rozbijí na střepy, rozložení, barvy a rukopis zůstanou."},
  {id: "chan_drop", name: "Vynechané kanály", hint: "Čtvrtina kanálů jednoho bloku se vypne: mírnější rozpad tvarů."},
  {id: "sa_identity", name: "Chybné čtení pozornosti", hint: "Model v prostředním bloku nečte vztahy mezi místy obrazu: stavba se jemně posune."},
];
export const GLITCH_UNTIL = {min: 0.1, max: 0.6, step: 0.05, default: 0.3};

export const glitchOp = id => GLITCH_OPS.find(item => item.id === (id || "")) || GLITCH_OPS[0];

// Request fields for a glitch; nothing at all when it is off.
export function glitchSettings(op, until) {
  if (!op) return {};
  const value = Number(until);
  return {glitch: op, glitch_until: Number.isFinite(value) ? Math.min(GLITCH_UNTIL.max, Math.max(GLITCH_UNTIL.min, value)) : GLITCH_UNTIL.default};
}
