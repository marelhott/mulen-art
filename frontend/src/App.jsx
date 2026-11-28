import React, { useEffect, useMemo, useRef, useState } from "react";
import StudioView from "./StudioView";
import { useJobs, loadStoredJobs, EMPTY_JOB } from "./useJobs";
import { averageWorkerSeconds, controlsFromSettings, usageLabel, isMixId, mixEntry, MIX_STORAGE_KEY, idsForSource, sourceOf, planVariants, DEFAULT_VARIANTS, VARIANTS_STORAGE_KEY, atelierBaseSeed, atelierFromSettings } from "./studioTools";
import { randomId, safeStorage } from "./shared";
import { DEFAULT_REIMAGINE, planReimagine, plannedImages, reimagineFromSettings } from "./reimagineTools";
import { DEFAULT_VARI, DEFAULT_COLLAGE, COLLAGE_MAX_SOURCES, forCollage, planVari, planCollage, plannedImages as nanoPlannedImages, variFromSettings, collageFromSettings, usableModels } from "./nanoTools";
import { glitchSettings } from "./glitchTools";
import { usePresets } from "./usePresets";
import { useGallery } from "./useGallery";
import { useServerOptions } from "./useServerOptions";
import { useInputImages } from "./useInputImages";
import { apiFetch, buildImageUrl, readJson, reconcileOptionIds } from "./api";

