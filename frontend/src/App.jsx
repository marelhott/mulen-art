import React, { useEffect, useMemo, useRef, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL || "";
const POLL_INTERVAL = 1500;
const PRESET_STORAGE_KEY = "img2img-presets-v1";
const DEFAULT_SAMPLER = "dpmpp_2m";
const DEFAULT_SCHEDULE = "karras";
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
  if (path.startsWith("http://") || path.startsWith("https://") || path.startsWith("data:")) return path;
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
  const imageFile = inputItems[0]?.file;
  const previewUrl = inputItems[0]?.url || "";
  const [imageSize, setImageSize] = useState({ width: 1024, height: 1024 });
  const [resizeScale, setResizeScale] = useState(1);
  const [modelId, setModelId] = useState("tuymans_sdxl");
  const [generationMode, setGenerationMode] = useState("checkpoint");
  const [loraId, setLoraId] = useState("none");
  const [loraStrength, setLoraStrength] = useState(0.8);
  const [numImages, setNumImages] = useState(2);
  const [denoise, setDenoise] = useState(0.45);
  const [cfg, setCfg] = useState(5);
  const [steps, setSteps] = useState(25);
  const [results, setResults] = useState([]);
  const [libraryItems, setLibraryItems] = useState([]);
  const [libraryModalOpen, setLibraryModalOpen] = useState(false);
  const [selectedImage, setSelectedImage] = useState(null);
  const [presets, setPresets] = useState([]);
  const [presetName, setPresetName] = useState("");
  const [selectedPresetId, setSelectedPresetId] = useState("");
  const [error, setError] = useState("");
  const [submissionErrors, setSubmissionErrors] = useState([]);
  const [job, setJob] = useState(EMPTY_JOB);
  const [activeJobs, setActiveJobs] = useState(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem("img2img-active-jobs") || "[]");
      if (Array.isArray(saved) && saved.length) return saved;
      const legacy = window.localStorage.getItem("img2img-active-job");
      if (legacy) return [{ job_id: legacy, source_name: "Input image", expected_images: 1 }];
      const lastBatch = JSON.parse(window.localStorage.getItem("img2img-last-batch") || "[]");
      return Array.isArray(lastBatch) ? lastBatch : [];
    } catch { return []; }
  });

  useEffect(() => {
    setPresets(loadStoredPresets());
  }, []);

  useEffect(() => {
    if (!previewUrl) return;
    const probe = new window.Image();
    probe.onload = () => setImageSize({ width: probe.naturalWidth, height: probe.naturalHeight });
    probe.src = previewUrl;
    return () => { probe.onload = null; };
  }, [previewUrl]);

  useEffect(() => {
    fetch(`${API_URL}/api/options`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!data) return;
        if (data.models?.length) {
          setModels(data.models);
          setModelId(data.models.find((item) => item.kind !== "base")?.id || "tuymans_sdxl");
        }
        if (data.loras?.length) {
          setLoras(data.loras);
          setLoraId(data.loras.find((item) => item.id !== "none")?.id || "none");
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
    const known = new Map();
    const poll = async () => {
      const responses = await Promise.allSettled(activeJobs.map(async (item) => {
        const previous = known.get(item.job_id);
        if (previous && ["completed", "failed"].includes(previous.status)) return previous;
        const response = await fetch(`${API_URL}/api/jobs/${item.job_id}`);
        if (response.status === 401) { window.location.assign("/login"); throw new Error("Sign in required"); }
        if (response.status === 404) return { id: item.job_id, status: "failed", progress: 0, error: { detail: "Job expired. Saved images remain in the library." } };
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Connection interrupted");
        return data;
      }));
      if (cancelled) return;
      responses.forEach((response, index) => {
        if (response.status === "fulfilled") known.set(activeJobs[index].job_id, response.value);
      });
      const records = activeJobs.map((item) => known.get(item.job_id) || { status: "queued", progress: 0 });
      const slots = records.flatMap((record, index) => {
        const images = record.result?.images || record.partial_images || [];
        return Array.from({ length: activeJobs[index].expected_images || images.length || 1 }, (_, slot) => images[slot] ? { ...images[slot], source_name: activeJobs[index].source_name } : null);
      });
      const finished = records.filter((record) => ["completed", "failed"].includes(record.status)).length;
      const failed = records.filter((record) => record.status === "failed");
      const logs = records.flatMap((record) => record.logs || []).sort((a, b) => a.timestamp.localeCompare(b.timestamp)).slice(-10);
      const ready = slots.filter(Boolean);
      const latest = logs.at(-1)?.message || "Čekání na cloudové GPU";
      setResults(slots);
      setLibraryItems((current) => Array.from(new Map([...ready, ...current].map((item) => [item.id, item])).values()));
      const progress = records.reduce((sum, record) => sum + (record.status === "completed" ? 1 : record.progress || 0), 0) / records.length;
      setJob({ ...EMPTY_JOB, status: finished === records.length ? (failed.length ? "failed" : "completed") : "running",
        progress, logs, message: `${ready.length}/${slots.length} obrázků · ${finished}/${records.length} vstupů hotovo · ${latest}` });
      const issues = [...submissionErrors, ...failed.map((record) => record.error?.detail || "Generation failed")];
      if (responses.some((response) => response.status === "rejected")) issues.push("Spojení přerušeno, kontrolu opakuji.");
      setError(issues.join(" · "));
      if (finished === records.length) {
        window.localStorage.setItem("img2img-last-batch", JSON.stringify(activeJobs));
        setActiveJobs([]); loadLibrary().catch(() => {});
      }
      else timer = window.setTimeout(poll, POLL_INTERVAL);
    };
    poll();
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [activeJobs, submissionErrors]);

  useEffect(() => {
    if (activeJobs.length) window.localStorage.setItem("img2img-active-jobs", JSON.stringify(activeJobs));
    else window.localStorage.removeItem("img2img-active-jobs");
    window.localStorage.removeItem("img2img-active-job");
  }, [activeJobs]);

  const targetSize = useMemo(() => {
    const ratio = Math.min(1, 1536 / Math.max(imageSize.width, imageSize.height));
    const baseWidth = Math.max(64, Math.floor(imageSize.width * ratio / 8) * 8);
    const baseHeight = Math.max(64, Math.floor(imageSize.height * ratio / 8) * 8);
    const width = Math.round(baseWidth * resizeScale);
    const height = Math.round(baseHeight * resizeScale);
    return { width, height };
  }, [imageSize, resizeScale]);

  const isGenerating =
    Boolean(activeJobs.length) || job.status === "preparing" || job.status === "queued" || job.status === "waiting" || job.status === "running";
  const progressValue = job.status === "completed" ? 100 : Math.max(0, Math.min(isGenerating ? 99 : 100, Math.round((job.progress || 0) * 100)));
  const readyCount = results.filter(Boolean).length;
  const outputCount = results.length || Math.max(1, inputItems.length) * numImages;
  const sourceCount = inputItems.length || activeJobs.length || new Set(results.filter(Boolean).map((item) => item.source_name)).size || 1;
  const visibleLogs = job.logs?.slice(-10) || [];

  function buildPresetPayload() {
    return {
      generationMode,
      modelId,
      loraId,
      loraStrength,
      numImages,
      denoise,
      cfg,
      steps,
      resizeScale,
    };
  }

  function applyPreset(preset) {
    const mode = preset.generationMode || (preset.loraId && preset.loraId !== "none" ? "lora" : "checkpoint");
    setGenerationMode(mode);
    setModelId(preset.modelId && preset.modelId !== "sdxl_base" ? preset.modelId : "tuymans_sdxl");
    setLoraId(preset.loraId && preset.loraId !== "none" ? preset.loraId : (loras.find((item) => item.id !== "none")?.id || "none"));
    setLoraStrength(Number(preset.loraStrength ?? 0.8));
    setNumImages(Number(preset.numImages ?? 2));
    setDenoise(Number(preset.denoise ?? 0.45));
    setCfg(Number(preset.cfg ?? 5));
    setSteps(Number(preset.steps ?? 25));
    setResizeScale(Number(preset.resizeScale ?? 1));
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

    const existing = presets.find((item) => item.name.toLowerCase() === name.toLowerCase());
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
    if (!files.length || isGenerating) return;
    if (files.length > 10) { setError("Vyber nejvýše 10 vstupních obrázků."); return; }
    if (files.some((file) => !["image/png", "image/jpeg", "image/webp"].includes(file.type))) {
      setError("Podporovány jsou PNG, JPEG a WebP."); return;
    }
    if (files.reduce((sum, file) => sum + file.size, 0) > 45 * 1024 * 1024) {
      setError("Vstupy mohou mít dohromady nejvýše 45 MiB."); return;
    }
    inputItems.forEach((item) => URL.revokeObjectURL(item.url));
    restoreRecentAllowed.current = false;
    const items = files.map((file) => ({ id: crypto.randomUUID(), file, url: URL.createObjectURL(file) }));
    setInputItems(items);
    setResizeScale(1);
    setResults([]);
    setSelectedImage(null);
    setError("");
    setJob(EMPTY_JOB);
  }

  async function handleGenerate() {
    if (!inputItems.length || isGenerating) return;
    setError(""); setSubmissionErrors([]); setResults([]); setSelectedImage(null);
    setJob({ ...EMPTY_JOB, status: "preparing", message: `Příprava ${inputItems.length} samostatných vstupů` });
    try {
      const inputs = await Promise.all(inputItems.map(async (item) => ({ name: item.file.name, image_base64: await fileToBase64(item.file) })));
      const response = await fetch(`${API_URL}/api/generate-batch`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inputs, settings: {
          model_id: generationMode === "lora" ? "sdxl_base" : modelId,
          lora_id: generationMode === "lora" ? loraId : "none",
          denoise: Number(denoise), lora_strength: Number(loraStrength), cfg: Number(cfg), steps: Number(steps),
          sampler: DEFAULT_SAMPLER, schedule: DEFAULT_SCHEDULE,
          scale: Number(resizeScale.toFixed(2)), num_images: Number(numImages),
        } }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Generation failed.");
      setSubmissionErrors(data.errors || []);
      setActiveJobs(data.jobs);
      if (data.errors?.length) setError(data.errors.join(" · "));
    } catch (generationError) {
      setError(generationError.message);
      setJob({ ...EMPTY_JOB, status: "failed", message: generationError.message });
    }
  }

  async function loadLibrary(restoreRecent = false) {
    const response = await fetch(`${API_URL}/api/library`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Library load failed.");
    }
    setLibraryItems(data.items || []);
    if (restoreRecent && !activeJobs.length && restoreRecentAllowed.current) {
      setResults((current) => current.length ? current : (data.items || []).slice(0, 20).map((item) => ({
        ...item, source_name: item.settings?.source_name || item.filename,
      })));
    }
  }

  async function deleteLibraryItem(itemId) {
    const response = await fetch(`${API_URL}/api/library/${itemId}`, { method: "DELETE" });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Delete failed.");
    }
    setLibraryItems((current) => current.filter((item) => item.id !== itemId));
    if (selectedImage?.libraryId === itemId) {
      setSelectedImage(null);
    }
  }

  function openResultImage(image, index) {
    setSelectedImage({
      src: image.url ? buildImageUrl(image.url) : `data:image/${image.format || "png"};base64,${image.image_base64}`,
      width: image.width,
      height: image.height,
      downloadUrl: image.url ? buildImageUrl(image.url) : `data:image/${image.format || "png"};base64,${image.image_base64}`,
      filename: `img2img-output-${index + 1}.${image.format || "png"}`,
    });
  }

  function openLibraryImage(item) {
    setSelectedImage({
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
    anchor.href = image.url ? buildImageUrl(image.url) : `data:image/${image.format || "png"};base64,${image.image_base64}`;
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
    if (!selectedImage?.downloadUrl) return;
    const anchor = document.createElement("a");
    anchor.href = selectedImage.downloadUrl;
    anchor.download = selectedImage.filename || "img2img-output.png";
    anchor.click();
  }

  return (
    <main className="app-shell">
      <aside className="app-panel app-panel-left">
        <div className="panel-intro">
          <div className="section-mark" />
          <div className="intro-copy">
            <h1>IMG2IMG</h1>
            <p>MODAL · SDXL STUDIO</p>
          </div>
        </div>

        <div className="panel-divider" />

        <section className="control-group upload-group">
          <SectionTitle title={`VSTUPY · ${inputItems.length}/10`} />
          <label className="upload-frame">
            <input type="file" multiple disabled={isGenerating} aria-label="Vstupní obrázky (max. 10)" accept="image/png,image/jpeg,image/webp" onChange={handleFileChange} />
            {previewUrl ? <img src={previewUrl} alt="Input" /> : <span className="upload-plus">+</span>}
            <span className="frame-corner frame-corner-tl" />
            <span className="frame-corner frame-corner-tr" />
            <span className="frame-corner frame-corner-bl" />
            <span className="frame-corner frame-corner-br" />
            {previewUrl ? (
              <span className="input-dimensions">
                {inputItems.length > 1 ? `${inputItems.length} samostatných vstupů` : `${imageSize.width} × ${imageSize.height}`}
              </span>
            ) : null}
          </label>
          {inputItems.length > 0 && <div className="input-thumbnails">
            {inputItems.map((item) => <div key={item.id} className="input-thumbnail">
              <img src={item.url} alt={item.file.name} title={item.file.name} />
              <button type="button" disabled={isGenerating} aria-label={`Odebrat ${item.file.name}`}
                onClick={() => { URL.revokeObjectURL(item.url); setInputItems((current) => current.filter((other) => other.id !== item.id)); setResults([]); }}>×</button>
            </div>)}
          </div>}
          <span className="batch-hint">Každý vstup samostatně · max. 10 obrázků</span>
        </section>

        <FieldSelect label="REŽIM" value={generationMode} onChange={setGenerationMode} options={[
          { id: "checkpoint", name: "Checkpoint — vlastní model" },
          { id: "lora", name: "LoRA — SDXL Base 1.0" },
        ]} />
        {generationMode === "checkpoint" ? (
          <FieldSelect label="CHECKPOINT" value={modelId} onChange={setModelId} options={models.filter((item) => item.kind !== "base")} />
        ) : (
          <>
            <section className="control-group"><SectionTitle title="ZÁKLAD: SDXL BASE 1.0" /></section>
            <FieldSelect label="LORA" value={loraId} onChange={setLoraId} options={loras.filter((item) => item.id !== "none")} />

        <SliderField label="LORA STR" value={loraStrength.toFixed(2)}>
          <input
            type="range"
            min="0"
            max="2"
            step="0.01"
            value={loraStrength}
            onChange={(event) => setLoraStrength(Number(event.target.value))}
          />
        </SliderField>
          </>
        )}

        <SliderField label="VARIANTY / VSTUP" value={String(numImages)}>
          <input type="range" min="1" max="4" step="1" value={numImages} onChange={(event) => setNumImages(Number(event.target.value))} />
        </SliderField>

        <label className="control-group resolution-group">
          <SectionTitle title="RESOLUTION" />
          <div className="resolution-head">
            <div className="resolution-box">
              <span>SOURCE</span>
              <strong>
                {inputItems.length > 1 ? `${inputItems.length} samostatných vstupů` : `${imageSize.width} × ${imageSize.height}`}
              </strong>
            </div>
            <div className="resolution-box">
              <span>TARGET</span>
              <strong>
                {inputItems.length > 1 ? "Podle každého vstupu" : `${targetSize.width} × ${targetSize.height}`}
              </strong>
            </div>
          </div>
          <input
            type="range"
            min="0.5"
            max="4"
            step="0.05"
            value={resizeScale}
            onChange={(event) => setResizeScale(Number(event.target.value))}
          />
        </label>
      </aside>

      <section className="app-panel app-panel-center">
        <div className="workspace-header">
          <div className="workspace-meta">
            <SectionTitle title="OUTPUTS" />
            <span className="workspace-subline">
              {`${readyCount}/${outputCount} HOTOVO · ${sourceCount} VSTUPŮ`}
            </span>
          </div>
          <button className="generate-button" disabled={isGenerating || !imageFile} onClick={handleGenerate}>
            {isGenerating ? "GENERATING" : "GENERATE"}
          </button>
        </div>

        <div className="panel-divider" />

        {error ? <div className="error-line">{error}</div> : null}

        <div className="output-stage" style={{ "--preview-columns": outputCount <= 1 ? 1 : outputCount <= 4 ? 2 : outputCount <= 9 ? 3 : outputCount <= 16 ? 4 : outputCount <= 25 ? 5 : 6 }}>
          {Array.from({ length: outputCount }).map((_, index) => {
            const image = results[index];
            const imageSrc = image ? (image.url ? buildImageUrl(image.url) : `data:image/${image.format || "png"};base64,${image.image_base64}`) : "";
            return (
              <div
                key={index}
                role="button"
                tabIndex={image ? 0 : -1}
                className={`output-tile ${image ? "is-filled" : ""}`}
                onClick={() => image && openResultImage(image, index)}
                onKeyDown={(event) => { if (image && ["Enter", " "].includes(event.key) && event.target === event.currentTarget) { event.preventDefault(); openResultImage(image, index); } }}
                aria-disabled={!image}
              >
                <span className="frame-corner frame-corner-tl" />
                <span className="frame-corner frame-corner-tr" />
                <span className="frame-corner frame-corner-bl" />
                <span className="frame-corner frame-corner-br" />

                {image ? (
                  <>
                    <div className="output-image-shell">
                      <img src={imageSrc} alt={`Output ${index + 1}`} />
                    </div>
                    <button
                      type="button"
                      className="output-download"
                      onClick={(event) => {
                        event.stopPropagation();
                        downloadDataImage(image, index);
                      }}
                      aria-label={`Download output ${index + 1}`}
                    >
                      ↓
                    </button>
                    <span className="output-dimensions">
                      {image.width} × {image.height}{image.source_name ? ` · ${image.source_name}` : ""}
                    </span>
                  </>
                ) : (
                  <div className="tile-state">
                    <strong>{isGenerating ? `${progressValue}%` : `#${index + 1}`}</strong>
                    <span>{isGenerating ? "GENERATING..." : "PLACEHOLDER"}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <aside className="app-panel app-panel-right">
        <section className={`generation-progress ${isGenerating ? "is-active" : ""} ${job.status === "failed" ? "is-failed" : ""}`}>
          <div className="generation-progress-heading">
            <span>PRŮBĚH GENEROVÁNÍ</span>
            <strong>{progressValue}<small>%</small></strong>
          </div>
          <div className="generation-progress-track" role="progressbar" aria-label="Průběh generování"
            aria-valuemin={0} aria-valuemax={100} aria-valuenow={progressValue} aria-valuetext={`${progressValue} % · ${job.message}`}>
            <div className="generation-progress-fill" style={{ width: `${progressValue}%` }} />
          </div>
          <div className="generation-progress-message" role="status">
            {job.status === "idle" ? "Připraveno ke generování" : job.status === "completed" ? "Hotovo · obrázky jsou uložené" : job.message}
          </div>
        </section>
        <SliderField label="DENOISE" value={denoise.toFixed(2)}>
          <input type="range" min="0.05" max="1" step="0.01" value={denoise} onChange={(event) => setDenoise(Number(event.target.value))} />
        </SliderField>

        <SliderField label="CFG" value={cfg.toFixed(1)}>
          <input type="range" min="1" max="20" step="0.1" value={cfg} onChange={(event) => setCfg(Number(event.target.value))} />
        </SliderField>

        <SliderField label="STEPS" value={String(steps)}>
          <input type="range" min="1" max="80" step="1" value={steps} onChange={(event) => setSteps(Number(event.target.value))} />
        </SliderField>

        <FieldSelect label="RYCHLOST" value={steps === 15 ? "preview" : steps === 25 ? "standard" : "custom"}
          onChange={(value) => { if (value !== "custom") setSteps(value === "preview" ? 15 : 25); }}
          options={[
            { id: "preview", name: "Rychlý náhled · 15 kroků" },
            { id: "standard", name: "Standard · 25 kroků" },
            ...(steps !== 15 && steps !== 25 ? [{ id: "custom", name: `Vlastní · ${steps} kroků` }] : []),
          ]} />

        <section className="control-group preset-group">
          <SectionTitle title="PRESETS" />
          <select value={selectedPresetId} onChange={handlePresetSelect}>
            <option value="">Select preset</option>
            {presets.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
          <input
            className="preset-input"
            type="text"
            value={presetName}
            onChange={(event) => setPresetName(event.target.value)}
            placeholder="Preset name"
          />
          <div className="preset-actions">
            <button type="button" className="preset-button" onClick={handleSavePreset}>
              SAVE
            </button>
            <button type="button" className="preset-button preset-button-danger" onClick={handleDeletePreset} disabled={!selectedPresetId}>
              DELETE
            </button>
          </div>
        </section>

        <div className="panel-divider panel-divider-debug" />

        <section className="debug-strip">
          <div className="debug-strip-head">
            <span>PROGRESS</span>
            <strong>{progressValue}%</strong>
          </div>
          <div className="debug-strip-body">
            {visibleLogs.length ? (
              visibleLogs.map((entry, index) => (
                <div key={`${entry.timestamp}-${index}`} className="debug-strip-line">
                  <span>{formatTime(entry.timestamp)}</span>
                  <span>{Math.round((entry.progress || 0) * 100)}%</span>
                  <span>{entry.message}</span>
                </div>
              ))
            ) : (
              <div className="debug-strip-line">
                <span>--:--:--</span>
                <span>0%</span>
                <span>IDLE</span>
              </div>
            )}
          </div>
        </section>

        <section className="library-panel">
          <button type="button" className="library-toggle" onClick={() => setLibraryModalOpen(true)}>
            <span className="library-toggle-title">
              <span className="section-mark" />
              <span>LIBRARY</span>
            </span>
            <strong>{libraryItems.length}</strong>
          </button>
          <div className="library-grid">
            {libraryItems.length ? (
              libraryItems.map((item) => (
                <div key={item.id} className="library-card">
                  <button type="button" className="library-thumb" onClick={() => openLibraryImage(item)}>
                    <img src={buildImageUrl(item.url)} alt={item.filename} loading="lazy" />
                  </button>
                  <button
                    type="button"
                    className="library-download"
                    onClick={() => downloadLibraryImage(item)}
                    aria-label={`Download ${item.filename}`}
                  >
                    ↓
                  </button>
                </div>
              ))
            ) : (
              <div className="library-empty">NO IMAGES</div>
            )}
          </div>
        </section>
      </aside>

      {libraryModalOpen ? (
        <div className="library-modal" onClick={() => setLibraryModalOpen(false)}>
          <div className="library-modal-frame" onClick={(event) => event.stopPropagation()}>
            <div className="library-modal-head">
              <div className="library-modal-title">
                <span className="section-mark" />
                <strong>LIBRARY</strong>
              </div>
              <button type="button" className="library-modal-close" onClick={() => setLibraryModalOpen(false)}>
                CLOSE
              </button>
            </div>
            <div className="library-modal-grid">
              {libraryItems.length ? (
                libraryItems.map((item) => (
                  <div key={item.id} className="library-modal-card">
                    <button type="button" className="library-modal-thumb" onClick={() => openLibraryImage(item)}>
                      <img src={buildImageUrl(item.url)} alt={item.filename} loading="lazy" />
                    </button>
                    <div className="library-modal-actions">
                      <button type="button" className="library-modal-button" onClick={() => downloadLibraryImage(item)}>
                        ↓
                      </button>
                      <button
                        type="button"
                        className="library-modal-button library-modal-button-danger"
                        onClick={() => deleteLibraryItem(item.id).catch((deleteError) => setError(deleteError.message))}
                      >
                        ×
                      </button>
                    </div>
                  </div>
                ))
              ) : (
                <div className="library-empty">NO IMAGES</div>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {selectedImage ? (
        <div className="lightbox" onClick={() => setSelectedImage(null)}>
          <div className="lightbox-frame" onClick={(event) => event.stopPropagation()}>
            <button type="button" className="lightbox-download" onClick={downloadSelectedImage} aria-label="Download image">
              ↓
            </button>
            <button type="button" className="lightbox-close" onClick={() => setSelectedImage(null)}>
              CLOSE
            </button>
            <img src={selectedImage.src} alt="Selected output" />
          </div>
        </div>
      ) : null}
    </main>
  );
}

function SectionTitle({ title }) {
  return (
    <div className="section-title">
      <span className="section-mark" />
      <strong>{title}</strong>
    </div>
  );
}

function FieldSelect({ label, value, onChange, options }) {
  return (
    <label className="control-group">
      <SectionTitle title={label} />
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function SliderField({ label, value, children }) {
  return (
    <label className="control-group slider-group">
      <div className="slider-head">
        <SectionTitle title={label} />
        <strong>{value}</strong>
      </div>
      {children}
    </label>
  );
}

function formatTime(isoValue) {
  const value = new Date(isoValue);
  return value.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default App;
