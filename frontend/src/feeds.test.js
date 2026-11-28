import test from "node:test";
import assert from "node:assert/strict";
import {modelOptions, splitByMode} from "./studioTools.js";
import {DEFAULT_REIMAGINE, planReimagine} from "./reimagineTools.js";

test("each pending card stays on the tab of its own job", () => {
  const done = {settings: {generation_type: "vari"}};
  const feeds = splitByMode([null, null, done, {settings: {}}], ["atelier", "vari"]);
  assert.deepEqual([feeds.atelier, feeds.vari, feeds.results.length], [[null], [null, done], 1]);
});

test("the model filter also offers the models that are not checkpoints", () => {
  const items = [{model_id: "nano_pro", settings: {model_name: "Vari · Nano Pro"}}, {model_id: "a"}];
  assert.deepEqual(modelOptions(items, [{id: "a", name: "A"}]), [{id: "a", name: "A"}, {id: "nano_pro", name: "Vari · Nano Pro"}]);
});

test("unCLIP sends the model damage for Varianta only, and nothing when it is off", () => {
  assert.equal("glitch" in planReimagine(DEFAULT_REIMAGINE, 1)[0], false);
  assert.equal(planReimagine({...DEFAULT_REIMAGINE, glitch: "chan_drop", usePresets: true}, 1)[0].glitch, "chan_drop");
  assert.equal("glitch" in planReimagine({...DEFAULT_REIMAGINE, mode: "metamorph", glitch: "chan_drop"}, 1)[0], false);
});
