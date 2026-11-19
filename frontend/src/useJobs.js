import { useEffect } from "react";
import { apiFetch, readJson } from "./api";
import { etaLabel, EXPIRED_NOTICE, keepUnexpired } from "./studioTools";

export const POLL_INTERVAL = 1500;
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
function storage(action) {
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

// Polls active jobs in bulk, mirrors their state into the canvas/job panel and persists the list.
export function useJobs({
  activeJobs, setActiveJobs, submissionErrors, recordsCache, deletedIds, plannedCount, submitting,
  setBatchResults, setResults, setJob, setError, loadLibrary, averageSeconds, onBatchFinished,
}) {
  useEffect(() => {
    if (!activeJobs.length) return undefined;
    let cancelled = false;
    let timer;
    // A new batch chunk restarts this effect; the previous in-flight poll must not keep running beside it.
    const controller = new AbortController();
    const known = recordsCache.current;
    const poll = async () => {
      // One bulk request per tick instead of one poll per job.
      const pending = activeJobs.filter((item) => {
        const previous = known.get(item.job_id);
        return !(previous && ["completed", "failed", "cancelled"].includes(previous.status));
      });
      let fetched = {};
      let failure = null;
      for (let offset = 0; offset < pending.length && !failure; offset += 200) {
        const ids = pending.slice(offset, offset + 200).map((item) => item.job_id).join(",");
        try {
          const response = await apiFetch(`/api/jobs?ids=${ids}`, { signal: controller.signal });
          const data = await readJson(response, "Spojení přerušeno.");
          Object.assign(fetched, data.jobs);
        } catch (error) {
          failure = error;
        }
      }
      const responses = activeJobs.map((item) => {
        if (item.job_id in fetched) {
          const value = fetched[item.job_id] || {
            id: item.job_id,
            status: "failed",
            progress: 0,
            expired: true,
          };
          return {status: "fulfilled", value};
        }
        const previous = known.get(item.job_id);
        if (previous && ["completed", "failed", "cancelled"].includes(previous.status))
          return {status: "fulfilled", value: previous};
        return {status: "rejected", reason: failure || new Error("Connection interrupted")};
      });
      if (cancelled) return;
      responses.forEach((response, index) => {
        if (response.status === "fulfilled")
          known.set(activeJobs[index].job_id, response.value);
      });
      const records = activeJobs.map(
        (item) => known.get(item.job_id) || { status: "queued", progress: 0 },
      );
      const slots = records.flatMap((record, index) => {
        if (record.expired) return [];  // an expired job has no images left to place; they live in the library
        const images = record.result?.images || record.partial_images || [];
        return Array.from(
          { length: activeJobs[index].expected_images || images.length || 1 },
          (_, slot) =>
            images[slot]
              ? {
                  ...images[slot],
                  source_name: activeJobs[index].source_name,
                  source_url: activeJobs[index].source_url || record.source_url,
                  source_id: activeJobs[index].source_id,
                }
              : null,
        );
      });
      const finished = records.filter((record) =>
        ["completed", "failed", "cancelled"].includes(record.status),
      ).length;
      const expired = records.filter((record) => record.expired);
      const failed = records.filter((record) => record.status === "failed" && !record.expired);
      const logs = records
        .flatMap((record) => record.logs || [])
        .sort((a, b) => String(a.timestamp || "").localeCompare(String(b.timestamp || "")))
        .slice(-10);
      const ready = slots.filter(Boolean);
      // New outputs stay on the canvas until explicitly saved; the library is refetched after the batch.
      const latest = logs.at(-1)?.message || "Čekání na cloudové GPU";
      setBatchResults(slots);
      setResults((current) => {
        const ids = new Set(ready.map((item) => item.id));
        return [...slots, ...current.filter((item) => item && !ids.has(item.id))].filter((item) => !item || !deletedIds.current.has(item.id));
      });
      // Progress is weighed in images (a job carries up to 8), jobs are counted as jobs.
      const weights = records.map((_, index) => activeJobs[index].expected_images || 1);
      const submittedImages = weights.reduce((sum, weight) => sum + weight, 0);
      const totalImages = Math.max(submittedImages, plannedCount.current, 1);
      const progress = records.reduce(
        (sum, record, index) =>
          sum + weights[index] * (["completed", "failed", "cancelled"].includes(record.status) ? 1 : record.progress || 0),
        0,
      ) / totalImages;
      const averageImagesPerJob = records.length ? submittedImages / records.length : 1;
      const notSubmittedJobs = Math.ceil(Math.max(0, plannedCount.current - submittedImages) / Math.max(1, averageImagesPerJob));
      const totalJobs = records.length + notSubmittedJobs;
      setJob({
        ...EMPTY_JOB,
        status:
          finished === records.length && !submitting.current
            ? failed.length
              ? "failed"
              : records.some((record) => record.status === "cancelled")
                ? "cancelled"
                : "completed"
            : "running",
        progress,
        queue_counts: {
          queued: records.filter(record => record.status === "queued").length,
          running: records.filter(record => record.status === "running").length,
          completed: records.filter(record => record.status === "completed").length,
          failed: failed.length,
        },
        active_steps: records.flatMap((record, index) => {
          if (record.status !== "running") return [];
          const match = (record.message || "").match(/step (\d+)\/(\d+)/);
          return match ? [{id: activeJobs[index].job_id, current: Number(match[1]), total: Number(match[2])}] : [];
        }),
        logs,
        started_at: records
          .map((record) => record.created_at)
          .filter(Boolean)
          .sort()[0],
        finished_at:
          finished === records.length
            ? records
                .map((record) => record.updated_at)
                .filter(Boolean)
                .sort()
                .at(-1)
            : null,
        message: [`${ready.length}/${Math.max(slots.length, plannedCount.current)} obrázků · ${finished}/${totalJobs} úloh hotovo`,
          etaLabel({remainingJobs: totalJobs - finished, averageSeconds: averageSeconds?.current}), latest].filter(Boolean).join(" · "),
      });
      const issues = [
        ...submissionErrors,
        ...failed.map((record) => record.error?.detail || "Generation failed"),
        ...(expired.length ? [EXPIRED_NOTICE] : []),
      ];
      if (responses.some((response) => response.status === "rejected"))
        issues.push("Spojení přerušeno, kontrolu opakuji.");
      setError(issues.join(" · "));
      if (finished === records.length && !submitting.current) {
        storage((store) => store.setItem("img2img-last-batch", JSON.stringify(keepUnexpired(activeJobs, records))));
        setActiveJobs([]);
        loadLibrary().catch(() => {});
        onBatchFinished?.();
      } else timer = window.setTimeout(poll, POLL_INTERVAL);
    };
    poll();
    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [activeJobs, submissionErrors]);

  useEffect(() => {
    storage((store) => {
      if (activeJobs.length) store.setItem("img2img-active-jobs", JSON.stringify(activeJobs));
      else store.removeItem("img2img-active-jobs");
      store.removeItem("img2img-active-job");
    });
  }, [activeJobs]);
}
