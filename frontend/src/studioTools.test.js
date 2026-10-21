import test from "node:test";
import assert from "node:assert/strict";
import { filterItems, averageWorkerSeconds, etaSeconds, formatEta, etaLabel, usageLabel, controlsFromSettings, creationMode, retryUrl, RETRY_DELAYS_MS, isMixId, parseMixId, normalizeWeights, buildMixId, mixEntry, sourceOf, idsForSource, planVariants, VARIANT_DISTANCES, describeVariant } from "./studioTools.js";

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

test("retryUrl cache-busts failed image loads but leaves inline sources alone", () => {
  assert.equal(retryUrl("/thumb/a.webp", 0), "/thumb/a.webp");
  assert.equal(retryUrl("/thumb/a.webp", 2), "/thumb/a.webp?retry=2");
  assert.equal(retryUrl("/x.png?v=1", 1), "/x.png?v=1&retry=1");
  assert.equal(retryUrl("blob:abc", 1), "blob:abc");
  assert.equal(retryUrl("data:image/png;base64,xx", 3), "data:image/png;base64,xx");
  assert.equal(retryUrl("", 1), "");
  assert.ok(RETRY_DELAYS_MS.length >= 2);
});

test("normalizeWeights always yields whole percents summing to 100 with no part below 1", () => {
  assert.deepEqual(normalizeWeights([50, 50]), [50, 50]);
  assert.deepEqual(normalizeWeights([1, 1, 1]), [34, 33, 33]);
  assert.deepEqual(normalizeWeights([3, 1]), [75, 25]);
  assert.deepEqual(normalizeWeights([1000, 1]), [99, 1]);
  for (const raw of [[7, 13, 29, 51], [1, 1, 1, 1], [100, 1, 1, 1], [33, 33, 34]]) {
    const result = normalizeWeights(raw);
    assert.equal(result.reduce((sum, value) => sum + value, 0), 100);
    assert.ok(result.every((value) => value >= 1));
  }
});

test("mix ids round-trip and are validated like the server does", () => {
  const id = buildMixId([{ id: "mulen_mara", weight: 3 }, { id: "tuymans_modal_2400", weight: 1 }]);
  assert.equal(id, "mix:mulen_mara=75,tuymans_modal_2400=25");
  assert.ok(isMixId(id));
  assert.deepEqual(parseMixId(id), [{ id: "mulen_mara", weight: 75 }, { id: "tuymans_modal_2400", weight: 25 }]);
  for (const bad of ["mix:a=100", "mix:a=60,a=40", "mix:a=60,b=30", "mix:a=0,b=100", "a=50,b=50", "mix:a=20,b=20,c=20,d=20,e=20", "mix:A=50,b=50"]) assert.equal(parseMixId(bad), null, bad);
});

test("mixEntry names a mix and rejects ones that mention unknown or base checkpoints", () => {
  const models = [{ id: "a", name: "A" }, { id: "b", name: "B" }, { id: "sdxl_base", name: "Base", kind: "base" }];
  assert.equal(mixEntry("mix:a=60,b=40", models).name, "Fúze: A 60 % + B 40 %");
  assert.equal(mixEntry("mix:a=60,zzz=40", models), null);
  assert.equal(mixEntry("mix:a=60,sdxl_base=40", models), null);
});

test("plain checkpoints and fusions are exclusive sources", () => {
  const ids = ["a", "mix:a=50,b=50", "b", "mix:a=30,b=70"];
  assert.deepEqual(idsForSource(ids, "single"), ["a", "b"]);
  assert.deepEqual(idsForSource(ids, "mix"), ["mix:a=50,b=50", "mix:a=30,b=70"]);
  assert.equal(sourceOf("mix:a=50,b=50"), "mix");
  assert.equal(sourceOf("a"), "single");
  assert.deepEqual(idsForSource([], "mix"), []);
});

test("variants: deterministic siblings that differ in seed, settings, prompt and fusion weights within the distance band", () => {
  const base = { denoise: 0.5, cfg: 5, loraStrength: 0.8, modelId: "mix:a=60,b=40" };
  const plan = planVariants({ count: 5, distance: "middle", spread: 0.5, prompt: "a quiet room", base, seed: 100 });
  assert.equal(plan.length, 5);
  assert.deepEqual(plan, planVariants({ count: 5, distance: "middle", spread: 0.5, prompt: "a quiet room", base, seed: 100 }));
  assert.deepEqual(plan.map((v) => v.seed), [100, 101, 102, 103, 104]);
  assert.equal(new Set(plan.map((v) => v.denoise)).size > 1, true);
  assert.equal(new Set(plan.map((v) => v.modelId)).size > 1, true);
  for (const v of plan) {
    assert.ok(parseMixId(v.modelId), "still a valid mix summing to 100");
    assert.ok(v.denoise >= 0.05 && v.denoise <= 0.95 && v.cfg >= 0.5 && v.cfg <= 20);
    assert.ok(v.prompt.startsWith("a quiet room, "));
  }
  assert.equal(new Set(plan.map((v) => v.directive)).size, 5);
});

test("variants: distance moves denoise, adds its suffix, and spread 0 keeps the weights and settings", () => {
  const base = { denoise: 0.5, cfg: 5, loraStrength: 0.8, modelId: "tuymans_sdxl" };
  const at = (distance, spread = 0) => planVariants({ count: 1, distance, spread, base, seed: 7 })[0];
  assert.ok(at("near").denoise < at("middle").denoise && at("middle").denoise < at("far").denoise && at("far").denoise < at("weird").denoise);
  assert.equal(at("middle").denoise, 0.5);
  assert.equal(at("middle").modelId, "tuymans_sdxl");
  assert.equal(at("near").prompt, "same pose, slightly different camera angle, camera a few degrees to the left");
  assert.match(at("weird").prompt, /^surreal, dreamlike/);
  assert.equal(planVariants({ count: 1, distance: "bogus", spread: 0, base, seed: 7 })[0].denoise, 0.5);
  assert.equal(VARIANT_DISTANCES.length, 4);
  const mixed = planVariants({ count: 2, distance: "middle", spread: 0, base: { ...base, modelId: "mix:a=70,b=30" }, seed: 1 });
  assert.deepEqual(mixed.map((v) => v.modelId), ["mix:a=70,b=30", "mix:a=70,b=30"]);
  assert.equal(describeVariant(mixed[0], [{ id: "a", name: "A" }, { id: "b", name: "B" }]).text.includes("váhy 70 / 30"), true);
});
