import test from "node:test";
import assert from "node:assert/strict";
import { GLITCH_OPS, GLITCH_UNTIL, glitchOp, glitchSettings } from "./glitchTools.js";

test("a glitch adds request fields only when switched on and keeps the share of damaged steps in range", () => {
  assert.deepEqual(glitchSettings("", 0.5), {});
  assert.deepEqual(glitchSettings(undefined, undefined), {});
  assert.deepEqual(glitchSettings("top_suppress", 0.45), {glitch: "top_suppress", glitch_until: 0.45});
  assert.equal(glitchSettings("chan_drop", 3).glitch_until, GLITCH_UNTIL.max);
  assert.equal(glitchSettings("chan_drop", 0).glitch_until, GLITCH_UNTIL.min);
  assert.equal(glitchSettings("chan_drop", "x").glitch_until, GLITCH_UNTIL.default);
});

test("the operations match the backend and the first choice is off", () => {
  assert.deepEqual(GLITCH_OPS.map(item => item.id), ["", "top_suppress", "chan_drop", "sa_identity"]);
  assert.equal(glitchOp("chan_drop").name, "Vynechané kanály");
  assert.equal(glitchOp("nonsense").id, "");
});
