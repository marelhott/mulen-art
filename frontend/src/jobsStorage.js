// Restoring jobs that were still running when the page closed. No imports, so it is trivially testable.
export const EMPTY_JOB = {
  id: "",
  status: "idle",
  progress: 0,
  message: "Idle",
  logs: [],
  result: null,
  error: null,
};

// localStorage throws in private mode or when blocked; it is only a convenience, never required.
export function storage(action) {
  try { return action(window.localStorage); } catch { return null; }
}

// Jobs still running when the page closed (or the last finished batch) come back from localStorage.
export function loadStoredJobs() {
  try {
    const saved = JSON.parse(storage((store) => store.getItem("img2img-active-jobs")) || "[]");
    if (Array.isArray(saved) && saved.length) return saved;
    const legacy = storage((store) => store.getItem("img2img-active-job"));
    if (legacy)
      return [
        { job_id: legacy, source_name: "Input image", expected_images: 1 },
      ];
    const lastBatch = JSON.parse(storage((store) => store.getItem("img2img-last-batch")) || "[]");
    return Array.isArray(lastBatch) ? lastBatch : [];
  } catch {
    return [];
  }
}
