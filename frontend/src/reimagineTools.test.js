import test from "node:test";
import assert from "node:assert/strict";
import {DEFAULT_REIMAGINE, planReimagine, plannedImages, presetLabel, REIMAGINE_PRESETS, reimagineFromSettings} from "./reimagineTools.js";

test("manual unCLIP mode splits a count into chunks of 8 with consecutive seeds", () => {
  const plan = planReimagine({...DEFAULT_REIMAGINE, count: 10, strength: 0.6, noise: 20}, 5);
  assert.deepEqual(plan.map(r => [r.num_images, r.seed, r.denoise, r.noise_level, r.reimagine_mode, r.long_side]),
    [[8, 5, 0.6, 20, "unclip", 1024], [2, 13, 0.6, 20, "unclip", 1024]]);
  assert.equal(plannedImages(plan), 10);
});

test("metamorph mode sends its own strength, adapter and guidance and no unCLIP fields", () => {
  const [request] = planReimagine({...DEFAULT_REIMAGINE, mode: "metamorph", count: 1}, 3);
  assert.deepEqual([request.reimagine_mode, request.denoise, request.ip_scale, request.ip_variant, request.cfg, request.steps], ["metamorph", 0.85, 0.6, "plain", 5.5, 30]);
  assert.equal(request.noise_level, undefined);
});

test("preset mode gives one image per preset of the active mode with a shared seed", () => {
  for (const mode of ["unclip", "metamorph"]) {
    const plan = planReimagine({...DEFAULT_REIMAGINE, mode, usePresets: true, count: 16}, 7);
    assert.equal(plan.length, REIMAGINE_PRESETS[mode].length);
    assert.ok(plan.every(r => r.num_images === 1 && r.seed === 7 && r.reimagine_mode === mode));
    assert.deepEqual(plan.map(r => r.denoise), REIMAGINE_PRESETS[mode].map(p => p.settings.denoise));
  }
});

test("labels and the repeat action round-trip the settings", () => {
  assert.equal(presetLabel(REIMAGINE_PRESETS.metamorph[2]), "Ukotvená v obraze · síla 0,85 · vliv obrazu 0,8");
  const back = reimagineFromSettings({reimagine_mode: "metamorph", denoise: 0.75, ip_scale: 0.5, ip_variant: "plus", steps: 25, guidance_scale: 6}, DEFAULT_REIMAGINE);
  assert.deepEqual([back.mode, back.mStrength, back.ipScale, back.ipVariant, back.mSteps, back.mCfg], ["metamorph", 0.75, 0.5, "plus", 25, 6]);
  assert.equal(reimagineFromSettings({denoise: 0.5, generation_width: 576, generation_height: 768}, DEFAULT_REIMAGINE).longSide, 768);
});
