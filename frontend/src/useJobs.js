import { useEffect } from "react";
import { API_URL } from "./api";

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

// Jobs still running when the page closed (or the last finished batch) come back from localStorage.
export function loadStoredJobs() {
  try {
    const saved = JSON.parse(
      window.localStorage.getItem("img2img-active-jobs") || "[]",
    );
    if (Array.isArray(saved) && saved.length) return saved;
    const legacy = window.localStorage.getItem("img2img-active-job");
    if (legacy)
      return [
        { job_id: legacy, source_name: "Input image", expected_images: 1 },
      ];
    const lastBatch = JSON.parse(
      window.localStorage.getItem("img2img-last-batch") || "[]",
    );
    return Array.isArray(lastBatch) ? lastBatch : [];
  } catch {
    return [];
  }
}

// Polls active jobs in bulk, mirrors their state into the canvas/job panel and persists the list.
export function useJobs({
  activeJobs, setActiveJobs, submissionErrors, recordsCache, deletedIds, plannedCount, submitting,
  setBatchResults, setResults, setJob, setError, loadLibrary,
}) {
  useEffect(() => {
    if (!activeJobs.length) return undefined;
    let cancelled = false;
    let timer;
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
          const response = await fetch(`${API_URL}/api/jobs?ids=${ids}`);
          if (response.status === 401) {
            window.location.assign("/login");
            throw new Error("Sign in required");
          }
          const data = await response.json();
          if (!response.ok)
            throw new Error(data.detail || "Connection interrupted");
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
            error: {detail: "Job expired. Saved images remain in the library."},
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
      const failed = records.filter((record) => record.status === "failed");
      const logs = records
        .flatMap((record) => record.logs || [])
        .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
        .slice(-10);
      const ready = slots.filter(Boolean);
      // New outputs stay on the canvas until explicitly saved; the library is refetched after the batch.
      const latest = logs.at(-1)?.message || "Čekání na cloudové GPU";
      setBatchResults(slots);
      setResults((current) => {
        const ids = new Set(ready.map((item) => item.id));
        return [...slots, ...current.filter((item) => item && !ids.has(item.id))].filter((item) => !item || !deletedIds.current.has(item.id));
      });
      const progress =
        records.reduce(
          (sum, record) =>
            sum + (record.status === "completed" ? 1 : record.progress || 0),
          0,
        ) / Math.max(records.length, plannedCount.current);
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
        message: `${ready.length}/${Math.max(slots.length, plannedCount.current)} obrázků · ${finished}/${Math.max(records.length, plannedCount.current)} úloh hotovo · ${latest}`,
      });
      const issues = [
        ...submissionErrors,
        ...failed.map((record) => record.error?.detail || "Generation failed"),
      ];
      if (responses.some((response) => response.status === "rejected"))
        issues.push("Spojení přerušeno, kontrolu opakuji.");
      setError(issues.join(" · "));
      if (finished === records.length && !submitting.current) {
        window.localStorage.setItem(
          "img2img-last-batch",
          JSON.stringify(activeJobs),
        );
        setActiveJobs([]);
        loadLibrary().catch(() => {});
      } else timer = window.setTimeout(poll, POLL_INTERVAL);
    };
    poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [activeJobs, submissionErrors]);

  useEffect(() => {
    if (activeJobs.length)
      window.localStorage.setItem(
        "img2img-active-jobs",
        JSON.stringify(activeJobs),
      );
    else window.localStorage.removeItem("img2img-active-jobs");
    window.localStorage.removeItem("img2img-active-job");
  }, [activeJobs]);
}
