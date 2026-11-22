"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  COMFY_DEFAULTS,
  DISTANCE_COPY,
  DISTANCE_VALUES,
  ENGINE_COPY,
  ENGINE_ORDER,
  type Distance,
  type Engine,
} from "@/lib/engines";

type TileStatus = "pending" | "done" | "error";
type ModelScope = "single" | "all";
type DistanceScope = "single" | "all";
type SourceItem = { id: string; file: File; preview: string; name: string };

type Tile = {
  id: string;
  jobId: string;
  status: TileStatus;
  url?: string;
  error?: string;
  settings: string;
  sourceId?: string;
  sourceName?: string;
  engine: Engine;
  distance: Distance;
  count: number;
  noise: number;
  strength: number;
  ipAdapterScale?: number;
  ipAdapterSteps?: number;
  chigoScale?: number;
  chigoSteps?: number;
  sdxlGuidance?: number;
  sdxlStrength?: number;
  sdxlSteps?: number;
  stableGuidance?: number;
  stableStrength?: number;
  stableSteps?: number;
  sdVariationGuidance?: number;
  sdVariationSteps?: number;
  fofrCfg?: number;
  fofrSteps?: number;
  fofrIpWeight?: number;
  zImageCreativity?: number;
};

type Job = {
  id: string;
  controller: AbortController;
  replicateJobIds: string[];
  tileIds: string[];
};

async function readJsonResponse(response: Response) {
  const text = await response.text();
  if (!text.trim()) {
    return { error: response.ok ? null : `Server vrátil prázdnou odpověď (${response.status}).` };
  }
  try {
    return JSON.parse(text);
  } catch {
    return { error: `Server nevrátil JSON (${response.status}): ${text.slice(0, 180)}` };
  }
}

