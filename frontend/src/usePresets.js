import { useState } from "react";
import { randomId, safeStorage } from "./shared";

const PRESET_STORAGE_KEY = "img2img-presets-v1";

function loadStoredPresets() {
  try {
    const raw = safeStorage.get(PRESET_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

// Named presets of the studio controls, kept in the browser. What a preset contains (`buildPayload`) and how
// it is applied (`applyPreset`) belong to the studio state, so they are passed in.
export function usePresets({ buildPayload, applyPreset, setError }) {
  const [presets, setPresets] = useState(loadStoredPresets);
  const [presetName, setPresetName] = useState("");
  const [selectedPresetId, setSelectedPresetId] = useState("");

  function store(next) {
    setPresets(next);
    safeStorage.set(PRESET_STORAGE_KEY, JSON.stringify(next));
  }

  function handlePresetSelect(event) {
    const nextId = event.target.value;
    setSelectedPresetId(nextId);
    const preset = presets.find((item) => item.id === nextId);
    if (!preset) return;
    setPresetName(preset.name);
    applyPreset(preset);
  }

  function handleSavePreset() {
    const name = presetName.trim();
    if (!name) {
      setError("Preset name required.");
      return;
    }
    const existing = presets.find((item) => item.name.toLowerCase() === name.toLowerCase());
    const nextPreset = { id: existing?.id || randomId(), name, ...buildPayload() };
    store(existing ? presets.map((item) => (item.id === existing.id ? nextPreset : item)) : [nextPreset, ...presets]);
    setSelectedPresetId(nextPreset.id);
    setError("");
  }

  function handleDeletePreset() {
    if (!selectedPresetId) return;
    store(presets.filter((item) => item.id !== selectedPresetId));
    setSelectedPresetId("");
    setPresetName("");
  }

  return { presets, presetName, setPresetName, selectedPresetId, handlePresetSelect, handleSavePreset, handleDeletePreset };
}
