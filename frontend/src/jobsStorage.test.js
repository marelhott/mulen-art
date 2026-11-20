// Run: node --test frontend/src/jobsStorage.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { loadStoredJobs } from "./jobsStorage.js";

function withStorage(entries, run) {
  const store = new Map(Object.entries(entries));
  globalThis.window = { localStorage: { getItem: (key) => store.get(key) ?? null } };
  try { return run(); } finally { delete globalThis.window; }
}

test("stored active jobs come back first", () => {
  const jobs = [{ job_id: "j1", expected_images: 2 }];
  assert.deepEqual(withStorage({ "img2img-active-jobs": JSON.stringify(jobs) }, loadStoredJobs), jobs);
});

test("a legacy single job id is upgraded to a job entry", () => {
  const [job] = withStorage({ "img2img-active-job": "old-id" }, loadStoredJobs);
  assert.equal(job.job_id, "old-id");
  assert.equal(job.expected_images, 1);
});

test("the last finished batch is the fallback, and garbage or blocked storage gives nothing", () => {
  const batch = [{ job_id: "done" }];
  assert.deepEqual(withStorage({ "img2img-last-batch": JSON.stringify(batch) }, loadStoredJobs), batch);
  assert.deepEqual(withStorage({ "img2img-active-jobs": "{not json" }, loadStoredJobs), []);
  globalThis.window = { get localStorage() { throw new Error("blocked"); } };
  try { assert.deepEqual(loadStoredJobs(), []); } finally { delete globalThis.window; }
});