function randomId() {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

// Grid columns chosen so tiles stay roughly proportional to the source image.
function gridColsFor(n: number) {
  if (n <= 1) return 1;
  if (n <= 2) return 2;
  if (n <= 4) return 2;
  if (n <= 6) return 3;
  return 4;
}

export default function Page() {
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [activeSourceId, setActiveSourceId] = useState<string | null>(null);
  const [distance, setDistance] = useState<Distance>("sibling");
  const [engine, setEngine] = useState<Engine>("sd-variation");
  const [modelScope, setModelScope] = useState<ModelScope>("single");
  const [distanceScope, setDistanceScope] = useState<DistanceScope>("single");
  const [count, setCount] = useState(2);
  const [comfyNoise, setComfyNoise] = useState(COMFY_DEFAULTS.sibling.noise);
  const [comfyStrength, setComfyStrength] = useState(COMFY_DEFAULTS.sibling.strength);
  const [ipAdapterScale, setIpAdapterScale] = useState(0.66);
  const [ipAdapterSteps, setIpAdapterSteps] = useState(48);
  const [chigoScale, setChigoScale] = useState(0.82);
  const [chigoSteps, setChigoSteps] = useState(68);
  const [sdxlGuidance, setSdxlGuidance] = useState(3.2);
  const [sdxlStrength, setSdxlStrength] = useState(0.5);
  const [sdxlSteps, setSdxlSteps] = useState(36);
  const [stableGuidance, setStableGuidance] = useState(3.8);
  const [stableStrength, setStableStrength] = useState(0.68);
  const [stableSteps, setStableSteps] = useState(30);
  const [sdVariationGuidance, setSdVariationGuidance] = useState(3);
  const [sdVariationSteps, setSdVariationSteps] = useState(25);
  const [fofrCfg, setFofrCfg] = useState(3.2);
  const [fofrSteps, setFofrSteps] = useState(48);
  const [fofrIpWeight, setFofrIpWeight] = useState(0.76);
  const [zImageCreativity, setZImageCreativity] = useState(0.5);
  const [tiles, setTiles] = useState<Tile[]>([]);
  const [activeJobCount, setActiveJobCount] = useState(0);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [isLight, setIsLight] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);
  const jobsRef = useRef<Map<string, Job>>(new Map());

  // Persist theme preference across reloads.
  useEffect(() => {
    const stored = typeof window !== "undefined" ? window.localStorage.getItem("variants:theme") : null;
    if (stored === "dark") setIsLight(false);
    else if (stored === "light") setIsLight(true);
  }, []);
  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem("variants:theme", isLight ? "light" : "dark");
    }
  }, [isLight]);

  const isGenerating = activeJobCount > 0;
  const totalTiles = tiles.length;
  const doneTiles = useMemo(() => tiles.filter((t) => t.status === "done" || t.status === "error").length, [tiles]);
  const progress = totalTiles ? Math.round((doneTiles / totalTiles) * 100) : 0;
  const activeSource = useMemo(
    () => sources.find((item) => item.id === activeSourceId) ?? sources[0] ?? null,
    [sources, activeSourceId],
  );
  const selectedEngines = modelScope === "all" ? ENGINE_ORDER : [engine];
  const selectedDistances = distanceScope === "all" ? DISTANCE_VALUES : [distance];
  const plannedJobs = sources.length * selectedEngines.length * selectedDistances.length;
  const plannedOutputs = plannedJobs * count;
  const runPresetLabel =
    modelScope === "single" && distanceScope === "single"
      ? "jedna kombinace"
      : modelScope === "all" && distanceScope === "single"
        ? "všechny modely / jedna volnost"
        : modelScope === "single" && distanceScope === "all"
          ? "jeden model / všechny 4 volnosti"
          : "všechny modely / všechny 4 volnosti";
  const buildSettingsLabel = (
    selectedEngine: Engine,
    selectedDistance: Distance,
    selectedCount: number,
    selectedNoise: number,
    selectedStrength: number,
    selectedIpAdapterScale?: number,
    selectedIpAdapterSteps?: number,
    selectedChigoScale?: number,
    selectedChigoSteps?: number,
    selectedSdxlGuidance?: number,
    selectedSdxlStrength?: number,
    selectedSdxlSteps?: number,
    selectedStableGuidance?: number,
    selectedStableStrength?: number,
    selectedStableSteps?: number,
    selectedSdVariationGuidance?: number,
    selectedSdVariationSteps?: number,
    selectedFofrCfg?: number,
    selectedFofrSteps?: number,
    selectedFofrIpWeight?: number,
    selectedZImageCreativity?: number,
  ) => {
    const base = `${ENGINE_COPY[selectedEngine]} / ${DISTANCE_COPY[selectedDistance]} / ${selectedCount} ks`;
    if (selectedEngine === "z-image") {
      return `${base} / kreativita ${(selectedZImageCreativity ?? zImageCreativity).toFixed(2)}`;
    }
    if (selectedEngine === "comfy-unclip") {
      return `${base} / noise ${selectedNoise.toFixed(2)} / strength ${selectedStrength.toFixed(2)}`;
    }
    if (selectedEngine === "ip-adapter-sdxl") {
      return `${base} / scale ${(selectedIpAdapterScale ?? ipAdapterScale).toFixed(2)} / steps ${Math.round(selectedIpAdapterSteps ?? ipAdapterSteps)}`;
    }
    if (selectedEngine === "chigozienri-ip-adapter-sdxl") {
      return `${base} / scale ${(selectedChigoScale ?? chigoScale).toFixed(2)} / steps ${Math.round(selectedChigoSteps ?? chigoSteps)}`;
    }
    if (selectedEngine === "sdxl-artistic") {
      return `${base} / guidance ${(selectedSdxlGuidance ?? sdxlGuidance).toFixed(1)} / strength ${(selectedSdxlStrength ?? sdxlStrength).toFixed(2)} / steps ${Math.round(selectedSdxlSteps ?? sdxlSteps)}`;
    }
    if (selectedEngine === "stable") {
      return `${base} / guidance ${(selectedStableGuidance ?? stableGuidance).toFixed(1)} / strength ${(selectedStableStrength ?? stableStrength).toFixed(2)} / steps ${Math.round(selectedStableSteps ?? stableSteps)}`;
    }
    if (selectedEngine === "sd-variation") {
      return `${base} / guidance ${(selectedSdVariationGuidance ?? sdVariationGuidance).toFixed(1)} / steps ${Math.round(selectedSdVariationSteps ?? sdVariationSteps)}`;
    }
    if (selectedEngine === "fofr-any-comfyui-workflow") {
      return `${base} / cfg ${(selectedFofrCfg ?? fofrCfg).toFixed(1)} / ip ${(selectedFofrIpWeight ?? fofrIpWeight).toFixed(2)} / steps ${Math.round(selectedFofrSteps ?? fofrSteps)}`;
    }
    return base;
  };

  const appendFiles = (fileList: FileList | File[]) => {
    const incoming = Array.from(fileList).filter((file) => file.type.startsWith("image/"));
    if (!incoming.length) return;
    const next = incoming.map((file) => ({
      id: randomId(),
      file,
      name: file.name,
      preview: URL.createObjectURL(file),
    }));
    setSources((current) => [...current, ...next].slice(0, 24));
    setActiveSourceId((current) => current ?? next[0]?.id ?? null);
    setError(null);
  };

  const chooseSourceImage = () => inputRef.current?.click();

  const removeSource = (sourceId: string) => {
    setSources((current) => {
      const target = current.find((source) => source.id === sourceId);
      if (target) {
        URL.revokeObjectURL(target.preview);
      }
      const next = current.filter((source) => source.id !== sourceId);
      setActiveSourceId((active) => {
        if (active !== sourceId) return active;
        return next[0]?.id ?? null;
      });
      return next;
    });
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    appendFiles(e.dataTransfer.files);
  }, []);

  useEffect(() => {
    return () => {
      sources.forEach((source) => URL.revokeObjectURL(source.preview));
    };
  }, [sources]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelectedImage(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Exponential backoff polling: 1.5s -> 3s -> 6s -> 10s cap. 20 min budget.
  const pollReplicateJob = async (jobId: string, signal: AbortSignal, limit: number): Promise<string[]> => {
    const startedAt = Date.now();
    const steps = [1500, 3000, 6000, 10000];
    const maxMs = 1000 * 60 * 20;
    let attempt = 0;

    while (Date.now() - startedAt < maxMs) {
      const delay = steps[Math.min(attempt, steps.length - 1)];
      attempt += 1;
      await new Promise((resolve) => window.setTimeout(resolve, delay));
      if (signal.aborted) throw new Error("Zrušeno uživatelem.");

      const res = await fetch(`/api/generate/status?jobId=${encodeURIComponent(jobId)}&limit=${limit}`, { signal });
      const data = await readJsonResponse(res);
      if (!res.ok || data.error) throw new Error(data.error || "Kontrola stavu selhala");

      setJobStatus(data.status);
      if (data.status === "succeeded") {
        return (data.images || []).map((i: { url: string }) => i.url).filter(Boolean) as string[];
      }
      if (data.status === "failed" || data.status === "canceled") {
        throw new Error(data.error || `Replicate job skončil stavem ${data.status}`);
      }
    }
    throw new Error("Replicate job trvá déle než 20 minut.");
  };

  const pollReplicateJobs = async (jobIds: string[], signal: AbortSignal, expectedCount: number): Promise<string[]> => {
    const settled = await Promise.all(jobIds.map((jobId) => pollReplicateJob(jobId, signal, expectedCount)));
    return settled.flat().slice(0, expectedCount);
  };

  const submitJob = async (
    selectedSource: File,
    selectedEngine: Engine,
    selectedCount: number,
    selectedDistance: Distance,
    selectedNoise: number,
    selectedStrength: number,
    selectedIpAdapterScale: number,
    selectedIpAdapterSteps: number,
    selectedChigoScale: number,
    selectedChigoSteps: number,
    selectedSdxlGuidance: number,
    selectedSdxlStrength: number,
    selectedSdxlSteps: number,
    selectedStableGuidance: number,
    selectedStableStrength: number,
    selectedStableSteps: number,
    selectedSdVariationGuidance: number,
    selectedSdVariationSteps: number,
    selectedFofrCfg: number,
    selectedFofrSteps: number,
    selectedFofrIpWeight: number,
    selectedZImageCreativity: number,
    signal: AbortSignal,
    onReplicateJobIds: (ids: string[]) => void,
  ): Promise<string[]> => {
    const form = new FormData();
    form.append("image", selectedSource);
    form.append("distance", selectedDistance);
    form.append("engine", selectedEngine);
    form.append("count", String(selectedCount));
    form.append("comfyNoise", String(selectedNoise));
    form.append("comfyStrength", String(selectedStrength));
    form.append("ipAdapterScale", String(selectedIpAdapterScale));
    form.append("ipAdapterSteps", String(selectedIpAdapterSteps));
    form.append("chigoScale", String(selectedChigoScale));
    form.append("chigoSteps", String(selectedChigoSteps));
    form.append("sdxlGuidance", String(selectedSdxlGuidance));
    form.append("sdxlStrength", String(selectedSdxlStrength));
    form.append("sdxlSteps", String(selectedSdxlSteps));
    form.append("stableGuidance", String(selectedStableGuidance));
    form.append("stableStrength", String(selectedStableStrength));
    form.append("stableSteps", String(selectedStableSteps));
    form.append("sdVariationGuidance", String(selectedSdVariationGuidance));
    form.append("sdVariationSteps", String(selectedSdVariationSteps));
    form.append("fofrCfg", String(selectedFofrCfg));
    form.append("fofrSteps", String(selectedFofrSteps));
    form.append("fofrIpWeight", String(selectedFofrIpWeight));
    form.append("zImageCreativity", String(selectedZImageCreativity));

    const res = await fetch("/api/generate", { method: "POST", body: form, signal });
    const data = await readJsonResponse(res);
    if (!res.ok || data.error) throw new Error(data.error || "Generování selhalo");

    const replicateJobIds = Array.isArray(data.jobIds)
      ? data.jobIds.filter((value: unknown): value is string => typeof value === "string")
      : data.jobId && data.provider === "replicate"
        ? [data.jobId]
        : [];

    if (replicateJobIds.length && data.provider === "replicate") {
      onReplicateJobIds(replicateJobIds);
      setJobStatus(`${ENGINE_COPY[selectedEngine]} / ${data.status || "starting"}`);
      return pollReplicateJobs(replicateJobIds, signal, selectedCount);
    }
    return (data.images || []) as string[];
  };

  // Core: spawn a set of pending tiles and resolve them as the job completes.
  // Non-blocking, concurrent-safe. Returns immediately; tiles update in place.
  const spawnJob = (
    selectedSource: SourceItem,
    selectedEngine: Engine,
    selectedCount: number,
    selectedDistance: Distance,
    selectedNoise: number,
    selectedStrength: number,
    selectedIpAdapterScale: number,
    selectedIpAdapterSteps: number,
    selectedChigoScale: number,
    selectedChigoSteps: number,
    selectedSdxlGuidance: number,
    selectedSdxlStrength: number,
    selectedSdxlSteps: number,
    selectedStableGuidance: number,
    selectedStableStrength: number,
    selectedStableSteps: number,
    selectedSdVariationGuidance: number,
    selectedSdVariationSteps: number,
    selectedFofrCfg: number,
    selectedFofrSteps: number,
    selectedFofrIpWeight: number,
    selectedZImageCreativity: number,
  ) => {
    const controller = new AbortController();
    const jobId = randomId();
    const settings = buildSettingsLabel(
      selectedEngine,
      selectedDistance,
      selectedCount,
      selectedNoise,
      selectedStrength,
      selectedIpAdapterScale,
      selectedIpAdapterSteps,
      selectedChigoScale,
      selectedChigoSteps,
      selectedSdxlGuidance,
      selectedSdxlStrength,
      selectedSdxlSteps,
      selectedStableGuidance,
      selectedStableStrength,
      selectedStableSteps,
      selectedSdVariationGuidance,
      selectedSdVariationSteps,
      selectedFofrCfg,
      selectedFofrSteps,
      selectedFofrIpWeight,
      selectedZImageCreativity,
    );
    const newTiles: Tile[] = Array.from({ length: selectedCount }, () => ({
      id: randomId(),
      jobId,
      status: "pending" as TileStatus,
      settings,
      sourceId: selectedSource.id,
      sourceName: selectedSource.name,
      engine: selectedEngine,
      distance: selectedDistance,
      count: selectedCount,
      noise: selectedNoise,
      strength: selectedStrength,
      ipAdapterScale: selectedIpAdapterScale,
      ipAdapterSteps: selectedIpAdapterSteps,
      chigoScale: selectedChigoScale,
      chigoSteps: selectedChigoSteps,
      sdxlGuidance: selectedSdxlGuidance,
      sdxlStrength: selectedSdxlStrength,
      sdxlSteps: selectedSdxlSteps,
      stableGuidance: selectedStableGuidance,
      stableStrength: selectedStableStrength,
      stableSteps: selectedStableSteps,
      sdVariationGuidance: selectedSdVariationGuidance,
      sdVariationSteps: selectedSdVariationSteps,
      fofrCfg: selectedFofrCfg,
      fofrSteps: selectedFofrSteps,
      fofrIpWeight: selectedFofrIpWeight,
      zImageCreativity: selectedZImageCreativity,
    }));

    const job: Job = {
      id: jobId,
      controller,
      replicateJobIds: [],
      tileIds: newTiles.map((t) => t.id),
    };
    jobsRef.current.set(jobId, job);

    setTiles((current) => [...current, ...newTiles]);
    setActiveJobCount((n) => n + 1);
    setError(null);

    (async () => {
      try {
        const urls = await submitJob(
          selectedSource.file,
          selectedEngine,
          selectedCount,
          selectedDistance,
          selectedNoise,
          selectedStrength,
          selectedIpAdapterScale,
          selectedIpAdapterSteps,
          selectedChigoScale,
          selectedChigoSteps,
          selectedSdxlGuidance,
          selectedSdxlStrength,
          selectedSdxlSteps,
          selectedStableGuidance,
          selectedStableStrength,
          selectedStableSteps,
          selectedSdVariationGuidance,
          selectedSdVariationSteps,
          selectedFofrCfg,
          selectedFofrSteps,
          selectedFofrIpWeight,
          zImageCreativity,
          controller.signal,
          (replicateIds) => {
            const j = jobsRef.current.get(jobId);
            if (j) j.replicateJobIds = replicateIds;
          },
        );
        setTiles((current) =>
          current.map((t) => {
            if (t.jobId !== jobId) return t;
            const slotIndex = job.tileIds.indexOf(t.id);
            const url = urls[slotIndex];
            return url ? { ...t, status: "done", url } : { ...t, status: "error", error: "Prázdný výstup" };
          }),
        );
      } catch (err) {
        const message = err instanceof Error ? err.message : "Generování selhalo";
        setTiles((current) =>
          current.map((t) => (t.jobId === jobId && t.status === "pending" ? { ...t, status: "error", error: message } : t)),
        );
      } finally {
        jobsRef.current.delete(jobId);
        setActiveJobCount((n) => Math.max(0, n - 1));
        if (jobsRef.current.size === 0) setJobStatus(null);
      }
    })();
  };

  const generate = () => {
    if (!sources.length) return;
    sources.forEach((selectedSource) => {
      selectedEngines.forEach((selectedEngine) => {
        selectedDistances.forEach((selectedDistance) => {
          spawnJob(
            selectedSource,
            selectedEngine,
            count,
            selectedDistance,
            comfyNoise,
            comfyStrength,
            ipAdapterScale,
            ipAdapterSteps,
            chigoScale,
            chigoSteps,
            sdxlGuidance,
            sdxlStrength,
            sdxlSteps,
            stableGuidance,
            stableStrength,
            stableSteps,
            sdVariationGuidance,
            sdVariationSteps,
            fofrCfg,
            fofrSteps,
            fofrIpWeight,
            zImageCreativity,
          );
        });
      });
    });
  };

  const cancelAll = async () => {
    const jobs = Array.from(jobsRef.current.values());
    jobsRef.current.clear();
    for (const job of jobs) {
      job.controller.abort();
      if (job.replicateJobIds.length) {
        fetch("/api/generate/cancel", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ jobIds: job.replicateJobIds }),
        }).catch(() => undefined);
      }
    }
    setJobStatus(null);
    setActiveJobCount(0);
    // Mark any remaining pending tiles as canceled errors.
    setTiles((current) =>
      current.map((t) => (t.status === "pending" ? { ...t, status: "error", error: "Zrušeno uživatelem." } : t)),
    );
  };

  const dismissTile = (tileId: string) => {
    setTiles((current) => current.filter((t) => t.id !== tileId));
  };

  const clearAll = () => {
    setTiles([]);
    setError(null);
  };

  const retryTile = (tileId: string) => {
    const target = tiles.find((t) => t.id === tileId);
    const targetSource = sources.find((source) => source.id === target?.sourceId) ?? activeSource;
    if (!target || !targetSource) return;
    // Replace the failed tile with a fresh pending tile in place.
    const controller = new AbortController();
    const jobId = randomId();
    const freshTile: Tile = {
      ...target,
      id: randomId(),
      jobId,
      status: "pending",
      url: undefined,
      error: undefined,
    };
    const job: Job = { id: jobId, controller, replicateJobIds: [], tileIds: [freshTile.id] };
    jobsRef.current.set(jobId, job);
    setTiles((current) => current.map((t) => (t.id === tileId ? freshTile : t)));
    setActiveJobCount((n) => n + 1);

    (async () => {
      try {
        const urls = await submitJob(
          targetSource.file,
          freshTile.engine,
          1,
          freshTile.distance,
          freshTile.noise,
          freshTile.strength,
          freshTile.ipAdapterScale ?? ipAdapterScale,
          freshTile.ipAdapterSteps ?? ipAdapterSteps,
          freshTile.chigoScale ?? chigoScale,
          freshTile.chigoSteps ?? chigoSteps,
          freshTile.sdxlGuidance ?? sdxlGuidance,
          freshTile.sdxlStrength ?? sdxlStrength,
          freshTile.sdxlSteps ?? sdxlSteps,
          freshTile.stableGuidance ?? stableGuidance,
          freshTile.stableStrength ?? stableStrength,
          freshTile.stableSteps ?? stableSteps,
          freshTile.sdVariationGuidance ?? sdVariationGuidance,
          freshTile.sdVariationSteps ?? sdVariationSteps,
          freshTile.fofrCfg ?? fofrCfg,
          freshTile.fofrSteps ?? fofrSteps,
          freshTile.fofrIpWeight ?? fofrIpWeight,
          freshTile.zImageCreativity ?? zImageCreativity,
          controller.signal,
          (replicateIds) => {
            const j = jobsRef.current.get(jobId);
            if (j) j.replicateJobIds = replicateIds;
          },
        );
        setTiles((current) =>
          current.map((t) =>
            t.id === freshTile.id
              ? urls[0]
                ? { ...t, status: "done", url: urls[0] }
                : { ...t, status: "error", error: "Prázdný výstup" }
              : t,
          ),
        );
      } catch (err) {
        const message = err instanceof Error ? err.message : "Generování selhalo";
        setTiles((current) => current.map((t) => (t.id === freshTile.id ? { ...t, status: "error", error: message } : t)));
      } finally {
        jobsRef.current.delete(jobId);
        setActiveJobCount((n) => Math.max(0, n - 1));
        if (jobsRef.current.size === 0) setJobStatus(null);
      }
    })();
  };

  const download = async (url: string, index: number) => {
    const res = await fetch(url);
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `sibling-${index + 1}.png`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const cols = gridColsFor(totalTiles);
  const statusLabel = isGenerating
    ? `běží ${activeJobCount} · ${jobStatus || "processing"}`
    : totalTiles
      ? `${doneTiles}/${totalTiles} hotovo`
      : "připraveno";
  const panelTone = isLight
      ? {
        page: {},
        text: "text-[#26251e]",
        soft: "text-[rgba(38,37,30,0.62)]",
        darkPanel: "border border-[rgba(38,37,30,0.1)] bg-[#ebeae5] text-[#26251e] shadow-[rgba(0,0,0,0.02)_0px_0px_16px,rgba(0,0,0,0.008)_0px_0px_8px]",
        lightPanel: "border border-[rgba(38,37,30,0.1)] bg-[#f7f7f4] text-[#26251e] shadow-[rgba(0,0,0,0.02)_0px_0px_16px,rgba(0,0,0,0.008)_0px_0px_8px]",
        control: "border border-[rgba(38,37,30,0.1)] bg-[#f7f7f4] p-[12px_14px]",
        ghost: "bg-[#f7f7f4] border border-[rgba(38,37,30,0.1)]",
      }
    : {
        page: { background: "#111827", color: "#f8fafc" },
        text: "text-slate-50",
        soft: "text-slate-300",
        darkPanel: "rounded-[31px] border border-white/10 bg-[rgba(15,23,42,0.98)] text-white",
        lightPanel: "rounded-[31px] border border-white/10 bg-[rgba(30,41,59,0.7)] text-white backdrop-blur-[24px]",
        control: "rounded-[24px] border border-white/10 bg-white/5 p-[12px_14px]",
        ghost: "bg-white/5 border border-white/10",
      };

  return (
    <div className="nx-shell min-h-screen transition-colors" style={panelTone.page}>
      <div className="nx-dot-field" />
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        onChange={(e) => e.target.files && appendFiles(e.target.files)}
      />
      <div className="nx-topbar">
        <div className="flex items-center gap-2">
          <div className="nx-topbar-badge">
            <span className="h-2 w-2 rounded-full bg-[#f97316]" />
            Variants Lab
          </div>
          <div className="nx-link">reference-first image system</div>
        </div>
        <div className="flex items-center gap-2">
          <span className="nx-link">{statusLabel}</span>
          <button onClick={() => setIsLight((value) => !value)} className="nx-chip" type="button">
            {isLight ? "Dark" : "Light"}
          </button>
          <a href="/gallery" target="_blank" rel="noreferrer" className="nx-chip">
            Galerie
          </a>
          <a href="/batch" target="_blank" rel="noreferrer" className="nx-chip">
            Batch
          </a>
        </div>
      </div>

      <main className="relative z-10 mx-auto flex w-full max-w-[1600px] flex-col gap-4 px-4 pb-8 pt-4 sm:px-6 lg:px-8">
        <section className="border-b border-[rgba(38,37,30,0.1)] px-1 pb-3">
          <div className="flex items-center justify-between gap-4">
          <p className={`truncate text-[11px] leading-4 tracking-[0.04em] ${panelTone.soft}`}>
            Reference-first image system pro varianty, sibling shots a paralelni prujezd modelu bez preplneneho ovladani.
          </p>
          <div className="flex shrink-0 items-center gap-2">
            <span className="nx-chip nx-chip-active">Variants</span>
            <span className="nx-chip">Inputs {sources.length}</span>
            <span className="nx-chip">Models {selectedEngines.length}</span>
            <span className="nx-chip">Modes {selectedDistances.length}</span>
            <button className="nx-button nx-button-primary-wide" onClick={generate} disabled={!sources.length}>
              {isGenerating ? `Generate ${activeJobCount}` : "Generate"}
            </button>
          </div>
          </div>
        </section>

        <section className="grid min-h-[calc(100vh-140px)] gap-4 xl:grid-cols-[280px_minmax(0,1fr)_300px]">
          <div className="flex flex-col gap-4">
            <div className="nx-shell-border">
              <div className={`${panelTone.darkPanel} flex min-h-[330px] flex-col p-4`}>
              <div className="mb-5 flex items-center justify-between">
                <div>
                  <div className={`nx-micro-strong ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/55"}`}>Input Relay</div>
                  <div className="mt-1 text-[20px] font-light tracking-[-0.03em]">Vstup a fronta</div>
                </div>
                <button className={`nx-chip ${isLight ? "" : "text-white/80"}`} onClick={chooseSourceImage} type="button">
                  Přidat
                </button>
              </div>

              <button
                type="button"
                className={`flex aspect-[1/1.02] w-full items-center justify-center overflow-hidden border text-left transition ${
                  dragging
                    ? isLight
                      ? "border-[rgba(38,37,30,0.2)] bg-[#f7f7f4]"
                      : "border-[#f97316]/70 bg-white/10"
                    : isLight
                      ? "border-[rgba(38,37,30,0.1)] bg-[#f2f1ed]"
                      : "border-white/10 bg-white/5"
                }`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                onClick={chooseSourceImage}
                title="Klik nebo přetažení více souborů"
              >
                {activeSource ? (
                  <img src={activeSource.preview} alt={activeSource.name} className="h-full w-full object-cover opacity-95" />
                ) : (
                  <div className={`flex max-w-[200px] flex-col items-center gap-3 text-center ${isLight ? "text-[rgba(38,37,30,0.75)]" : "text-white/80"}`}>
                    <span className={`nx-micro-strong ${isLight ? "text-[rgba(38,37,30,0.45)]" : "text-white/50"}`}>1. vstup</span>
                    <span className="text-[22px] leading-[1.05] tracking-[-0.03em]">Drop one or many source images.</span>
                    <span className={`nx-micro ${isLight ? "text-[rgba(38,37,30,0.5)]" : "text-white/45"}`}>klik nebo přetažení více souborů najednou</span>
                  </div>
                )}
              </button>

              <div className="mt-5 flex flex-wrap gap-2">
                {sources.map((source) => {
                  const active = source.id === activeSource?.id;
                  return (
                    <div
                      key={source.id}
                      className={`group relative h-16 w-16 overflow-hidden border transition ${
                        active ? "border-[rgba(38,37,30,0.2)] bg-[#e6e5e0]" : isLight ? "border-[rgba(38,37,30,0.1)] bg-[#f7f7f4]" : "border-white/10 opacity-75"
                      }`}
                      title={source.name}
                    >
                      <button
                        type="button"
                        onClick={() => setActiveSourceId(source.id)}
                        className="h-full w-full"
                        aria-label={`Aktivovat ${source.name}`}
                      >
                        <img src={source.preview} alt={source.name} className="h-full w-full object-cover" />
                      </button>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          removeSource(source.id);
                        }}
                        className={`absolute right-0 top-0 flex h-5 w-5 items-center justify-center border-l border-b text-[11px] leading-none opacity-0 transition group-hover:opacity-100 ${
                          isLight
                            ? "border-[rgba(38,37,30,0.1)] bg-[#f2eadc]/95 text-[#4a3820]"
                            : "border-white/10 bg-black/75 text-white/80"
                        }`}
                        aria-label={`Smazat ${source.name}`}
                        title="Smazat"
                      >
                        ×
                      </button>
                    </div>
                  );
                })}
              </div>

              <div className="mt-auto space-y-3 pt-4">
                <div className={`px-3 py-2.5 ${isLight ? "border border-[rgba(38,37,30,0.1)] bg-[#f7f7f4]" : "border border-white/10 bg-white/5"}`}>
                  <div className={`nx-micro-strong ${isLight ? "text-[rgba(38,37,30,0.45)]" : "text-white/45"}`}>Run Summary</div>
                  <div className={`mt-1.5 text-[12px] leading-5 ${isLight ? "text-[rgba(38,37,30,0.78)]" : "text-white/78"}`}>
                    {sources.length ? `${sources.length} vstupů` : "bez vstupů"} · {runPresetLabel}
                  </div>
                  <div className={`mt-1 text-[11px] leading-4 ${isLight ? "text-[rgba(38,37,30,0.45)]" : "text-white/45"}`}>
                    {selectedEngines.length} modelů · {selectedDistances.length} volnosti · {count} kusy na kombinaci
                  </div>
                </div>
                <div className={`h-[2px] w-full overflow-hidden rounded-full ${isLight ? "bg-[rgba(38,37,30,0.1)]" : "bg-white/10"}`}>
                  <div className={`h-full transition-all duration-500 ${isLight ? "bg-[#f54e00]" : "bg-[#f97316]"}`} style={{ width: `${progress}%` }} />
                </div>
              </div>
            </div>
            </div>

            <div className="nx-shell-border">
              <div className={`${panelTone.lightPanel} flex min-h-[280px] flex-col p-4`}>
              <div className="mb-4 flex items-center justify-between gap-4">
                <div>
                  <div className="nx-micro-strong">Command Layer</div>
                  <div className="mt-1 text-[18px] font-light tracking-[-0.03em]">Rozsah experimentu</div>
                </div>
                <button onClick={generate} disabled={!sources.length} className="nx-button">
                  {isGenerating ? `Running ${activeJobCount}` : "Generate"}
                </button>
              </div>

              <div className={`${panelTone.control} space-y-3`}>
                <div>
                  <div className="nx-micro-strong">2. rozsah běhu</div>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <button type="button" onClick={() => setModelScope("single")} className={`nx-chip w-full justify-start ${modelScope === "single" ? "nx-chip-active" : ""}`}>1 model</button>
                    <button type="button" onClick={() => setModelScope("all")} className={`nx-chip w-full justify-start ${modelScope === "all" ? "nx-chip-active" : ""}`}>všechny modely</button>
                    <button type="button" onClick={() => setDistanceScope("single")} className={`nx-chip w-full justify-start ${distanceScope === "single" ? "nx-chip-active" : ""}`}>1 volnost</button>
                    <button type="button" onClick={() => setDistanceScope("all")} className={`nx-chip w-full justify-start ${distanceScope === "all" ? "nx-chip-active" : ""}`}>všechny 4</button>
                  </div>
                </div>

                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <span className="nx-micro-strong">3. množství</span>
                    <span className="text-[12px] font-medium text-[#f97316]">{count}</span>
                  </div>
                  <input type="range" min={1} max={8} step={1} value={count} onChange={(e) => setCount(Number(e.target.value))} />
                </div>

                <div className="grid grid-cols-2 gap-2">
                    <div className={`${isLight ? "border border-[rgba(38,37,30,0.1)] bg-[#ebeae5]" : "rounded-[18px] border border-slate-200/80 bg-white/70"} p-2.5`}>
                    <div className="nx-micro-strong">kombinace</div>
                    <div className="mt-1.5 text-[26px] leading-none tracking-[-0.05em]">{plannedJobs}</div>
                    <div className="mt-1 text-[11px] leading-4 text-slate-500">vstupy × modely × volnosti</div>
                  </div>
                    <div className={`${isLight ? "border border-[rgba(38,37,30,0.1)] bg-[#ebeae5]" : "rounded-[18px] border border-slate-200/80 bg-white/70"} p-2.5`}>
                    <div className="nx-micro-strong">výstupy</div>
                    <div className="mt-1.5 text-[26px] leading-none tracking-[-0.05em]">{plannedOutputs}</div>
                    <div className="mt-1 text-[11px] leading-4 text-slate-500">celkem obrázků po doběhu</div>
                  </div>
                </div>
              </div>

              <div className={`${isLight ? "mt-4 border border-[rgba(38,37,30,0.1)] bg-[#ebeae5] p-3" : "mt-4 rounded-[22px] border border-slate-200/80 bg-white/70 p-3"}`}>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <span className="nx-micro-strong">5. výchozí volnost</span>
                  <span className="text-[11px] leading-4 text-slate-500">{DISTANCE_COPY[distance]}</span>
                </div>
                <div className="space-y-1.5">
                  {DISTANCE_VALUES.map((option) => (
                    <button
                      key={option}
                      type="button"
                      onClick={() => {
                        setDistance(option);
                        setComfyNoise(COMFY_DEFAULTS[option].noise);
                        setComfyStrength(COMFY_DEFAULTS[option].strength);
                        setIpAdapterScale(option === "locked" ? 0.82 : option === "sibling" ? 0.66 : option === "looser" ? 0.52 : 0.4);
                        setIpAdapterSteps(option === "locked" ? 55 : option === "sibling" ? 48 : option === "looser" ? 44 : 40);
                        setChigoScale(option === "locked" ? 0.92 : option === "sibling" ? 0.82 : option === "looser" ? 0.68 : 0.54);
                        setChigoSteps(option === "locked" ? 80 : option === "sibling" ? 68 : option === "looser" ? 58 : 48);
                        setSdxlGuidance(option === "locked" ? 3.6 : option === "sibling" ? 3.2 : option === "looser" ? 2.9 : 2.6);
                        setSdxlStrength(option === "locked" ? 0.42 : option === "sibling" ? 0.5 : option === "looser" ? 0.58 : 0.66);
                        setSdxlSteps(option === "locked" ? 40 : option === "sibling" ? 36 : option === "looser" ? 32 : 28);
                        setStableGuidance(option === "new-frame" ? 3.2 : 3.8);
                        setStableStrength(option === "new-frame" ? 0.92 : option === "looser" ? 0.82 : 0.68);
                        setStableSteps(30);
                        setSdVariationGuidance(option === "locked" ? 3.4 : option === "sibling" ? 3 : option === "looser" ? 2.7 : 2.4);
                        setSdVariationSteps(option === "locked" ? 28 : option === "sibling" ? 25 : option === "looser" ? 22 : 20);
                        setFofrCfg(option === "locked" ? 3.6 : option === "sibling" ? 3.2 : option === "looser" ? 2.9 : 2.6);
                        setFofrSteps(option === "locked" ? 54 : option === "sibling" ? 48 : option === "looser" ? 44 : 40);
                        setFofrIpWeight(option === "locked" ? 0.86 : option === "sibling" ? 0.76 : option === "looser" ? 0.64 : 0.52);
                        setZImageCreativity(option === "locked" ? 0.36 : option === "sibling" ? 0.5 : option === "looser" ? 0.66 : 0.8);
                      }}
                      className={`grid w-full grid-cols-[minmax(0,1fr)_72px] items-center gap-2 border px-3 py-2 text-left transition ${
                        distance === option
                          ? isLight
                            ? "border-[rgba(38,37,30,0.2)] bg-[#f7f7f4] text-[#26251e]"
                            : "border-[#f97316]/50 bg-[#f97316]/8 text-slate-900"
                          : isLight
                            ? "border-[rgba(38,37,30,0.1)] bg-[#f2f1ed] text-[rgba(38,37,30,0.62)]"
                            : "border-slate-200 bg-white/55 text-slate-500"
                      }`}
                    >
                      <span className="text-[12px] leading-4">{DISTANCE_COPY[option]}</span>
                      <span className={`text-right text-[11px] uppercase tracking-[0.08em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-slate-400"}`}>{option}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-auto flex gap-2 pt-5">
                {tiles.length ? (
                  <button type="button" onClick={clearAll} className="nx-button-secondary">
                    Vyčistit
                  </button>
                ) : null}
                {isGenerating ? (
                  <button type="button" onClick={cancelAll} className="nx-button-danger">
                    Zrušit vše
                  </button>
                ) : null}
              </div>
            </div>
          </div>
          </div>

          <section className="space-y-3">
            <div className="flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex items-center justify-between">
                  <span className="nx-link">{progress}% complete</span>
                  <span className="nx-link">{doneTiles}/{totalTiles || 0}</span>
                </div>
                <div className="nx-progress" aria-label="Progress">
                  <div className="nx-progress-bar" style={{ width: `${progress}%` }} />
                </div>
              </div>
              {isGenerating ? (
                <button onClick={cancelAll} className="nx-button-danger shrink-0">
                  Zrušit
                </button>
              ) : null}
              {!isGenerating && totalTiles > 0 ? (
                <button onClick={clearAll} className="nx-button-secondary shrink-0">
                  Vyčistit
                </button>
              ) : null}
            </div>

            {tiles.length === 0 ? (
              <div className="flex min-h-[640px] items-center justify-center bg-transparent">
                <span className="nx-micro-strong">{sources.length ? "stiskni generate" : ""}</span>
              </div>
            ) : (
              <div className="grid auto-rows-fr gap-4" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
                {tiles.map((tile, index) => {
                  const url = tile.url;
                  return (
                    <div key={tile.id} className={`group relative flex min-h-[360px] flex-col overflow-hidden ${isLight ? "border border-[rgba(38,37,30,0.1)] bg-[#f7f7f4] shadow-[rgba(0,0,0,0.02)_0px_0px_16px,rgba(0,0,0,0.008)_0px_0px_8px]" : "nx-output-card"}`}>
                      {tile.status === "done" && url ? (
                        <>
                          <button className={`flex min-h-0 flex-1 cursor-zoom-in items-center justify-center p-4 ${isLight ? "bg-[#f7f7f4]" : "bg-white/40"}`} onClick={() => setSelectedImage(url)} title="Klik pro zvětšení">
                            <img src={url} alt={`variant ${index + 1}`} className="h-full w-full object-contain" />
                          </button>
                          <div className={`border-t px-4 py-3 ${isLight ? "border-[rgba(38,37,30,0.1)]" : "border-slate-200/80"}`}>
                            <div className={`truncate text-[11px] uppercase tracking-[0.16em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-slate-500"}`}>{tile.settings}</div>
                            <div className={`mt-1 text-[12px] ${isLight ? "text-[rgba(38,37,30,0.4)]" : "text-slate-400"}`}>{tile.sourceName || "source"}</div>
                          </div>
                          <button onClick={() => download(url, index)} className={`absolute right-3 top-3 px-3 py-2 text-[11px] opacity-0 transition group-hover:opacity-100 ${isLight ? "border border-[rgba(38,37,30,0.1)] bg-[#f2eadc]/90 text-[#4a3820]" : "bg-[rgba(15,23,42,0.85)] text-white"}`}>
                            stáhnout
                          </button>
                          <button onClick={() => dismissTile(tile.id)} className={`absolute left-3 top-3 px-3 py-2 text-[11px] opacity-0 transition group-hover:opacity-100 ${isLight ? "border border-[rgba(38,37,30,0.1)] bg-[#f2eadc]/90 text-[#4a3820]" : "bg-white/80 text-slate-700"}`}>
                            odstranit
                          </button>
                        </>
                      ) : tile.status === "error" ? (
                        <div className="flex h-full flex-col justify-between gap-4 p-5">
                          <div>
                            <div className="text-[11px] uppercase tracking-[0.16em] text-slate-400">{tile.settings}</div>
                            <div className="mt-6 text-[12px] uppercase tracking-[0.18em] text-red-500">selhalo</div>
                            <div className="mt-2 text-[13px] leading-5 text-slate-500">{tile.error}</div>
                          </div>
                          <div className="flex justify-end gap-2">
                            <button onClick={() => dismissTile(tile.id)} className="nx-button-secondary">zahodit</button>
                            <button onClick={() => retryTile(tile.id)} className="nx-button">zkusit znovu</button>
                          </div>
                        </div>
                      ) : (
                        <div className={`flex h-full flex-col items-center justify-center gap-5 p-5 ${isLight ? "bg-[#ebeae5]" : "bg-white/45"}`}>
                          <div className={`h-14 w-14 animate-spin border ${isLight ? "border-[rgba(38,37,30,0.18)] border-t-[#8b6f3d]" : "border-slate-300 border-t-[#f97316]"}`} />
                          <div className={`max-w-[85%] text-center text-[11px] uppercase tracking-[0.16em] ${isLight ? "text-[rgba(38,37,30,0.45)]" : "text-slate-400"}`}>{tile.settings}</div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          <div className="nx-shell-border">
            <div className={`${panelTone.darkPanel} flex min-h-[690px] flex-col p-5`}>
              <div className="mb-5">
                <div className={`nx-micro-strong ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/55"}`}>Engine Matrix</div>
                <div className="mt-1 text-[20px] font-light tracking-[-0.03em]">Modely a tuning</div>
              </div>

              <div className="grid grid-cols-1 gap-2">
                {ENGINE_ORDER.map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setEngine(option)}
                    className={`border px-4 py-3 text-left text-[13px] leading-5 transition ${
                      engine === option
                        ? isLight
                          ? "border-[rgba(38,37,30,0.2)] bg-[#f7f7f4] text-[#26251e]"
                          : "border-[#f97316]/60 bg-white/12 text-white"
                        : isLight
                          ? "border-[rgba(38,37,30,0.1)] bg-[#f2f1ed] text-[rgba(38,37,30,0.62)]"
                          : "border-white/10 bg-white/5 text-white/65"
                    }`}
                    title={ENGINE_COPY[option]}
                  >
                    {ENGINE_COPY[option]}
                  </button>
                ))}
              </div>

              <div className="mt-5 space-y-3">
                {engine === "z-image" ? (
                  <div className="nx-dark-control">
                    <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}>
                      <span>kreativita</span>
                      <span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{zImageCreativity.toFixed(2)}</span>
                    </div>
                    <input type="range" min={0.2} max={0.95} step={0.01} value={zImageCreativity} onChange={(e) => setZImageCreativity(Number(e.target.value))} />
                  </div>
                ) : null}

                {engine === "comfy-unclip" ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>noise</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{comfyNoise.toFixed(2)}</span></div>
                      <input type="range" min={0} max={0.35} step={0.01} value={comfyNoise} onChange={(e) => setComfyNoise(Number(e.target.value))} />
                    </div>
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>strength</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{comfyStrength.toFixed(2)}</span></div>
                      <input type="range" min={0.35} max={1} step={0.01} value={comfyStrength} onChange={(e) => setComfyStrength(Number(e.target.value))} />
                    </div>
                  </div>
                ) : null}

                {engine === "ip-adapter-sdxl" ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>scale</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{ipAdapterScale.toFixed(2)}</span></div>
                      <input type="range" min={0.2} max={1} step={0.01} value={ipAdapterScale} onChange={(e) => setIpAdapterScale(Number(e.target.value))} />
                    </div>
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>steps</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{Math.round(ipAdapterSteps)}</span></div>
                      <input type="range" min={20} max={80} step={1} value={ipAdapterSteps} onChange={(e) => setIpAdapterSteps(Number(e.target.value))} />
                    </div>
                  </div>
                ) : null}

                {engine === "chigozienri-ip-adapter-sdxl" ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>scale</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{chigoScale.toFixed(2)}</span></div>
                      <input type="range" min={0.3} max={1} step={0.01} value={chigoScale} onChange={(e) => setChigoScale(Number(e.target.value))} />
                    </div>
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>steps</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{Math.round(chigoSteps)}</span></div>
                      <input type="range" min={24} max={100} step={1} value={chigoSteps} onChange={(e) => setChigoSteps(Number(e.target.value))} />
                    </div>
                  </div>
                ) : null}

                {engine === "sdxl-artistic" ? (
                  <div className="grid gap-3 md:grid-cols-3">
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>guidance</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{sdxlGuidance.toFixed(1)}</span></div>
                      <input type="range" min={1.5} max={6} step={0.1} value={sdxlGuidance} onChange={(e) => setSdxlGuidance(Number(e.target.value))} />
                    </div>
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>strength</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{sdxlStrength.toFixed(2)}</span></div>
                      <input type="range" min={0.2} max={0.9} step={0.01} value={sdxlStrength} onChange={(e) => setSdxlStrength(Number(e.target.value))} />
                    </div>
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>steps</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{Math.round(sdxlSteps)}</span></div>
                      <input type="range" min={20} max={60} step={1} value={sdxlSteps} onChange={(e) => setSdxlSteps(Number(e.target.value))} />
                    </div>
                  </div>
                ) : null}

                {engine === "stable" ? (
                  <div className="grid gap-3 md:grid-cols-3">
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>guidance</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{stableGuidance.toFixed(1)}</span></div>
                      <input type="range" min={1.5} max={6} step={0.1} value={stableGuidance} onChange={(e) => setStableGuidance(Number(e.target.value))} />
                    </div>
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>strength</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{stableStrength.toFixed(2)}</span></div>
                      <input type="range" min={0.2} max={1} step={0.01} value={stableStrength} onChange={(e) => setStableStrength(Number(e.target.value))} />
                    </div>
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>steps</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{Math.round(stableSteps)}</span></div>
                      <input type="range" min={20} max={60} step={1} value={stableSteps} onChange={(e) => setStableSteps(Number(e.target.value))} />
                    </div>
                  </div>
                ) : null}

                {engine === "sd-variation" ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>guidance</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{sdVariationGuidance.toFixed(1)}</span></div>
                      <input type="range" min={1} max={10} step={0.1} value={sdVariationGuidance} onChange={(e) => setSdVariationGuidance(Number(e.target.value))} />
                    </div>
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>steps</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{Math.round(sdVariationSteps)}</span></div>
                      <input type="range" min={1} max={50} step={1} value={sdVariationSteps} onChange={(e) => setSdVariationSteps(Number(e.target.value))} />
                    </div>
                  </div>
                ) : null}

                {engine === "fofr-any-comfyui-workflow" ? (
                  <div className="grid gap-3 md:grid-cols-3">
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>cfg</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{fofrCfg.toFixed(1)}</span></div>
                      <input type="range" min={1.5} max={6} step={0.1} value={fofrCfg} onChange={(e) => setFofrCfg(Number(e.target.value))} />
                    </div>
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>ip weight</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{fofrIpWeight.toFixed(2)}</span></div>
                      <input type="range" min={0.2} max={1} step={0.01} value={fofrIpWeight} onChange={(e) => setFofrIpWeight(Number(e.target.value))} />
                    </div>
                    <div className="nx-dark-control">
                      <div className={`mb-2 flex items-center justify-between text-[12px] uppercase tracking-[0.14em] ${isLight ? "text-[rgba(38,37,30,0.55)]" : "text-white/50"}`}><span>steps</span><span className={isLight ? "text-[#f54e00]" : "text-[#f97316]"}>{Math.round(fofrSteps)}</span></div>
                      <input type="range" min={20} max={70} step={1} value={fofrSteps} onChange={(e) => setFofrSteps(Number(e.target.value))} />
                    </div>
                  </div>
                ) : null}
              </div>

              {error ? <p className="mt-4 text-[12px] leading-5 text-red-300">{error}</p> : null}
            </div>
          </div>
        </section>
      </main>

      {selectedImage ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black p-2"
          onClick={() => setSelectedImage(null)}
          title="Klik zavře"
        >
          <img src={selectedImage} alt="large variant" className="max-h-[99vh] max-w-[99vw] cursor-zoom-out object-contain" />
        </div>
      ) : null}
    </div>
  );
}
