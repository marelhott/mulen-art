import test from "node:test";
import assert from "node:assert/strict";
import {planReimagine, plannedImages, REIMAGINE_PRESETS} from "./reimagineTools.js";

test("manual mode splits a count into chunks of 8 with consecutive seeds", () => {
  const plan = planReimagine({count: 10, strength: 0.6, noise: 20, seed: 5, usePresets: false});
  assert.deepEqual(plan.map(r => [r.num_images, r.seed, r.denoise, r.noise_level]), [[8, 5, 0.6, 20], [2, 13, 0.6, 20]]);
  assert.equal(plannedImages(plan), 10);
});

test("preset mode gives one image per preset with a shared seed and ignores the manual values", () => {
  const plan = planReimagine({count: 16, strength: 0.3, noise: 500, seed: 7, usePresets: true});
  assert.equal(plan.length, REIMAGINE_PRESETS.length);
  assert.ok(plan.every(r => r.num_images === 1 && r.seed === 7));
  assert.deepEqual(plan.map(r => [r.denoise, r.noise_level]), REIMAGINE_PRESETS.map(p => [p.denoise, p.noise]));
  assert.equal(plannedImages(plan), 4);
});
