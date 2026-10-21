// UI copy for the newer studio features lives here (Czech), so wording stays in one place.
export const TEXT = {
  filterModelAll: "Všechny modely",
  filterSearch: "Hledat v promptu, námětu, seedu…",
  filterEmpty: "Filtru neodpovídá žádný obrázek.",
  compare: "Porovnat",
  compareTitle: "Porovnání výstupů",
  compareHelp: "Stejný vstup a seed na různých checkpointech vedle sebe.",
  repeat: "ZOPAKOVAT S NASTAVENÍM",
  repeatDone: "Nastavení převzato; vstup je připraven.",
  exportPrint: "EXPORT PRO TISK 2×",
  budget: (spent, budget) => `Tento měsíc ≈ $${spent.toFixed(2)} z $${budget.toFixed(2)}`,
  spentOnly: (spent) => `Tento měsíc ≈ $${spent.toFixed(2)}`,
  eta: (text) => `zbývá ≈ ${text}`,
};
