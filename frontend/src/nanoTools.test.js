import test from "node:test";
import assert from "node:assert/strict";
import {DEFAULT_COLLAGE, DEFAULT_VARI, clampCount, collageFromSettings, isFused, planCollage, planVari, plannedImages, usableModels, variFromSettings} from "./nanoTools.js";

const catalogue = [
  {id: "nano-pro", available: true}, {id: "gpt", available: true}, {id: "flux", available: false}, {id: "qwen-pro", available: true},
  {id: "lustify", available: true, max_inputs: 0},
];

test("only selected models with a key are used, in catalogue order", () => {
  assert.deepEqual(usableModels(["qwen-pro", "flux", "nano-pro"], catalogue).map(item => item.id), ["nano-pro", "qwen-pro"]);
  assert.deepEqual(usableModels([], catalogue), []);
});

test("a text-only model is never used, even when selected", () => {
  assert.deepEqual(usableModels(["lustify", "gpt"], catalogue).map(item => item.id), ["gpt"]);
});

test("Vari plans one request per model with the clamped count and distance", () => {
  const plan = planVari({...DEFAULT_VARI, models: ["gpt", "nano-pro"], count: 9, distance: "far", prompt: "  mine "}, catalogue);
  assert.deepEqual(plan.map(item => item.nano_model), ["nano-pro", "gpt"]);
  assert.ok(plan.every(item => item.generation_type === "vari" && item.num_images === 5 && item.nano_distance === "far" && item.prompt === "mine"));
  assert.equal(plannedImages(plan), 10);
  assert.equal(clampCount(0), 1);
  assert.equal(clampCount("abc"), 1);
});

test("Koláž fuses two or more inputs into one request per model with the other sources attached", () => {
  const plan = planCollage({...DEFAULT_COLLAGE, models: ["nano-pro", "gpt"]}, catalogue, ["a", "b", "c"], 10);
  assert.equal(plan.length, 2);
  assert.deepEqual(plan.map(item => item.settings.extra_source_ids), [["b", "c"], ["b", "c"]]);
  assert.deepEqual(plan.map(item => item.settings.seed), [10, 11]);
  assert.ok(plan.every(item => item.sourceIndex === 0 && item.settings.collage_fuse && item.settings.num_images === 1));
});

test("Koláž works on each input separately when fusing is off or there is one input", () => {
  const off = planCollage({...DEFAULT_COLLAGE, fuse: false, count: 2}, catalogue, ["a", "b"], 0);
  assert.equal(off.length, 2);
  assert.ok(off.every(item => !item.settings.collage_fuse && item.settings.num_images === 2 && item.settings.extra_source_ids === undefined));
  assert.deepEqual(off.map(item => item.sourceIndex), [0, 1]);
  assert.equal(isFused({fuse: true}, 1), false);
  assert.equal(isFused({fuse: true}, 2), true);
  assert.equal(planCollage(DEFAULT_COLLAGE, catalogue, ["a"], 0)[0].settings.collage_fuse, false);
});

test("repeat restores the controls from stored settings", () => {
  assert.deepEqual(variFromSettings({nano_model: "gpt", nano_distance: "weird", custom_prompt: "x"}, DEFAULT_VARI), {...DEFAULT_VARI, models: ["gpt"], distance: "weird", prompt: "x"});
  assert.equal(collageFromSettings({nano_model: "flux", collage_fuse: false}, DEFAULT_COLLAGE).fuse, false);
});
