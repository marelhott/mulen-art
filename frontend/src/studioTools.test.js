import test from "node:test";
import assert from "node:assert/strict";
import { filterItems, averageWorkerSeconds, etaSeconds, formatEta, etaLabel, usageLabel, controlsFromSettings, creationMode } from "./studioTools.js";

const items = [
  { id: "a", model_id: "m1", settings: { prompt: "red fox", seed: 42, worker_seconds: 20 } },
  { id: "b", model_id: "m2", settings: { subject_title: "Zátiší", seed: 7, worker_seconds: 40 } },
  null,
];

test("filterItems keeps everything (and placeholders) without a filter", () => {
  assert.equal(filterItems(items, {}), items);
});

test("filterItems narrows by model and by text over prompt, subject and seed", () => {
  assert.deepEqual(filterItems(items, { modelId: "m2" }).map((i) => i.id), ["b"]);
  assert.deepEqual(filterItems(items, { text: "FOX" }).map((i) => i.id), ["a"]);
  assert.deepEqual(filterItems(items, { text: "zátiší" }).map((i) => i.id), ["b"]);
  assert.deepEqual(filterItems(items, { text: "42" }).map((i) => i.id), ["a"]);
  assert.deepEqual(filterItems(items, { modelId: "m1", text: "zátiší" }), []);
});

test("ETA uses average GPU seconds and the parallel job cap", () => {
  assert.equal(averageWorkerSeconds(items), 30);
  assert.equal(averageWorkerSeconds([]), null);
  assert.equal(etaSeconds({ remainingJobs: 25, parallel: 10, averageSeconds: 30 }), 90);
  assert.equal(etaSeconds({ remainingJobs: 0, averageSeconds: 30 }), null);
  assert.equal(etaSeconds({ remainingJobs: 3, averageSeconds: null }), null);
  assert.equal(formatEta(32), "30 s");
  assert.equal(formatEta(300), "5 min");
  assert.equal(etaLabel({ remainingJobs: 3, averageSeconds: 60 }), "zbývá ≈ 60 s");
  assert.equal(etaLabel({ remainingJobs: 0, averageSeconds: 60 }), "");
});

test("usageLabel shows spend with or without a budget and stays empty when untracked", () => {
  assert.equal(usageLabel({ spent_usd: 1.234, budget_usd: 20 }), "Tento měsíc ≈ $1.23 z $20.00");
  assert.equal(usageLabel({ spent_usd: 2, budget_usd: null }), "Tento měsíc ≈ $2.00");
  assert.equal(usageLabel({ spent_usd: null }), "");
  assert.equal(usageLabel(null), "");
});

test("controlsFromSettings maps stored settings onto studio controls", () => {
  const controls = controlsFromSettings({ model_id: "m1", lora_id: "l", lora_strength: 0.7, denoise: 0.4, guidance_scale: 5,
    steps: 28, seed: 123, sampler: "euler_a", schedule: "karras", render_mode: "detail", prompt: "x", negative_prompt: "y" });
  assert.deepEqual(controls, { engine: { mode: "detail", sampler: "euler_a", schedule: "karras", prompt: "x", negativePrompt: "y", seed: "123" },
    modelId: "m1", loraId: "l", loraStrength: 0.7, denoise: 0.4, cfg: 5, steps: 28 });
  assert.deepEqual(controlsFromSettings(undefined), { engine: {} });
});

test("creationMode names the Atelier way an image was made and ignores img2img outputs", () => {
  assert.equal(creationMode({ settings: { generation_type: "atelier", atelier_mode: "photo" } }), "Foto → malba");
  assert.equal(creationMode({ settings: { generation_type: "atelier", atelier_mode: "noise" } }), "Volná studie");
  assert.equal(creationMode({ settings: { generation_type: "atelier", atelier_mode: "subject" } }), "Automatický námět");
  assert.equal(creationMode({ settings: { generation_type: "atelier", atelier_mode: "archive" } }), "Archiv → fúze");
  assert.equal(creationMode({ settings: { generation_type: "atelier" } }), "Ateliér");
  assert.equal(creationMode({ settings: { generation_type: "img2img" } }), "");
  assert.equal(creationMode(null), "");
});