const DEFAULT_ENGINE = { mode: "quick", conditioningMode: "style", sampler: "dpmpp_2m_sde", schedule: "karras", seed: "-1", prompt: "", negativePrompt: "", maxSide: 1536, detailStrength: 0.25, detailSteps: 15 };

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function App() {
  const [usage, setUsage] = useState(null);
  const [variants, setVariants] = useState(() => {
    try { return {...DEFAULT_VARIANTS, ...JSON.parse(safeStorage.get(VARIANTS_STORAGE_KEY) || "{}"), enabled: false}; }
    catch { return DEFAULT_VARIANTS; }
  });
  useEffect(() => {
    safeStorage.set(VARIANTS_STORAGE_KEY, JSON.stringify(variants));
  }, [variants]);
  // Checkpoint mixes live in the browser; each one is fully described by its id, so there is nothing to sync.
  const [mixIds, setMixIds] = useState(() => {
    try { const saved = JSON.parse(safeStorage.get(MIX_STORAGE_KEY) || "[]"); return Array.isArray(saved) ? saved.filter(isMixId) : []; }
    catch { return []; }
  });
  const { inputItems, setInputItems, imageSize } = useInputImages();
  const submitting = useRef(false);
  const pendingSubmissions = useRef(0);
  const plannedCount = useRef(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [plannedOutputs, setPlannedOutputs] = useState(0);
  const [submittedOutputs, setSubmittedOutputs] = useState(0);
  const [startedAt, setStartedAt] = useState(null);
  const recordsCache = useRef(new Map());
  const [resizeScale, setResizeScale] = useState(2);
  const [useRealsrgan, setUseRealsrgan] = useState(false);
  const [useRealEsrgan, setUseRealEsrgan] = useState(false);
  const [restormerMode, setRestormerMode] = useState('off');
  const [inputScale, setInputScale] = useState(1);
  const [selectedModelIds, setSelectedModelIds] = useState(["tuymans_sdxl"]);
  // Individual checkpoints and fusions are exclusive: only ids of the active source are ever generated.
  const [checkpointSource, setCheckpointSource] = useState("single");
  const modelId = idsForSource(selectedModelIds, checkpointSource)[0] ?? selectedModelIds[0];
  const setModelId = (id) => setSelectedModelIds([id]);
  const [generationMode, setGenerationMode] = useState("checkpoint");
  const [atelier, setAtelier] = useState({mode: "noise", theme: "all", archive: "hofmann", modelIds: ["tuymans_modal_2400"], source: "single", colorLevel: 2, count: 4,
    width: 1024, height: 1024, ratio: "random", scale: 2, cfg: 0.5, steps: 28, seed: "-1", denoise: 0.82,
    sampler: "dpmpp_2m", schedule: "karras"});
  const [reimagine, setReimagine] = useState(DEFAULT_REIMAGINE);
  const [vari, setVari] = useState(DEFAULT_VARI);
  const [collage, setCollage] = useState(DEFAULT_COLLAGE);
  const [loraId, setLoraId] = useState("none");
  const [loraStrength, setLoraStrength] = useState(0.8);
  const { archives, gpuHourlyUsd, nanoModels, archiveStatus, serverModels, loras, reload: reloadArchives } = useServerOptions({
    onModels: (data) => setSelectedModelIds(current => reconcileOptionIds(current,
      [...data, ...current.filter(id => mixEntry(id, data)).map(id => ({id}))],
      data.find(item => item.kind !== "base")?.id)),
    onLoras: (data) => setLoraId(current => reconcileOptionIds([current], data)[0]),
  });
  const models = useMemo(
    () => [...serverModels, ...mixIds.map((id) => mixEntry(id, serverModels)).filter(Boolean)],
    [serverModels, mixIds],
  );
  const [numImages, setNumImages] = useState(2);
  const [denoise, setDenoise] = useState(0.52);
  const [cfg, setCfg] = useState(5);
  const [steps, setSteps] = useState(28);
  const [engine, setEngine] = useState(DEFAULT_ENGINE);
  const [batchResults, setBatchResults] = useState([]);
  const { results, setResults, libraryItems, setLibraryItems, deletedIds, loadLibrary, galleryLoading } = useGallery();
  const [selectedImage, setSelectedImage] = useState(null);
  const [error, setError] = useState("");
  const [submissionErrors, setSubmissionErrors] = useState([]);
  const [job, setJob] = useState(EMPTY_JOB);
  const [activeJobs, setActiveJobs] = useState(loadStoredJobs);
  const { presets, presetName, setPresetName, selectedPresetId, handlePresetSelect, handleSavePreset, handleDeletePreset } =
    usePresets({ buildPayload: buildPresetPayload, applyPreset, setError });



  useEffect(() => {
    safeStorage.set(MIX_STORAGE_KEY, JSON.stringify(mixIds));
  }, [mixIds]);

  // `target` is where the new mix is selected right away: the canvas checkpoint list or the Atelier one.
  function addMix(id, target) {
    if (!mixEntry(id, serverModels)) { setError("Tuto fúzi nelze vytvořit: některý checkpoint není k dispozici."); return; }
    setMixIds(current => (current.includes(id) ? current : [...current, id]));
    // A new fusion switches the picker to fusions and selects it; the plain checkpoints stay remembered but off.
    if (target === "atelier") setAtelier(current => ({...current, source: "mix", modelIds: [...new Set([...current.modelIds, id])]}));
    else { setCheckpointSource("mix"); setSelectedModelIds(current => [...new Set([...current, id])]); }
  }
  function removeMix(id) {
    setMixIds(current => current.filter(item => item !== id));
    const fallback = serverModels.find(item => item.kind !== "base")?.id;
    setSelectedModelIds(current => {
      const next = current.filter(item => item !== id);
      if (next.length) return next;
      return fallback ? [fallback] : current;
    });
    setAtelier(current => { const next = current.modelIds.filter(item => item !== id); return {...current, modelIds: next.length ? next : ["tuymans_modal_2400"]}; });
  }

  // What the siblings would get for the first selected model; the real plan is rebuilt per input at submit time.
  const variantsPlan = useMemo(() => planVariants({
    count: Math.min(Math.max(1, Number(numImages) || 1), 12), distance: variants.distance, spread: variants.spread,
    prompt: variants.prompt, negativePrompt: variants.negative, seed: 12345,
    base: { denoise: Number(denoise), cfg: Number(cfg), loraStrength: Number(loraStrength), modelId: generationMode === "lora" ? "sdxl_base" : modelId },
  }), [numImages, variants, denoise, cfg, loraStrength, generationMode, modelId]);

  async function refreshUsage() {
    try {
      setUsage(await readJson(await apiFetch("/api/usage")));
    } catch {
      /* the budget label is informational; keep the last value */
    }
  }
  useEffect(() => { refreshUsage(); }, []);

  // Seconds of GPU time a typical job took recently; drives the "time remaining" estimate.
  const averageSeconds = useRef(null);
  const typicalSeconds = useMemo(() => averageWorkerSeconds([...results, ...libraryItems].filter(Boolean)), [results, libraryItems]);
  averageSeconds.current = typicalSeconds;

  async function applySettings(settings) {
    if (settings?.generation_type === "atelier") {
      const id = settings.model_id;
      if (id && isMixId(id) && mixEntry(id, serverModels)) setMixIds(current => (current.includes(id) ? current : [...current, id]));
      const seed = settings.seed !== undefined && id ? String(await atelierBaseSeed(settings.seed, id)) : "-1";
      setAtelier(current => ({...atelierFromSettings(settings, current), seed}));
      return;
    }
    if (settings?.generation_type === "vari") {
      setVari(current => variFromSettings(settings, current));
      return;
    }
    if (settings?.generation_type === "collage") {
      setCollage(current => collageFromSettings(settings, current));
      return;
    }
    if (settings?.generation_type === "reimagine") {
      setReimagine(current => reimagineFromSettings(settings, current));
      return;
    }
    const next = controlsFromSettings(settings);
    if (next.modelId && isMixId(next.modelId) && mixEntry(next.modelId, serverModels))
      setMixIds(current => (current.includes(next.modelId) ? current : [...current, next.modelId]));
    // An image made with a LoRA was generated in LoRA mode (base checkpoint + LoRA): repeat it the same way.
    const loraMode = Boolean(next.loraId && next.loraId !== "none" && loras.some((lora) => lora.id === next.loraId));
    if (!loraMode && next.modelId && (models.some((model) => model.id === next.modelId && model.kind !== "base") || mixEntry(next.modelId, serverModels))) {
      setSelectedModelIds([next.modelId]); setCheckpointSource(sourceOf(next.modelId));
    }
    if (loraMode) setLoraId(next.loraId);
    if (next.loraStrength !== undefined) setLoraStrength(next.loraStrength);
    if (next.denoise !== undefined) setDenoise(next.denoise);
    if (next.cfg !== undefined) setCfg(next.cfg);
    if (next.steps !== undefined) setSteps(next.steps);
    setGenerationMode(loraMode ? "lora" : "checkpoint");
    setEngine((current) => ({ ...current, ...next.engine }));
  }

  useJobs({
    activeJobs, setActiveJobs, submissionErrors, recordsCache, deletedIds, plannedCount, submitting,
    setBatchResults, setResults, setJob, setError, loadLibrary, averageSeconds, onBatchFinished: refreshUsage,
  });

  const generationSize = useMemo(() => {
    const longest = Math.max(imageSize.width, imageSize.height);
    const automatic = longest < 1000 ? 1016 / longest : 1;
    const ratio = Math.min(1, 1536 / (Math.max(imageSize.width, imageSize.height) * automatic * inputScale));
    return {width: Math.max(64, Math.floor(imageSize.width * automatic * inputScale * ratio / 8) * 8), height: Math.max(64, Math.floor(imageSize.height * automatic * inputScale * ratio / 8) * 8)};
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
      variants,
      useRealsrgan,
      useRealEsrgan,
      restormerMode,
      atelier,
      modelId,
      selectedModelIds: idsForSource(selectedModelIds, checkpointSource),
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
    // Presets saved before these settings existed lack the keys: leave the current choice alone then.
    if ("useRealsrgan" in preset) setUseRealsrgan(Boolean(preset.useRealsrgan));
    if ("useRealEsrgan" in preset) setUseRealEsrgan(Boolean(preset.useRealEsrgan));
    if ("restormerMode" in preset) setRestormerMode(["off", "motion", "defocus"].includes(preset.restormerMode) ? preset.restormerMode : "off");
    if (preset.variants && typeof preset.variants === "object") setVariants(current => ({...current, ...preset.variants}));
    setModelId(
      preset.modelId && preset.modelId !== "sdxl_base"
        ? preset.modelId
        : "tuymans_sdxl",
    );
    if (Array.isArray(preset.selectedModelIds)) {
      const known = id => models.some(model => model.id === id && model.kind !== "base") || Boolean(mixEntry(id, serverModels));
      const ids = [...new Set(preset.selectedModelIds)].filter(known);
      setMixIds(current => [...new Set([...current, ...ids.filter(isMixId)])]);
      if (ids.length) { setSelectedModelIds(ids); setCheckpointSource(sourceOf(ids[0])); }
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
    const items = files.map((file) => ({
      id: randomId(),
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
    const modelIds = generationMode === "lora" ? ["sdxl_base"] : [...new Set(idsForSource(selectedModelIds, checkpointSource))];
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
      use_realsrgan: useRealsrgan,
      output_upscaler: useRealEsrgan ? 'realesrgan' : useRealsrgan ? 'swinir' : 'lanczos',
      restormer_mode: restormerMode,
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
      safeStorage.remove("img2img-last-batch");
    }
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
      // Upload the input once; every model/chunk below references it by id.
      let sourceId;
      try {
        const upload = await apiFetch("/api/sources", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ image_base64: image }),
        });
        sourceId = (await readJson(upload, "Nahrání se nezdařilo.")).source_id;
      } catch (error) {
        issues.push(`${item.file.name}: ${error.message}`);
        continue;
      }
      // One random seed per input, shared across models for a fair comparison.
      const inputSeed = settings.seed === -1 ? crypto.getRandomValues(new Uint32Array(1))[0] : settings.seed;
      for (const selectedModelId of modelIds) {
        // Plain mode: chunks of up to 8 images with consecutive seeds. Variants: one job per sibling, each with
        // its own seed, settings, fusion weights and prompt (see planVariants).
        const requests = variants.enabled
          ? planVariants({
              count, distance: variants.distance, spread: variants.spread, prompt: variants.prompt, negativePrompt: variants.negative,
              seed: inputSeed, base: { denoise: settings.denoise, cfg: settings.cfg, loraStrength: settings.lora_strength, modelId: selectedModelId },
            }).map((sibling) => ({
              model_id: sibling.modelId, seed: sibling.seed, num_images: 1, denoise: sibling.denoise, cfg: sibling.cfg,
              lora_strength: sibling.loraStrength, prompt: sibling.prompt, negative_prompt: sibling.negativePrompt,
            }))
          : Array.from({ length: Math.ceil(count / 8) }, (_, chunk) => ({
              model_id: selectedModelId, seed: (inputSeed + chunk * 8) % 4294967296, num_images: Math.min(8, count - chunk * 8),
            }));
        for (const request of requests) {
          try {
            const response = await apiFetch("/api/generate-batch", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                inputs: [{ name: item.file.name, source_id: sourceId }],
                settings: { ...settings, ...request },
              }),
            });
            const data = await readJson(response, "Odeslání se nezdařilo.");
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
    const modelIds = [...new Set(idsForSource(atelier.modelIds, atelier.source || "single"))].filter(id => models.some(model => model.id === id && model.kind !== "base"));
    const count = Number(atelier.count), total = count * modelIds.length;
    if (!modelIds.length || !Number.isSafeInteger(count) || count < 1 || !Number.isSafeInteger(total)) {
      setError("Vyber checkpoint a kladný celý počet studií."); return;
    }
    const settings = {generation_type: "atelier", input_scale: atelier.inputScale ?? 1, atelier_mode: atelier.mode, atelier_theme: atelier.theme, atelier_framing: atelier.framing || "crop", atelier_archive: atelier.archive || "hofmann", atelier_photo_source: atelier.photoSource || "generated", atelier_photo_collection: atelier.photoCollection || "malba", atelier_photo_id: atelier.photoId || "", atelier_ratio: atelier.ratio || "fixed", atelier_color_level: atelier.colorLevel ?? 2, ...glitchSettings(atelier.glitch, atelier.glitchUntil),
      width: atelier.width, height: atelier.height, scale: Number(atelier.scale), use_realsrgan: Boolean(atelier.useRealsrgan), output_upscaler: atelier.useRealEsrgan ? 'realesrgan' : atelier.useRealsrgan ? 'swinir' : 'lanczos', restormer_mode: atelier.restormerMode || 'off', cfg: Number(atelier.cfg),
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
      safeStorage.remove("img2img-last-batch");
    }
    let sent = 0;
    const issues = [];
    const batchId = `${Date.now().toString(36)}-${seed.toString(36)}`;  // groups the siblings of this click in the gallery records
    for (let offset = 0; offset < count; offset += 8) {
      try {
        const response = await apiFetch("/api/atelier-batch", {method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({model_ids: modelIds, batch_id: batchId, count: Math.min(8, count - offset), settings: {...settings, seed: (seed + offset) % 4294967296}})});
        const data = await readJson(response, "Ateliér: odeslání se nezdařilo.");
        const jobs = data.jobs.map(job => ({...job, source_id: `atelier-${seed}-${job.model_id}-${offset + job.source_index}`, generation_type: "atelier"}));
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

  async function handleGenerateReimagine() {
    const count = Number(reimagine.count);
    const requestedSeed = Number(reimagine.seed === "" ? -1 : reimagine.seed);
    if (!inputItems.length || !Number.isSafeInteger(count) || count < 1) {setError("Přidej obrázek a zvol kladný počet variant."); return;}
    if (!Number.isInteger(requestedSeed) || requestedSeed < -1 || requestedSeed > 4294967295) {setError("Seed musí být celé číslo od −1 do 4294967295."); return;}
    const planFor = seed => planReimagine(reimagine, seed);
    const total = inputItems.length * plannedImages(planFor(0));
    const continuing = submitting.current || activeJobs.length > 0;
    pendingSubmissions.current += 1; submitting.current = true;
    plannedCount.current = (continuing ? Math.max(plannedCount.current, activeJobs.reduce((sum, item) => sum + item.expected_images, 0)) : 0) + total;
    setIsSubmitting(true); setPlannedOutputs(plannedCount.current);
    if (!continuing) {
      setSubmittedOutputs(0); setStartedAt(Date.now()); recordsCache.current.clear();
      setSubmissionErrors([]); setBatchResults([]); setJob({...EMPTY_JOB, status: "preparing", message: "unCLIP: odesílání do fronty"});
      safeStorage.remove("img2img-last-batch");
    }
    setError("");
    let sent = 0;
    const issues = [];
    for (const item of inputItems) {
      let sourceId;
      try {
        const upload = await apiFetch("/api/sources", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({image_base64: await fileToBase64(item.file)})});
        sourceId = (await readJson(upload, "Nahrání se nezdařilo.")).source_id;
      } catch (error) { issues.push(`${item.file.name}: ${error.message}`); continue; }
      const seed = requestedSeed === -1 ? crypto.getRandomValues(new Uint32Array(1))[0] : requestedSeed;
      for (const request of planFor(seed)) {
        try {
          const response = await apiFetch("/api/generate-batch", {method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({inputs: [{name: item.file.name, source_id: sourceId}], settings: request})});
          const data = await readJson(response, "Odeslání se nezdařilo.");
          const jobs = data.jobs.map(job => ({...job, source_id: item.id, source_name: item.file.name}));
          const accepted = jobs.reduce((sum, job) => sum + job.expected_images, 0); sent += accepted;
          setActiveJobs(current => [...current, ...jobs]); setSubmittedOutputs(current => current + accepted);
          issues.push(...(data.errors || []));
        } catch (error) { issues.push(`${item.file.name}: ${error.message}`); }
      }
    }
    pendingSubmissions.current -= 1; submitting.current = pendingSubmissions.current > 0;
    setIsSubmitting(submitting.current); setSubmissionErrors(current => [...current, ...issues]);
    if (issues.length) setError(issues.join(" · "));
    plannedCount.current -= total - sent; setPlannedOutputs(plannedCount.current);
    if (!sent && !continuing && !submitting.current) setJob({...EMPTY_JOB, status: "failed", message: "unCLIP: žádná úloha nebyla přijata."});
  }

  // Vari and Koláž: `buildCalls(issues)` uploads what it needs and returns the calls {name, sourceId, refId, settings}; one
  // /api/generate-batch request per call (one job per model run). `total` is the number of images the plan will make.
  async function submitCalls(label, total, buildCalls) {
    const continuing = submitting.current || activeJobs.length > 0;
    pendingSubmissions.current += 1; submitting.current = true;
    plannedCount.current = (continuing ? Math.max(plannedCount.current, activeJobs.reduce((sum, item) => sum + item.expected_images, 0)) : 0) + total;
    setIsSubmitting(true); setPlannedOutputs(plannedCount.current);
    if (!continuing) {
      setSubmittedOutputs(0); setStartedAt(Date.now()); recordsCache.current.clear();
      setSubmissionErrors([]); setBatchResults([]); setJob({...EMPTY_JOB, status: "preparing", message: `${label}: odesílání do fronty`});
      safeStorage.remove("img2img-last-batch");
    }
    setError("");
    let sent = 0;
    const issues = [];
    let calls = [];
    try { calls = await buildCalls(issues); } catch (error) { issues.push(error.message); }
    for (const call of calls) {
      try {
        const response = await apiFetch("/api/generate-batch", {method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({inputs: [{name: call.name, source_id: call.sourceId}], settings: call.settings})});
        const data = await readJson(response, "Odeslání se nezdařilo.");
        const jobs = data.jobs.map(job => ({...job, source_id: call.refId, source_name: call.name}));
        const accepted = jobs.reduce((sum, job) => sum + job.expected_images, 0); sent += accepted;
        setActiveJobs(current => [...current, ...jobs]); setSubmittedOutputs(current => current + accepted);
        issues.push(...(data.errors || []));
      } catch (error) { issues.push(`${call.name}: ${error.message}`); }
    }
    pendingSubmissions.current -= 1; submitting.current = pendingSubmissions.current > 0;
    setIsSubmitting(submitting.current); setSubmissionErrors(current => [...current, ...issues]);
    if (issues.length) setError(issues.join(" · "));
    plannedCount.current -= total - sent; setPlannedOutputs(plannedCount.current);
    if (!sent && !continuing && !submitting.current) setJob({...EMPTY_JOB, status: "failed", message: `${label}: žádná úloha nebyla přijata.`});
  }

  async function uploadSource(item) {
    const upload = await apiFetch("/api/sources", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({image_base64: await fileToBase64(item.file)})});
    return (await readJson(upload, "Nahrání se nezdařilo.")).source_id;
  }

  async function handleGenerateVari() {
    const plan = planVari(vari, nanoModels);
    if (!inputItems.length) {setError("Přidej obrázek, ze kterého se varianty odvodí."); return;}
    if (!plan.length) {setError("Vyber model, který má nastavený klíč."); return;}
    await submitCalls("Vari", inputItems.length * nanoPlannedImages(plan), async issues => {
      const calls = [];
      for (const item of inputItems) {
        let sourceId;
        try { sourceId = await uploadSource(item); } catch (error) { issues.push(`${item.file.name}: ${error.message}`); continue; }
        for (const settings of plan) calls.push({name: item.file.name, sourceId, refId: item.id, settings});
      }
      return calls;
    });
  }

  async function handleGenerateCollage() {
    if (!inputItems.length) {setError("Přidej aspoň jeden obrázek."); return;}
    if (inputItems.length > COLLAGE_MAX_SOURCES) {setError(`Nejvýš ${COLLAGE_MAX_SOURCES} vstupních obrázků.`); return;}
    if (!usableModels(collage.models, nanoModels.filter(forCollage)).length) {setError("Vyber model, který má nastavený klíč."); return;}
    const seedStart = crypto.getRandomValues(new Uint32Array(1))[0] % 1000;
    // The plan depends only on the number of inputs, so the image total is known before anything is uploaded.
    const preview = planCollage(collage, nanoModels, inputItems.map(item => item.id), seedStart);
    await submitCalls("Koláž", nanoPlannedImages(preview), async issues => {
      const ids = [];
      for (const item of inputItems) ids.push(await uploadSource(item));
      return planCollage(collage, nanoModels, ids, seedStart).map(({sourceIndex, settings}) =>
        ({name: inputItems[sourceIndex].file.name, sourceId: ids[sourceIndex], refId: inputItems[sourceIndex].id, settings}));
    });
  }

  async function handleCancel() {
    // The next poll tick sees "cancelled"; images that were already saved stay in the library.
    await Promise.allSettled(
      activeJobs.map((item) =>
        apiFetch(`/api/jobs/${item.job_id}/cancel`, { method: "POST" }),
      ),
    );
  }

  async function saveLibraryItem(itemId) {
    const data = await readJson(await apiFetch(`/api/library/${itemId}`, {method: "POST"}), "Uložení se nezdařilo.");
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
      await readJson(await apiFetch(`/api/library/${itemId}`, {method: "DELETE"}), "Smazání se nezdařilo.");
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
    const response = await apiFetch("/api/library/order", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    const data = await readJson(response, "Pořadí knihovny se nepodařilo uložit.");
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
    // A result still held in memory has no stored file yet: save it from its data instead.
    if (!item.url && item.image_base64) return downloadDataImage(item, 0);
    if (!item.url) return;
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
        handleCancel, atelier, setAtelier, handleGenerateAtelier, reimagine, setReimagine, handleGenerateReimagine, archives, archiveStatus, reloadArchives,
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
        resizeScale, useRealsrgan, setUseRealsrgan, useRealEsrgan, setUseRealEsrgan, restormerMode, setRestormerMode,
        setResizeScale,
        inputScale, setInputScale, generationSize,
        targetSize,
        imageSize,
        results,
        libraryItems,
        galleryLoading,
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
        gpuHourlyUsd, nanoModels, vari, setVari, handleGenerateVari, collage, setCollage, handleGenerateCollage, applySettings, addMix, removeMix, variants, setVariants, variantsPlan, checkpointSource, setCheckpointSource, usageText: usageLabel(usage),
        pendingMode: {atelier: "atelier", reimagine: "reimagine", vari: "vari", collage: "collage"}[activeJobs.at(-1)?.generation_type] || "results",
      }}
    />
  );
}

export default App;
