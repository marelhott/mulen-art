import test from "node:test";
import assert from "node:assert/strict";
import {DEFAULT_VARI, availableEngines, maxPerCall, planVari, plannedVariImages, variFromSettings} from "./variTools.js";

const engines = [
  {id: "sd-variation", available: true, tuning: [{key: "sd_variation_steps"}, {key: "sd_variation_guidance"}]},
  {id: "gpt-image-2", available: false, missing: ["OPENAI_API_KEY"], tuning: []},
  {id: "stable", available: true, tuning: [{key: "stable_steps"}]},
];

test("a single engine and distance chunks the count into provider calls", () => {
  const plan = planVari({...DEFAULT_VARI, engineId: "sd-variation", distance: "looser", count: 10}, engines);
  assert.deepEqual(plan.map(r => [r.vari_engine, r.vari_distance, r.num_images]), [["sd-variation", "looser", 4], ["sd-variation", "looser", 4], ["sd-variation", "looser", 2]]);
  assert.equal(plannedVariImages(plan), 10);
  assert.equal(maxPerCall("stable"), 12);
});

test("all engines uses only the available ones and all distances multiplies by four", () => {
  const plan = planVari({...DEFAULT_VARI, allEngines: true, allDistances: true, count: 2}, engines);
  assert.equal(plan.length, 2 * 4);
  assert.ok(plan.every(r => r.vari_engine !== "gpt-image-2"));
  assert.deepEqual(availableEngines(engines).map(e => e.id), ["sd-variation", "stable"]);
});

test("only the tuning of the chosen engine is sent, and only finite numbers", () => {
  const [request] = planVari({...DEFAULT_VARI, engineId: "sd-variation", count: 1, tuning: {sd_variation_steps: 31, stable_steps: 9, sd_variation_guidance: NaN}}, engines);
  assert.deepEqual(request.vari_tuning, {sd_variation_steps: 31});
});

test("an unavailable single engine plans nothing", () => {
  assert.deepEqual(planVari({...DEFAULT_VARI, engineId: "gpt-image-2"}, engines), []);
});

test("the repeat action restores engine, distance and tuning", () => {
  const next = variFromSettings({vari_engine: "stable", vari_distance: "locked", tuning: {stable_steps: 20}}, {...DEFAULT_VARI, allEngines: true});
  assert.deepEqual([next.engineId, next.distance, next.allEngines, next.tuning], ["stable", "locked", false, {stable_steps: 20}]);
});
