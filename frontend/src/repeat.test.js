import test from "node:test";
import assert from "node:assert/strict";
import {atelierBaseSeed, atelierFromSettings, sourceUrls, tabForSettings} from "./studioTools.js";

test("repeat goes to the tab that made the image", () => {
  assert.equal(tabForSettings({generation_type: "atelier"}), "atelier");
  assert.equal(tabForSettings({generation_type: "collage"}), "collage");
  assert.equal(tabForSettings({}), "results");
});

test("a fused collage brings back all its inputs in order", () => {
  assert.deepEqual(sourceUrls({settings: {source_url: "/library/a.png", extra_source_urls: ["/library/b.png"]}}), ["/library/a.png", "/library/b.png"]);
  assert.deepEqual(sourceUrls({settings: {}}), []);
});

test("the Atelier base seed undoes the server's per-model offset", async () => {
  const offset = 4153797571;  // first four bytes of sha256("mulen_mara"), as app_runtime/cloud_server.py computes it
  assert.equal(await atelierBaseSeed((1234 + offset) % 4294967296, "mulen_mara"), 1234);
});

test("an Atelier study restores its own controls, not the boosted CFG", () => {
  const current = {mode: "subject", count: 4, cfg: 2, colorLevel: 2, glitch: "chan_drop", ratio: "random", modelIds: ["x"]};
  const next = atelierFromSettings({atelier_mode: "noise", model_id: "mulen_mara", cfg: 4.5, requested_cfg: 0.5, color_level: 1,
    generation_width: 832, generation_height: 1216, upscaler: "lanczos"}, current);
  assert.deepEqual([next.mode, next.count, next.cfg, next.colorLevel, next.glitch, next.ratio, next.width, next.modelIds],
    ["noise", 1, 0.5, 1, "", "fixed", 832, ["mulen_mara"]]);
  const archive = atelierFromSettings({atelier_mode: "archive", color_level: 0, atelier_archive: "mulen", generation_width: 700}, current);
  assert.deepEqual([archive.colorLevel, archive.archive, archive.ratio], [2, "mulen", "random"]);
});
