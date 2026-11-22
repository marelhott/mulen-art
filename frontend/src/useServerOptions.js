import { useEffect, useState } from "react";
import { apiFetch, readJson } from "./api";

// What the server offers (checkpoints, LoRAs, archives, GPU rate). Retries every 5 s while it is unreachable
// (a cold start). The studio keeps its own selection state, so reconciliation callbacks are passed in:
// they drop selected ids the server no longer knows.
export function useServerOptions({ onModels, onLoras }) {
  const [archives, setArchives] = useState([]);
  const [gpuHourlyUsd, setGpuHourlyUsd] = useState(null);
  const [archiveStatus, setArchiveStatus] = useState("loading");
  const [serverModels, setServerModels] = useState([]);
  const [loras, setLoras] = useState([]);
  const [nanoModels, setNanoModels] = useState([]);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let retry;
    setArchiveStatus("loading");
    apiFetch("/api/options", { cache: "no-store" })
      .then((response) => readJson(response, "Možnosti nelze načíst."))
      .then((data) => {
        if (cancelled) return;
        setArchives(data.archives || []);
        setGpuHourlyUsd(data.gpu_hourly_usd ?? null);
        setNanoModels(data.nano_models || []);
        setArchiveStatus(data.archives?.length ? "ready" : "error");
        if (data.models?.length) {
          setServerModels(data.models);
          onModels(data.models);
        }
        if (data.loras?.length) {
          setLoras(data.loras);
          onLoras(data.loras);
        }
      })
      .catch(() => {
        if (!cancelled) { setArchiveStatus("error"); retry = setTimeout(() => setRevision((v) => v + 1), 5000); }
      });
    return () => { cancelled = true; clearTimeout(retry); };
  }, [revision]);

  return { archives, gpuHourlyUsd, nanoModels, archiveStatus, serverModels, loras, reload: () => setRevision((v) => v + 1) };
}
