import React, { useEffect, useMemo, useRef, useState } from "react";
import StudioView from "./StudioView";

const API_URL = import.meta.env.VITE_API_URL || "";
const POLL_INTERVAL = 1500;
const PRESET_STORAGE_KEY = "img2img-presets-v1";
const DEFAULT_ENGINE = { mode: "quick", conditioningMode: "style", sampler: "dpmpp_2m_sde", schedule: "karras", seed: "-1", prompt: "", negativePrompt: "", maxSide: 1536, detailStrength: 0.25, detailSteps: 15 };
const EMPTY_JOB = {
  id: "",
  status: "idle",
  progress: 0,
  message: "Idle",
  logs: [],
  result: null,
  error: null,
};

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function buildImageUrl(path) {
  if (!path) return "";
  if (
    path.startsWith("http://") ||
    path.startsWith("https://") ||
    path.startsWith("data:")
  )
    return path;
  return `${API_URL}${path}`;
}

function loadStoredPresets() {
  try {
    const raw = window.localStorage.getItem(PRESET_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveStoredPresets(presets) {
  window.localStorage.setItem(PRESET_STORAGE_KEY, JSON.stringify(presets));
}

function App() {
  const [models, setModels] = useState([]);
  const [loras, setLoras] = useState([]);
  const [inputItems, setInputItems] = useState([]);
  const restoreRecentAllowed = useRef(true);
  const inputUrls = useRef(new Set());
  const submitting = useRef(false);
  const pendingSubmissions = useRef(0);
  const plannedCount = useRef(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [plannedOutputs, setPlannedOutputs] = useState(0);
  const [submittedOutputs, setSubmittedOutputs] = useState(0);
  const [startedAt, setStartedAt] = useState(null);
  const recordsCache = useRef(new Map());
  const deletedIds = useRef(new Set());
  const previewUrl = inputItems[0]?.url || "";
  const [imageSize, setImageSize] = useState({ width: 1024, height: 1024 });
  const [resizeScale, setResizeScale] = useState(2);
  const [inputScale, setInputScale] = useState(1);
  const [selectedModelIds, setSelectedModelIds] = useState(["tuymans_sdxl"]);
  const modelId = selectedModelIds[0];
  const setModelId = (id) => setSelectedModelIds([id]);
  const [generationMode, setGenerationMode] = useState("checkpoint");
  const [atelier, setAtelier] = useState({mode: "noise", theme: "all", modelIds: ["tuymans_modal_2400"], count: 4,
    width: 1024, height: 1024, scale: 2, cfg: 0.5, steps: 28, seed: "-1", denoise: 0.52,
    sampler: "dpmpp_2m", schedule: "karras"});
  const [loraId, setLoraId] = useState("none");
  const [loraStrength, setLoraStrength] = useState(0.8);
  const [numImages, setNumImages] = useState(2);
  const [denoise, setDenoise] = useState(0.52);
  const [cfg, setCfg] = useState(5);
  const [steps, setSteps] = useState(28);
  const [engine, setEngine] = useState(DEFAULT_ENGINE);
  const [results, setResults] = useState([]);
  const [batchResults, setBatchResults] = useState([]);
  const [libraryItems, setLibraryItems] = useState([]);
  const [selectedImage, setSelectedImage] = useState(null);
  const [presets, setPresets] = useState([]);
  const [presetName, setPresetName] = useState("");
  const [selectedPresetId, setSelectedPresetId] = useState("");
  const [error, setError] = useState("");
  const [submissionErrors, setSubmissionErrors] = useState([]);
  const [job, setJob] = useState(EMPTY_JOB);
  const [activeJobs, setActiveJobs] = useState(() => {
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
  });

  useEffect(() => {
    const next = new Set(inputItems.map((item) => item.url));
    inputUrls.current.forEach((url) => {
      if (!next.has(url)) URL.revokeObjectURL(url);
    });
    inputUrls.current = next;
  }, [inputItems]);
  useEffect(
    () => () => {
      inputUrls.current.forEach((url) => URL.revokeObjectURL(url));
    },
    [],
  );

  useEffect(() => {
    setPresets(loadStoredPresets());
  }, []);

  useEffect(() => {
    if (!previewUrl) return;
    const probe = new window.Image();
    probe.onload = () =>
      setImageSize({ width: probe.naturalWidth, height: probe.naturalHeight });
    probe.src = previewUrl;
    return () => {
      probe.onload = null;
    };
  }, [previewUrl]);

  useEffect(() => {
    fetch(`${API_URL}/api/options`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!data) return;
        if (data.models?.length) {
          setModels(data.models);
          setModelId(
            data.models.find((item) => item.kind !== "base")?.id ||
              "tuymans_sdxl",
          );
        }
        if (data.loras?.length) {
          setLoras(data.loras);
          setLoraId(
            data.loras.find((item) => item.id !== "none")?.id || "none",
          );
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadLibrary(true).catch(() => {});
  }, []);

  useEffect(() => {
    if (!activeJobs.length) return undefined;
    let cancelled = false;
    let timer;
    const known = recordsCache.current;
    const poll = async () => {
      const responses = await mapSettled(activeJobs, 8, async (item) => {
        const previous = known.get(item.job_id);
        if (previous && ["completed", "failed"].includes(previous.status))
          return previous;
        const response = await fetch(`${API_URL}/api/jobs/${item.job_id}`);
        if (response.status === 401) {
          window.location.assign("/login");
          throw new Error("Sign in required");
        }
        if (response.status === 404)
          return {
            id: item.job_id,
            status: "failed",
            progress: 0,
            error: {
              detail: "Job expired. Saved images remain in the library.",
            },
          };
        const data = await response.json();
        if (!response.ok)
          throw new Error(data.detail || "Connection interrupted");
        return data;
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
        ["completed", "failed"].includes(record.status),
      ).length;
      const failed = records.filter((record) => record.status === "failed");
      const logs = records
        .flatMap((record) => record.logs || [])
        .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
        .slice(-10);
      const ready = slots.filter(Boolean);
      setLibraryItems((current) => {
        const ids = new Set(current.map((item) => item.id));
        return [...ready.filter((item) => !ids.has(item.id) && !deletedIds.current.has(item.id)), ...current];
      });
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
              : "completed"
            : "running",
        progress,
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

  const generationSize = useMemo(() => {
    const ratio = Math.min(1, 1536 / Math.max(imageSize.width * inputScale, imageSize.height * inputScale));
    return {width: Math.max(64, Math.floor(imageSize.width * inputScale * ratio / 8) * 8), height: Math.max(64, Math.floor(imageSize.height * inputScale * ratio / 8) * 8)};
  }, [imageSize, inputScale]);
  const targetSize = {width: Math.round(generationSize.width * resizeScale), height: Math.round(generationSize.height * resizeScale)};

  const isGenerating =
    isSubmitting ||
    Boolean(activeJobs.length) ||
    job.status === "preparing" ||
    job.status === "queued" ||
    job.status === "waiting" ||
    job.status === "running";
  const progressValue =
    job.status === "completed"
      ? 100
      : Math.max(
          0,
          Math.min(
            isGenerating ? 99 : 100,
            Math.round((job.progress || 0) * 100),
          ),
        );
  const readyCount = batchResults.filter(Boolean).length;
  const outputCount = isGenerating
    ? Math.max(
        batchResults.length,
        plannedOutputs,
        activeJobs.reduce((sum, item) => sum + item.expected_images, 0),
      )
    : batchResults.length || 0;
  const sourceCount =
    inputItems.length ||
    new Set(activeJobs.map((item) => item.source_id || item.source_name))
      .size ||
    new Set(
      results
        .filter(Boolean)
        .map(
          (item) =>
            item.source_id || item.source_name || item.settings?.source_name,
        ),
    ).size;
  const visibleLogs = job.logs?.slice(-10) || [];

  function buildPresetPayload() {
    return {
      generationMode,
      atelier,
      modelId,
      selectedModelIds,
      loraId,
      loraStrength,
      numImages,
      denoise,
      cfg,
      steps,
      resizeScale,
      inputScale,
      engine,
    };
  }

  function applyPreset(preset) {
    const mode =
      preset.generationMode ||
      (preset.loraId && preset.loraId !== "none" ? "lora" : "checkpoint");
    setGenerationMode(mode);
    if (preset.atelier) setAtelier(current => ({...current, ...preset.atelier}));
    setModelId(
      preset.modelId && preset.modelId !== "sdxl_base"
        ? preset.modelId
        : "tuymans_sdxl",
    );
    if (Array.isArray(preset.selectedModelIds)) {
      const ids = [...new Set(preset.selectedModelIds)].filter(id => models.some(model => model.id === id && model.kind !== "base"));
      if (ids.length) setSelectedModelIds(ids);
    }
    setLoraId(
      preset.loraId && preset.loraId !== "none"
        ? preset.loraId
        : loras.find((item) => item.id !== "none")?.id || "none",
    );
    setLoraStrength(Number(preset.loraStrength ?? 0.8));
    setNumImages(Number(preset.numImages ?? 2));
    setDenoise(Number(preset.denoise ?? 0.52));
    setCfg(Number(preset.cfg ?? 5));
    setSteps(Number(preset.steps ?? 28));
    setEngine({...DEFAULT_ENGINE, ...(preset.engine || {}), mode: "quick", maxSide: 1536});
    setInputScale(Number(preset.inputScale ?? 1));
    setResizeScale(Math.min(preset.engine?.mode === "detail" ? 2 : 4, Number(preset.resizeScale ?? 2)));
  }

  function handlePresetSelect(event) {
    const nextId = event.target.value;
    setSelectedPresetId(nextId);
    const preset = presets.find((item) => item.id === nextId);
    if (!preset) return;
    setPresetName(preset.name);
    applyPreset(preset);
  }

  function handleSavePreset() {
    const name = presetName.trim();
    if (!name) {
      setError("Preset name required.");
      return;
    }

    const existing = presets.find(
      (item) => item.name.toLowerCase() === name.toLowerCase(),
    );
    const nextPreset = {
      id: existing?.id || crypto.randomUUID(),
      name,
      ...buildPresetPayload(),
    };
    const nextPresets = existing
      ? presets.map((item) => (item.id === existing.id ? nextPreset : item))
      : [nextPreset, ...presets];
    setPresets(nextPresets);
    setSelectedPresetId(nextPreset.id);
    saveStoredPresets(nextPresets);
    setError("");
  }

  function handleDeletePreset() {
    if (!selectedPresetId) return;
    const nextPresets = presets.filter((item) => item.id !== selectedPresetId);
    setPresets(nextPresets);
    saveStoredPresets(nextPresets);
    setSelectedPresetId("");
    setPresetName("");
  }

  function handleFileChange(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (!files.length) return;
    if (
      files.some(
        (file) =>
          !["image/png", "image/jpeg", "image/webp"].includes(file.type),
      )
    ) {
      setError("Podporovány jsou PNG, JPEG a WebP.");
      return;
    }
    restoreRecentAllowed.current = false;
    const items = files.map((file) => ({
      id: crypto.randomUUID(),
      file,
      url: URL.createObjectURL(file),
    }));
    setInputItems((current) => [...current, ...items]);
    setResizeScale(1);
    setSelectedImage(null);
    setError("");
    if (!isGenerating) setJob(EMPTY_JOB);
  }

  async function handleGenerate() {
    if (!inputItems.length) return;
    const modelIds = generationMode === "lora" ? ["sdxl_base"] : [...new Set(selectedModelIds)];
    if (!modelIds.length) { setError("Vyber alespoň jeden checkpoint."); return; }
    if (
      !Number.isSafeInteger(numImages) ||
      numImages < 1 ||
      !Number.isSafeInteger(numImages * inputItems.length * modelIds.length)
    ) {
      setError("Počet variant musí být kladné celé číslo.");
      return;
    }
    const settings = {
      model_id: generationMode === "lora" ? "sdxl_base" : modelId,
      lora_id: generationMode === "lora" ? loraId : "none",
      denoise: Number(denoise),
      lora_strength: Number(loraStrength),
      cfg: Number(cfg),
      steps: Number(steps),
      sampler: engine.sampler,
      schedule: engine.schedule,
      conditioning_mode: "style",
      render_mode: "quick", seed: Number(engine.seed === "" ? -1 : engine.seed),
      prompt: "", negative_prompt: "",
      max_side: 1536, detail_strength: engine.detailStrength, detail_steps: engine.detailSteps,
      input_scale: inputScale,
      scale: Number(resizeScale.toFixed(2)),
    };
    const count = numImages;
    const total = inputItems.length * count * modelIds.length;
    const continuing = submitting.current || activeJobs.length > 0;
    pendingSubmissions.current += 1;
    submitting.current = true;
    plannedCount.current = (continuing ? Math.max(plannedCount.current, activeJobs.reduce((sum, item) => sum + item.expected_images, 0)) : 0) + total;
    setIsSubmitting(true);
    setPlannedOutputs(plannedCount.current);
    if (!continuing) {
      setSubmittedOutputs(0);
      setStartedAt(Date.now());
      recordsCache.current.clear();
      setSubmissionErrors([]);
      setBatchResults([]);
      setJob({...EMPTY_JOB, status: "preparing", message: "Odesílání do fronty"});
      window.localStorage.removeItem("img2img-last-batch");
    }
    restoreRecentAllowed.current = false;
    setError("");
    const accepted = [],
      issues = [];
    let sent = 0;
    // Malé přenosové dávky nemění celkový počet; každá varianta dostane vlastní GPU úlohu.
    for (const item of inputItems) {
      let image;
      try {
        image = await fileToBase64(item.file);
      } catch {
        issues.push(`${item.file.name}: obrázek nelze načíst.`);
        continue;
      }
      // One random seed per input, shared across models for a fair comparison.
      const inputSeed = settings.seed === -1 ? crypto.getRandomValues(new Uint32Array(1))[0] : settings.seed;
      for (const selectedModelId of modelIds) {
        for (let offset = 0; offset < count; offset += 8) {
          try {
            const response = await fetch(`${API_URL}/api/generate-batch`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                inputs: [{ name: item.file.name, image_base64: image }],
                settings: {
                  ...settings,
                  model_id: selectedModelId,
                  seed: (inputSeed + offset) % 4294967296,
                  num_images: Math.min(8, count - offset),
                },
              }),
            });
            if (response.status === 401) {
              window.location.assign("/login");
              throw new Error("Přihlášení vypršelo.");
            }
            const data = await response.json();
            if (!response.ok)
              throw new Error(
                typeof data.detail === "string"
                  ? data.detail
                  : "Odeslání se nezdařilo.",
              );
            const jobs = data.jobs.map((job) => ({
              ...job,
              source_id: item.id,
              source_name: item.file.name,
            }));
            accepted.push(...jobs);
            sent += jobs.reduce((sum, job) => sum + job.expected_images, 0);
            setActiveJobs((current) => [...current, ...jobs]);
            setSubmittedOutputs((current) => current + jobs.reduce((sum, job) => sum + job.expected_images, 0));
            issues.push(...(data.errors || []));
          } catch (error) {
            issues.push(`${item.file.name} / ${models.find(model => model.id === selectedModelId)?.name || selectedModelId}: ${error.message}`);
          }
        }
      }
    }
    pendingSubmissions.current -= 1;
    submitting.current = pendingSubmissions.current > 0;
    setIsSubmitting(submitting.current);
    setSubmissionErrors((current) => [...current, ...issues]);
    if (issues.length) setError(issues.join(" · "));
    plannedCount.current -= total - sent;
    setPlannedOutputs(plannedCount.current);
    if (!accepted.length && !continuing && !submitting.current)
      setJob({...EMPTY_JOB, status: "failed", message: "Žádná úloha se nepodařila odeslat."});
  }

  async function handleGenerateAtelier() {
    const modelIds = [...new Set(atelier.modelIds)].filter(id => models.some(model => model.id === id && model.kind !== "base"));
    const count = Number(atelier.count), total = count * modelIds.length;
    if (!modelIds.length || !Number.isSafeInteger(count) || count < 1 || !Number.isSafeInteger(total)) {
      setError("Vyber checkpoint a kladný celý počet studií."); return;
    }
    const settings = {generation_type: "atelier", atelier_mode: atelier.mode, atelier_theme: atelier.theme,
      width: atelier.width, height: atelier.height, scale: Number(atelier.scale), cfg: Number(atelier.cfg),
      steps: Number(atelier.steps), sampler: atelier.sampler, schedule: atelier.schedule, denoise: Number(atelier.denoise), render_mode: "quick"};
    const requestedSeed = Number(atelier.seed === "" ? -1 : atelier.seed);
    if (!Number.isInteger(requestedSeed) || requestedSeed < -1 || requestedSeed > 4294967295) {setError("Seed musí být celé číslo od −1 do 4294967295."); return;}
    const seed = requestedSeed === -1 ? crypto.getRandomValues(new Uint32Array(1))[0] : requestedSeed;
    const continuing = submitting.current || activeJobs.length > 0;
    pendingSubmissions.current += 1; submitting.current = true;
    plannedCount.current = (continuing ? Math.max(plannedCount.current, activeJobs.reduce((sum, item) => sum + item.expected_images, 0)) : 0) + total;
    setIsSubmitting(true); setPlannedOutputs(plannedCount.current);
    if (!continuing) {
      setSubmittedOutputs(0); setStartedAt(Date.now()); recordsCache.current.clear();
      setSubmissionErrors([]); setBatchResults([]); setJob({...EMPTY_JOB, status: "preparing", message: "Ateliér: odesílání do fronty"});
      window.localStorage.removeItem("img2img-last-batch");
    }
    restoreRecentAllowed.current = false; setError("");
    let sent = 0;
    const issues = [];
    for (let offset = 0; offset < count; offset += 8) {
      try {
        const response = await fetch(`${API_URL}/api/atelier-batch`, {method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({model_ids: modelIds, count: Math.min(8, count - offset), settings: {...settings, seed: (seed + offset) % 4294967296}})});
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Ateliér: odeslání se nezdařilo.");
        const jobs = data.jobs.map(job => ({...job, source_id: `atelier-${seed}-${offset + job.source_index}`, generation_type: "atelier"}));
        const accepted = jobs.reduce((sum, job) => sum + job.expected_images, 0); sent += accepted;
        setActiveJobs(current => [...current, ...jobs]); setSubmittedOutputs(current => current + accepted);
        issues.push(...(data.errors || []));
      } catch (error) { issues.push(error.message); }
    }
    pendingSubmissions.current -= 1; submitting.current = pendingSubmissions.current > 0;
    setIsSubmitting(submitting.current); setSubmissionErrors(current => [...current, ...issues]);
    if (issues.length) setError(issues.join(" · "));
    plannedCount.current -= total - sent; setPlannedOutputs(plannedCount.current);
    if (!sent && !continuing && !submitting.current) setJob({...EMPTY_JOB, status: "failed", message: "Ateliér: žádná úloha nebyla přijata."});
  }

  async function loadLibrary(restoreRecent = false) {
    const response = await fetch(`${API_URL}/api/library`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Library load failed.");
    }
    setLibraryItems((data.items || []).filter((item) => !deletedIds.current.has(item.id)));
    const historyResponse = await fetch(`${API_URL}/api/history`);
    if (!historyResponse.ok) throw new Error("Historii se nepodařilo načíst.");
    const history = await historyResponse.json();
    for (const id of history.deleted_ids || []) deletedIds.current.add(id);
    setResults((current) => {
      const ids = new Set(current.filter(Boolean).map((item) => item.id));
      return [...current, ...(history.items || []).filter((item) => !ids.has(item.id))].filter((item) => !item || !deletedIds.current.has(item.id));
    });
  }

  async function saveLibraryItem(itemId) {
    const response = await fetch(`${API_URL}/api/library/${itemId}`, {method: "POST"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Uložení se nezdařilo.");
    setLibraryItems((current) => current.some((item) => item.id === itemId) ? current : [data.item, ...current]);
    setResults((current) => current.map((item) => item?.id === itemId ? {...item, saved_to_library: true} : item));
  }

  async function deleteLibraryItem(itemId) {
    if (deletedIds.current.has(itemId)) return;
    const libraryIndex = libraryItems.findIndex((item) => item.id === itemId);
    const canvasIndex = results.findIndex((item) => item?.id === itemId);
    const libraryItem = libraryItems[libraryIndex];
    const canvasItem = results[canvasIndex];
    deletedIds.current.add(itemId);
    setLibraryItems((current) => current.filter((item) => item.id !== itemId));
    setResults((current) => current.filter((item) => item?.id !== itemId));
    if (selectedImage?.libraryId === itemId || selectedImage?.id === itemId) setSelectedImage(null);
    try {
      const response = await fetch(`${API_URL}/api/library/${itemId}`, {method: "DELETE"});
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Smazání se nezdařilo.");
      }
    } catch (error) {
      deletedIds.current.delete(itemId);
      const restore = (item, index) => (current) => {
        if (!item || current.some((entry) => entry?.id === itemId)) return current;
        const next = [...current];
        next.splice(Math.min(Math.max(0, index), next.length), 0, item);
        return next;
      };
      setLibraryItems(restore(libraryItem, libraryIndex));
      setResults(restore(canvasItem, canvasIndex));
      throw error;
    }
  }

  async function reorderLibraryItems(ids) {
    const response = await fetch(`${API_URL}/api/library/order`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Library reorder failed.");
    const positions = new Map(data.ids.map((id, index) => [id, index]));
    setLibraryItems((current) =>
      [...current].sort(
        (a, b) =>
          (positions.get(a.id) ?? Infinity) - (positions.get(b.id) ?? Infinity),
      ),
    );
  }

  function openResultImage(image, index) {
    setSelectedImage({
      ...image,
      context: "results",
      index,
      src: image.url
        ? buildImageUrl(image.url)
        : `data:image/${image.format || "png"};base64,${image.image_base64}`,
      width: image.width,
      height: image.height,
      downloadUrl: image.url
        ? buildImageUrl(image.url)
        : `data:image/${image.format || "png"};base64,${image.image_base64}`,
      filename: `img2img-output-${index + 1}.${image.format || "png"}`,
    });
  }

  function openLibraryImage(item) {
    setSelectedImage({
      ...item,
      context: "library",
      src: buildImageUrl(item.url),
      width: item.width,
      height: item.height,
      downloadUrl: buildImageUrl(item.url),
      filename: item.filename || `img2img-library-${item.id}.png`,
      libraryId: item.id,
    });
  }

  function downloadDataImage(image, index) {
    const anchor = document.createElement("a");
    anchor.href = image.url
      ? buildImageUrl(image.url)
      : `data:image/${image.format || "png"};base64,${image.image_base64}`;
    anchor.download = `img2img-output-${index + 1}.${image.format || "png"}`;
    anchor.click();
  }

  function downloadLibraryImage(item) {
    const anchor = document.createElement("a");
    anchor.href = buildImageUrl(item.url);
    anchor.download = item.filename || `img2img-library-${item.id}.png`;
    anchor.click();
  }

  function downloadSelectedImage() {
    if (!(selectedImage?.downloadUrl || selectedImage?.src)) return;
    const anchor = document.createElement("a");
    anchor.href = selectedImage.downloadUrl || selectedImage.src;
    anchor.download = selectedImage.filename || "img2img-output.png";
    anchor.click();
  }

  return (
    <StudioView
      {...{
        models,
        loras,
        inputItems,
        setInputItems,
        modelId,
        setModelId,
        selectedModelIds,
        setSelectedModelIds,
        generationMode,
        setGenerationMode,
        atelier, setAtelier, handleGenerateAtelier,
        loraId,
        setLoraId,
        loraStrength,
        setLoraStrength,
        numImages,
        setNumImages,
        denoise,
        setDenoise,
        cfg,
        setCfg,
        steps,
        setSteps,
        engine, setEngine,
        resizeScale,
        setResizeScale,
        inputScale, setInputScale, generationSize,
        targetSize,
        imageSize,
        results,
        libraryItems,
        saveLibraryItem,
        isGenerating,
        isSubmitting,
        plannedOutputs,
        submittedOutputs,
        outputCount,
        sourceCount,
        job,
        progressValue,
        readyCount,
        visibleLogs,
        startedAt,
        error,
        setError,
        presets,
        presetName,
        setPresetName,
        selectedPresetId,
        handlePresetSelect,
        handleSavePreset,
        handleDeletePreset,
        handleFileChange,
        handleGenerate,
        deleteLibraryItem,
        reorderLibraryItems,
        selectedImage,
        setSelectedImage,
        openResultImage,
        openLibraryImage,
        downloadDataImage,
        downloadLibraryImage,
        downloadSelectedImage,
      }}
    />
  );
}

async function mapSettled(items, concurrency, task) {
  const results = new Array(items.length);
  let cursor = 0;
  await Promise.all(
    Array.from({ length: Math.min(concurrency, items.length) }, async () => {
      while (cursor < items.length) {
        const index = cursor++;
        try {
          results[index] = {
            status: "fulfilled",
            value: await task(items[index], index),
          };
        } catch (reason) {
          results[index] = { status: "rejected", reason };
        }
      }
    }),
  );
  return results;
}

export default App;
