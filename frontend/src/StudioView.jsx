import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronRight,
  Grid2X2,
  LogOut,
  Images,
  Layers3,
  Combine,
  Moon,
  PanelRightClose,
  PanelRightOpen,
  Columns2,
  Plus,
  Search,
  Shuffle,
  Sparkles,
  Sun,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { signOut } from "./api";
import { safeStorage, urlFor } from "./shared";
import { buildImageUrl } from "./api";
import { filterItems, idsForSource } from "./studioTools";
import { TEXT } from "./texts";
import { Compare } from "./components/Compare";
import { CheckpointPicker } from "./components/CheckpointPicker";
import { VariantsPanel } from "./components/VariantsPanel";
import { AtelierControls, AtelierQueue } from "./components/Atelier";
import { ReimagineControls } from "./components/Reimagine";
import { VariControls, CollageControls } from "./components/Nano";
import { ContextMenu } from "./components/ContextMenu";
import { LibraryDialog } from "./components/LibraryDialog";
import { SettingsPanel } from "./components/SettingsPanel";
import { ImageCard } from "./components/ImageCard";
import { ImageViewer } from "./components/ImageViewer";
import { IconButton, Label, Range, Select } from "./components/controls";

export default function StudioView(p) {
  const [theme, setTheme] = useState(
    () => safeStorage.get("img2img-theme") || "dark",
  );
  // On phones the settings panel overlays the canvas, so it starts closed there.
  const [rightOpen, setRightOpen] = useState(() => window.innerWidth >= 900);
  const [progressReset, setProgressReset] = useState(false);
  useEffect(() => {
    if (p.isGenerating || p.job.status !== "completed") {setProgressReset(false); return;}
    const timer = setTimeout(() => setProgressReset(true), 2500);
    return () => clearTimeout(timer);
  }, [p.isGenerating, p.job.status, p.job.id]);
  const progressState = progressReset ? {...p, job: {...p.job, status:"idle", progress:0, queue_counts:{}, active_steps:[]}, progressValue:0, readyCount:0, outputCount:0, plannedOutputs:0, submittedOutputs:0} : p;

  const [libraryOpen, setLibraryOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [filterModel, setFilterModel] = useState("");
  const [filterText, setFilterText] = useState("");
  const [tab, setTab] = useState("vari");
  const isAtelier = tab === "atelier";
  const isReimagine = tab === "reimagine";
  const isVari = tab === "vari";
  const isCollage = tab === "collage";
  const updateAtelier = patch => p.setAtelier(current => ({...current, ...patch}));
  const [thumbSize, setThumbSize] = useState(
    () => Number(safeStorage.get("img2img-thumb-size")) || 0,
  );
  const [selection, setSelection] = useState(new Set());
  const [selecting, setSelecting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState("");
  const [dragging, setDragging] = useState(false);
  const [context, setContext] = useState(null);
  const deletingIds = useRef(new Set());
  async function removeImage(item) {
    if (deletingIds.current.has(item.id)) return;
    deletingIds.current.add(item.id);
    setContext(null);
    try {
      await p.deleteLibraryItem(item.id);
      setSelection(
        (current) => new Set([...current].filter((id) => id !== item.id)),
      );
    } catch (error) {
      p.setError(error.message);
    } finally {
      deletingIds.current.delete(item.id);
    }
  }
  async function removeSelectedImages() {
    const targets = (tab === "library" ? p.libraryItems : p.results.filter(Boolean)).filter((item) => selection.has(item.id));
    setSelection(new Set());
    const outcomes = await Promise.allSettled(targets.map((item) => p.deleteLibraryItem(item.id)));
    const errors = outcomes.flatMap((result, index) => result.status === "rejected" ? [`${targets[index].filename}: ${result.reason.message}`] : []);
    if (errors.length) p.setError(errors.join(" · "));
  }

  async function moveLibraryItem(sourceId, targetId) {
    if (sourceId === targetId) return;
    const ordered = [...p.libraryItems];
    const from = ordered.findIndex((item) => item.id === sourceId);
    const to = ordered.findIndex((item) => item.id === targetId);
    if (from < 0 || to < 0) return;
    ordered.splice(to, 0, ordered.splice(from, 1)[0]);
    try {
      await p.reorderLibraryItems(ordered.map((item) => item.id));
    } catch (error) {
      p.setError(error.message);
    }
  }
  const [visible, setVisible] = useState(80);
  const inputRef = useRef(null),
    moreRef = useRef(null);
  const closeLibrary = useCallback(() => setLibraryOpen(false), []);
  // Two separate feeds: canvas (img2img) and Atelier; the library holds both. Pending placeholders
  // (null) belong to the kind of job currently running.
  const isAtelierItem = (item) => item?.settings?.generation_type === "atelier";
  const isUnclipItem = (item) => item?.settings?.generation_type === "reimagine";
  const atelierItems = p.results.filter((item) => (item ? isAtelierItem(item) : p.pendingMode === "atelier"));
  const unclipItems = p.results.filter((item) => (item ? isUnclipItem(item) : p.pendingMode === "reimagine"));
  const isVariItem = (item) => item?.settings?.generation_type === "vari";
  const isCollageItem = (item) => item?.settings?.generation_type === "collage";
  const variItems = p.results.filter((item) => (item ? isVariItem(item) : p.pendingMode === "vari"));
  const collageItems = p.results.filter((item) => (item ? isCollageItem(item) : p.pendingMode === "collage"));
  const canvasItems = p.results.filter((item) => (item ? !isAtelierItem(item) && !isUnclipItem(item) && !isVariItem(item) && !isCollageItem(item) : p.pendingMode === "results"));
  const unfiltered = tab === "library" ? p.libraryItems : isAtelier ? atelierItems : isReimagine ? unclipItems : isVari ? variItems : isCollage ? collageItems : canvasItems;
  const items = filterItems(unfiltered, { modelId: filterModel, text: filterText });
  const filtering = Boolean(filterModel || filterText.trim());
  const modelNameFor = (item) => p.models.find((model) => model.id === (item?.model_id || item?.settings?.model_id))?.name;
  const count = items.length;
  const workspaceRef = useRef(null);
  const [workspaceWidth, setWorkspaceWidth] = useState(600);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) =>
      setWorkspaceWidth(entry.contentRect.width),
    );
    observer.observe(workspaceRef.current);
    return () => observer.disconnect();
  }, []);
  const columns =
    count <= 1
      ? 1
      : count <= 4
        ? 2
        : count <= 9
          ? 3
          : count <= 16
            ? 4
            : count <= 25
              ? 5
              : 6;
  const automatic = Math.max(
    100,
    Math.min(440, Math.floor((workspaceWidth - 20 * (columns - 1)) / columns)),
  );
  const size = thumbSize || automatic;

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    safeStorage.set("img2img-theme", theme);
  }, [theme]);
  useEffect(() => {
    safeStorage.set("img2img-thumb-size", String(thumbSize));
  }, [thumbSize]);
  useEffect(() => {
    setVisible(80);
    setSelection(new Set());
    setSelecting(false);
  }, [tab]);
  useEffect(() => {
    if (!moreRef.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setVisible((n) => n + 80);
      },
      { rootMargin: "400px" },
    );
    observer.observe(moreRef.current);
    return () => observer.disconnect();
  }, [visible, count]);

  const open = (item, index) =>
    tab === "library"
      ? p.openLibraryImage(item)
      : p.openResultImage(item, index);
  const toggleSelection = (id) =>
    setSelection((current) => {
      const next = new Set(current);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  // A proxy or odd server may label an image "application/octet-stream"; the upload check needs a real type.
  const imageType = (blob) => (/^image\/(png|jpeg|webp)$/.test(blob.type) ? blob.type : "image/png");
  const addFiles = (files) =>
    p.handleFileChange({ target: { files, value: "" } });
  async function reuse(item) {
    try {
      const response = await fetch(urlFor(item));
      if (!response.ok) throw new Error("Obrázek se nepodařilo načíst.");
      const blob = await response.blob();
      addFiles([
        new File([blob], item.filename || "vysledek.png", { type: imageType(blob) }),
      ]);
      p.setSelectedImage(null);
      setLibraryOpen(false);
      if (isAtelier) setTab("results");
    } catch (error) {
      p.setError(error.message);
    }
  }
  // Take over the stored settings and bring back the original source image as input.
  async function repeat(item) {
    p.applySettings(item.settings || {});
    const source = item.settings?.source_url || item.source_url;
    if (!source) return reuse(item);
    try {
      const response = await fetch(buildImageUrl(source));
      if (!response.ok) throw new Error("source unavailable");
      const blob = await response.blob();
      addFiles([new File([blob], item.settings?.source_name || "vstup.png", { type: imageType(blob) })]);
      p.setSelectedImage(null);
      setLibraryOpen(false);
      if (isAtelier) setTab("results");
      p.setError("");
    } catch {
      await reuse(item);
    }
  }
  async function drop(event) {
    event.preventDefault();
    setDragging(false);
    const own = event.dataTransfer.getData("application/x-img2img");
    if (own) {
      try {
        await reuse(JSON.parse(own));
      } catch {
        p.setError("Obrázek nelze přidat.");
      }
    } else addFiles(Array.from(event.dataTransfer.files));
  }
  async function exportImages(selectedOnly = false) {
    setExporting(true);
    try {
      const { default: JSZip } = await import("jszip");
      const zip = new JSZip();
      const chosen = items.filter(
        (item) => item && (!selectedOnly || selection.has(item.id)),
      );
      // Postupně: export velké galerie nezahltí síť souběžnými přenosy.
      for (let index = 0; index < chosen.length; index++) {
        const item = chosen[index],
          response = await fetch(urlFor(item));
        if (!response.ok) throw new Error("Stažení obrázku se nezdařilo.");
        zip.file(
          `${String(index + 1).padStart(3, "0")}-${item.filename || "obrazek.png"}`,
          await response.blob(),
        );
        setExportProgress(`${index + 1} / ${chosen.length}`);
      }
      const blob = await zip.generateAsync({ type: "blob" }, (meta) => setExportProgress(`balím ${Math.round(meta.percent)} %`));
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `mulen-img2img-${Date.now()}.zip`;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (error) {
      p.setError(error.message);
    } finally {
      setExporting(false);
      setExportProgress("");
    }
  }
  const download = (item) => p.downloadLibraryImage(item);
  // Cards get one stable `actions` object that always calls the latest handlers, so React.memo on the
  // card can skip re-rendering the whole grid on every unrelated state change (progress ticks, typing).
  const latest = useRef(null);
  latest.current = { open, toggleSelection, moveLibraryItem, reuse, removeImage, download, saveLibraryItem: p.saveLibraryItem, setError: p.setError, openLibraryImage: p.openLibraryImage };
  const cardActions = useMemo(() => ({
    open: (item, index) => latest.current.open(item, index),
    select: (item) => latest.current.toggleSelection(item.id),
    download: (item) => latest.current.download(item),
    reuse: (item) => latest.current.reuse(item),
    remove: (item) => latest.current.removeImage(item),
    save: async (item) => {
      try { await latest.current.saveLibraryItem(item.id); } catch (error) { latest.current.setError(error.message); }
    },
    libraryDrop: (sourceId, item) => latest.current.moveLibraryItem(sourceId, item.id),
    context: (event, item) => {
      event.preventDefault();
      if (item) setContext({ item, x: Math.min(event.clientX, window.innerWidth - 210), y: Math.min(event.clientY, window.innerHeight - 180) });
    },
  }), []);
  const libraryActions = useMemo(() => ({
    open: (item) => latest.current.openLibraryImage(item),
    download: (item) => latest.current.download(item),
    reuse: (item) => latest.current.reuse(item),
    remove: (item) => latest.current.removeImage(item),
  }), []);
  const modelNames = useMemo(() => new Map(p.models.map((model) => [model.id, model.name])), [p.models]);
  const savedIds = useMemo(() => new Set(p.libraryItems.map((saved) => saved.id)), [p.libraryItems]);
  const viewerPool =
    p.selectedImage?.context === "library"
      ? p.libraryItems
      : (isAtelier ? atelierItems : isReimagine ? unclipItems : isVari ? variItems : isCollage ? collageItems : canvasItems).filter(Boolean);
  const viewerIndex = viewerPool.findIndex(
    (item) => item.id === p.selectedImage?.id,
  );
  const navigate = (delta) => {
    const item = viewerPool[viewerIndex + delta];
    if (item)
      p.selectedImage.context === "library"
        ? p.openLibraryImage(item)
        : p.openResultImage(item, viewerIndex + delta);
  };

  const inputBlock = (
    <div className="control-block input-block">
      <div className="label-row">
        <Label>VSTUPNÍ OBRÁZKY</Label>
        <span>{p.inputItems.length}</span>
      </div>
      <div
        className={`upload-zone ${dragging ? "drag-over" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false); }}
        onDrop={drop}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept="image/png,image/jpeg,image/webp"
          disabled={false}
          aria-label="Přidat vstupní obrázky"
          onChange={p.handleFileChange}
        />
        {p.inputItems.length ? (
          <div className="input-grid">
            {p.inputItems.map((item, index) => (
              <div className="input-thumb" key={item.id}>
                <button
                  className="input-preview"
                  title={`Zvětšit ${item.file.name}`}
                  onClick={() =>
                    p.setSelectedImage({
                      id: item.id,
                      src: item.url,
                      filename: item.file.name,
                      context: "input",
                    })
                  }
                >
                  <img src={item.url} alt={item.file.name} loading="lazy" />
                </button>
                <button
                  className="thumb-remove"
                  disabled={false}
                  aria-label={`Odebrat ${item.file.name}`}
                  onClick={() =>
                    p.setInputItems((current) =>
                      current.filter((other) => other.id !== item.id),
                    )
                  }
                >
                  <X size={11} />
                </button>
                <span>{index + 1}</span>
              </div>
            ))}
            <button
              className="add-input-tile"
              aria-label="Přidat další obrázky"
              disabled={false}
              onClick={() => inputRef.current.click()}
            >
              <Plus size={18} />
            </button>
          </div>
        ) : (
          <button
            className="upload-empty"
            disabled={false}
            onClick={() => inputRef.current.click()}
          >
            <Plus size={23} />
            <span>Přetáhni obrázky nebo vyber soubory</span>
          </button>
        )}
      </div>
      <p className="help-text">
        Každý obrázek samostatně. Další výběr přidává vstupy.
      </p>
      {p.inputItems.length > 0 && (
        <button
          className="text-button"
          disabled={false}
          onClick={() => p.setInputItems([])}
        >
          Vyprázdnit vstupy
        </button>
      )}
    </div>
  );

  return (
    <div className={`studio ${rightOpen ? "" : "right-hidden"}`}>
      <nav className="icon-rail" aria-label="Navigace studia">
        <a href="#" className="brand-symbol" aria-label="Mulen Art">
          <svg width="26" height="21" viewBox="200 110 1190 960" fill="currentColor" aria-hidden="true">
            <path d="M231 137 801 630 1356 137V1028H1261V350L800 771 329 352V1028H231Z" />
            <path d="M383 523 801 917 1204 536V655L798 1047 383 655Z" />
          </svg>
        </a>
        <button className={isVari ? "active" : ""} onClick={() => setTab("vari")} title="Vari — sourozenci jednoho obrázku přes OpenRouter a Venice">
          <Layers3 /><span>VARI</span>
        </button>
        <button className={isReimagine ? "active" : ""} onClick={() => setTab("reimagine")} title="unCLIP — varianty z jednoho obrázku (SD 2.1 unCLIP, dříve Clipdrop Reimagine)">
          <Shuffle /><span>UNCLIP</span>
        </button>
        <button className={isAtelier ? "active" : ""} onClick={() => setTab("atelier")} title="Ateliér — tvorba bez vstupní fotografie">
          <Sparkles /><span>ATELIÉR</span>
        </button>
        <button
          className={tab === "results" ? "active" : ""}
          onClick={() => setTab("results")}
          title="Plátno"
        >
          <Grid2X2 />
          <span>PLÁTNO</span>
        </button>
        <button className={isCollage ? "active" : ""} onClick={() => setTab("collage")} title="Koláž — splynutí jednoho až deseti obrázků do jednoho díla">
          <Combine /><span>KOLÁŽ</span>
        </button>
        <button
          className={tab === "library" ? "active" : ""}
          onClick={() => setTab("library")}
          title="Knihovna"
        >
          <Images />
          <span>KNIHOVNA</span>
        </button>
        <div className="rail-bottom">
          <span className="online-dot" />
          <span>MODAL</span>
        </div>
      </nav>
      <header className="app-header">
        <div className="brand-wordmark">
          MULEN <span>ART</span>
        </div>
        <div className="header-actions">
          <span className="cloud-status">
            <span className="online-dot" />
            Cloud GPU
          </span>
          <IconButton
            label={rightOpen ? "Skrýt pravý panel" : "Zobrazit pravý panel"}
            onClick={() => setRightOpen(!rightOpen)}
          >
            {rightOpen ? <PanelRightClose /> : <PanelRightOpen />}
          </IconButton>
          <button
            className="theme-toggle"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
            {theme === "dark" ? "LIGHT" : "DARK"}
          </button>
          <IconButton label="Odhlásit se" onClick={signOut}>
            <LogOut />
          </IconButton>
        </div>
      </header>
      <aside className="left-panel control-panel">
        {isAtelier ? <AtelierControls atelier={p.atelier} update={updateAtelier} models={p.models} archives={p.archives} archiveStatus={p.archiveStatus} reloadArchives={p.reloadArchives} generating={p.isGenerating} onGenerate={p.handleGenerateAtelier} onAddMix={p.addMix} onRemoveMix={p.removeMix} /> : isVari ? <VariControls value={p.vari} update={patch => p.setVari(current => ({...current, ...patch}))} models={p.nanoModels || []} inputCount={p.inputItems.length} generating={p.isGenerating} onGenerate={p.handleGenerateVari} inputBlock={inputBlock} /> : isCollage ? <CollageControls value={p.collage} update={patch => p.setCollage(current => ({...current, ...patch}))} models={p.nanoModels || []} inputCount={p.inputItems.length} generating={p.isGenerating} onGenerate={p.handleGenerateCollage} inputBlock={inputBlock} /> : isReimagine ? <ReimagineControls value={p.reimagine} update={patch => p.setReimagine(current => ({...current, ...patch}))} inputCount={p.inputItems.length} generating={p.isGenerating} onGenerate={p.handleGenerateReimagine} inputBlock={inputBlock} /> : <>
        <button
          className="primary-button generate"
          disabled={!p.inputItems.length || (p.generationMode === "checkpoint" && !idsForSource(p.selectedModelIds, p.checkpointSource).length)}
          onClick={() => {
            setTab("results");
            p.handleGenerate();
          }}
        >
          <Sparkles size={16} />
          {p.isGenerating ? "PŘIDAT DO FRONTY" : "GENEROVAT"}
        </button>
        <div className="control-block">
          <div className="label-row">
            <Label>VARIANTY NA VSTUP</Label>
            <span>
              {p.inputItems.length
                ? `${p.inputItems.length} × ${p.numImages || "—"} × ${p.generationMode === "lora" ? 1 : idsForSource(p.selectedModelIds, p.checkpointSource).length} modelů`
                : "na každý obrázek"}
            </span>
          </div>
          <div className="count-control">
            <button
              aria-label="Méně variant"
              disabled={p.numImages <= 1}
              onClick={() => p.setNumImages(Math.max(1, p.numImages - 1))}
            >
              −
            </button>
            <input
              aria-label="Počet variant na vstup"
              type="number"
              min="1"
              step="1"
              value={p.numImages}
              disabled={false}
              onChange={(event) =>
                p.setNumImages(
                  event.target.value === "" ? "" : Number(event.target.value),
                )
              }
            />
            <button
              aria-label="Více variant"
              disabled={false}
              onClick={() => p.setNumImages(Number(p.numImages || 0) + 1)}
            >
              +
            </button>
          </div>
          <div className="count-presets">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                disabled={false}
                aria-pressed={p.numImages === n}
                onClick={() => p.setNumImages(n)}
              >
                {n}
              </button>
            ))}
            <span>nebo vlastní počet</span>
          </div>
        </div>
        {inputBlock}
        <div className="control-block">
          <Label>REŽIM GENEROVÁNÍ</Label>
          <div className="segmented">
            <button
              aria-pressed={p.generationMode === "checkpoint"}
              onClick={() => p.setGenerationMode("checkpoint")}
            >
              CHECKPOINT
            </button>
            <button
              aria-pressed={p.generationMode === "lora"}
              onClick={() => p.setGenerationMode("lora")}
            >
              LoRA + BASE
            </button>
          </div>
        </div>
        {p.generationMode === "checkpoint" ? (
          <CheckpointPicker label="MODELY · VÝBĚR VÍCE" items={p.models.filter(item => item.kind !== "base")}
            selectedIds={p.selectedModelIds} onChange={p.setSelectedModelIds}
            source={p.checkpointSource} onSourceChange={p.setCheckpointSource}
            mixCandidates={p.models.filter(item => item.kind !== "base" && item.kind !== "mix")}
            onAddMix={(id) => p.addMix(id, "canvas")} onRemoveMix={p.removeMix}
            hint="Každý vstup × každý model. Stejný seed; více modelů = více výpočtů." />
        ) : (
          <>
            <div className="base-model">
              <Layers3 size={15} />
              <span>
                SDXL Base 1.0<small>Oficiální základní model</small>
              </span>
              <Check size={13} />
            </div>
            <Select
              label="NAUČENÁ LoRA"
              value={p.loraId}
              onChange={p.setLoraId}
              items={p.loras.filter((item) => item.id !== "none")}
            />
            <Range
              label="SÍLA LoRA"
              value={p.loraStrength}
              min={0}
              max={2}
              step={0.01}
              onChange={p.setLoraStrength}
            />
          </>
        )}
        <VariantsPanel value={p.variants} onChange={p.setVariants} plan={p.variantsPlan} models={p.models} />
        <div className="control-block resolution">
          <Label>VSTUP PŘED GENEROVÁNÍM</Label>
          <Range label="ZVĚTŠENÍ VSTUPU" min={1} max={4} step={0.05} value={p.inputScale} onChange={p.setInputScale}
            hint={`Vstupy pod 1000 px automaticky zvětším nad 1000 px; další zvětšení ${p.inputScale.toFixed(2)}×. Maximum 1536 px.`} />
          <p className="help-text">{p.inputItems.length > 1 ? "Každý vstup se zvětší samostatně." : `${p.imageSize.width} × ${p.imageSize.height} → ${p.generationSize.width} × ${p.generationSize.height} px pro model`}</p>
        </div>
        <div className="control-block resolution">
          <Label>VÝSLEDEK PO GENEROVÁNÍ</Label>
          <div className="resolution-values">
            <span>
              PRO MODEL
              <strong>
                {p.inputItems.length > 1
                  ? "Každý samostatně"
                  : `${p.generationSize.width} × ${p.generationSize.height}`}
              </strong>
            </span>
            <ArrowRight size={15} />
            <span>
              VÝSTUP
              <strong>
                {p.inputItems.length > 1
                  ? `Zvětšení ${p.resizeScale.toFixed(2)}×`
                  : `${p.targetSize.width} × ${p.targetSize.height}`}
              </strong>
            </span>
          </div>
          <Range
            label="ZVĚTŠENÍ VÝSLEDKU"
            min={0.5}
            max={4}
            step={0.05}
            value={p.resizeScale}
            onChange={p.setResizeScale}
            hint={(p.useRealsrgan || p.useRealEsrgan) ? "AI zvětšení použije zvolený cílový rozměr." : "Lanczos s jemným doostřením po SDXL; bez AI dokreslování."}
          />
          <label className="variants-toggle realsr-toggle">
            <input type="checkbox" checked={p.useRealsrgan} onChange={event => {p.setUseRealsrgan(event.target.checked); if (event.target.checked) p.setUseRealEsrgan(false);}} />
            <span><b>Real-SR GAN · SwinIR</b><small>Volitelné AI zvětšení a obnova detailu. Přidává čas výpočtu na GPU.</small></span>
          </label>
          <label className="variants-toggle realsr-toggle">
            <input type="checkbox" checked={p.useRealEsrgan} onChange={event => {p.setUseRealEsrgan(event.target.checked); if (event.target.checked) p.setUseRealsrgan(false);}} />
            <span><b>Real-ESRGAN x4plus</b><small>AI zvětšení a obnova textury. Lze kombinovat s Restormerem.</small></span>
          </label>
          <Select label="RESTORMER · ODSTRANĚNÍ ROZMAZÁNÍ" value={p.restormerMode} onChange={p.setRestormerMode}
            items={[{id:'off',name:'Vypnuto'},{id:'defocus',name:'Rozostření'},{id:'motion',name:'Pohybové rozmazání'}]} />
          <p className="help-text">Restormer se použije před zvětšením; obě volby prodlouží výpočet na GPU.</p>
        </div>
        <button className="library-launch" onClick={() => setLibraryOpen(true)}>
          <Images size={18} />
          <span>
            KNIHOVNA<small>Přetáhni výsledek do vstupů</small>
          </span>
          <ChevronRight size={15} />
        </button>
        </>}
      </aside>
      <main className="workspace" ref={workspaceRef}>
        <div className="workspace-toolbar">
          <div>
            <h1>
              <span className="heading-glow" />
              {tab === "library" ? "KNIHOVNA OBRÁZKŮ" : isAtelier ? "ATELIÉR · NOVÉ STUDIE" : isReimagine ? "UNCLIP · VARIANTY Z OBRÁZKU" : isVari ? "VARI · SOUROZENCI OBRAZU" : isCollage ? "KOLÁŽ · SPLYNUTÍ OBRAZŮ" : "PLÁTNO · HISTORIE GENEROVÁNÍ"}
            </h1>
            <p>
              {tab === "library"
                ? `${items.length} uložených obrázků`
                : p.isGenerating
                  ? `Celá fronta: ${p.readyCount} / ${p.outputCount} hotovo`
                  : isAtelier ? `${atelierItems.length} studií · bez vlastní vstupní fotografie` : isReimagine ? `${unclipItems.filter(Boolean).length} variant · varianty a metamorfózy bez promptu` : isVari ? `${variItems.filter(Boolean).length} variant · modely z Mulen Nano` : isCollage ? `${collageItems.filter(Boolean).length} koláží · modely z Mulen Nano` : `${canvasItems.filter(Boolean).length} vygenerovaných obrázků · historie zůstává na plátně`}
            </p>
          </div>
          <button
            className="toolbar-button"
            disabled={!items.some(Boolean) || exporting}
            onClick={() => exportImages()}
          >
            <ArrowDownToLine size={12} />
            {exporting ? `BALÍM… ${exportProgress}` : "EXPORTOVAT VŠE"}
          </button>
        </div>
        {isAtelier && <AtelierQueue p={progressState} />}
        <div className="gallery-tools">
          <div className="segmented tabs">
            <button aria-pressed={isVari} onClick={() => setTab("vari")}>Vari <span>{variItems.filter(Boolean).length}</span></button>
            <button aria-pressed={isReimagine} onClick={() => setTab("reimagine")}>unCLIP <span>{unclipItems.filter(Boolean).length}</span></button>
            <button aria-pressed={isAtelier} onClick={() => setTab("atelier")}>Ateliér <span>{atelierItems.filter(Boolean).length}</span></button>
            <button
              aria-pressed={tab === "results"}
              onClick={() => setTab("results")}
            >
              Plátno <span>{canvasItems.filter(Boolean).length}</span>
            </button>
            <button aria-pressed={isCollage} onClick={() => setTab("collage")}>Koláž <span>{collageItems.filter(Boolean).length}</span></button>
            <button
              aria-pressed={tab === "library"}
              onClick={() => setTab("library")}
            >
              Knihovna <span>{p.libraryItems.length}</span>
            </button>
          </div>
          <div className="density-control">
            <Grid2X2 size={13} />
            <input
              type="range"
              aria-label="Velikost miniatur"
              min="100"
              max="440"
              step="10"
              value={size}
              onChange={(event) => setThumbSize(Number(event.target.value))}
            />
            <button
              className={thumbSize ? "" : "active"}
              onClick={() => setThumbSize(0)}
            >
              AUTO
            </button>
          </div>
        </div>
        {p.error && (
          <div className="error-banner" role="alert">
            <span>{p.error}</span>
            <button type="button" aria-label="Zavřít hlášení" onClick={() => p.setError("")}><X size={13} /></button>
          </div>
        )}
        {!isReimagine && (
          <div className="canvas-actions">
            <button className={`toolbar-button ${selecting ? "active" : ""}`} aria-pressed={selecting}
              onClick={() => {setSelecting(!selecting); setSelection(new Set());}}>
              <Check size={13} /> {selecting ? "Ukončit výběr" : "Vybrat více"}
            </button>
            <span className="help-text">Kliknutím zvětšíš · ve výběru označíš rámečkem</span>
          </div>
        )}
        {selection.size > 0 && (
          <div className="selection-toolbar">
            <span>
              <Check size={14} />
              Vybráno {selection.size}
            </span>
            <button onClick={() => setSelection(new Set())}>
              Zrušit výběr
            </button>
            <button disabled={exporting} onClick={() => exportImages(true)}>
              Stáhnout výběr
            </button>
            {selection.size >= 2 && (
              <button onClick={() => setCompareOpen(true)}><Columns2 size={13} /> {TEXT.compare}</button>
            )}
            {tab !== "library" && <button onClick={async () => {
              try { for (const item of p.results.filter((item) => item && selection.has(item.id))) await p.saveLibraryItem(item.id); }
              catch (error) { p.setError(error.message); }
            }}><Plus size={13} /> Uložit výběr do knihovny</button>}
            {(
              <button
                className="selection-delete"
                onClick={removeSelectedImages}
              >
                <Trash2 size={13} /> Smazat výběr
              </button>
            )}
          </div>
        )}
        {tab !== "atelier" && !isReimagine && !isVari && !isCollage && unfiltered.filter(Boolean).length > 1 && (
          <div className="filter-bar" role="search">
            <select aria-label="Filtrovat podle modelu" value={filterModel} onChange={(event) => setFilterModel(event.target.value)}>
              <option value="">{TEXT.filterModelAll}</option>
              {p.models.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}
            </select>
            <label className="filter-search">
              <Search size={13} aria-hidden="true" />
              <input type="search" aria-label="Hledat ve výstupech" placeholder={TEXT.filterSearch}
                value={filterText} onChange={(event) => setFilterText(event.target.value)} />
            </label>
            {filtering && <span className="help-text">{count} / {unfiltered.filter(Boolean).length}</span>}
          </div>
        )}
        {filtering && !count && <p className="help-text filter-empty">{TEXT.filterEmpty}</p>}
        {count ? (
          <div className="results-grid" style={{ "--thumb-size": `${size}px` }}>
            {Array.from({ length: Math.min(visible, count) }, (_, index) => {
              const item = items[index];
              return (
                <ImageCard
                  key={item?.id || `pending-${index}`}
                  item={item}
                  modelName={modelNames.get(item?.model_id || item?.settings?.model_id)}
                  index={index}
                  generating={item ? false : p.isGenerating}
                  progress={item ? 0 : p.progressValue}
                  selected={selection.has(item?.id)}
                  isLibrary={tab === "library"}
                  selectMode={selecting}
                  isSaved={savedIds.has(item?.id)}
                  canSave={tab !== "library"}
                  reorderable={tab === "library"}
                  canDelete={true}
                  actions={cardActions}
                />
              );
            })}
          </div>
        ) : p.galleryLoading ? (
          <div className="results-grid skeleton-grid" aria-busy="true" aria-label="Načítám galerii">
            {Array.from({ length: 8 }, (_, index) => <div className="skeleton-card" key={index} />)}
          </div>
        ) : (
          <div className="empty-workspace">
            <div className="empty-orbit">
              <Images size={35} strokeWidth={1} />
            </div>
            <h2>
              Prostor pro <em>nové obrazy.</em>
            </h2>
            <p>
              {isAtelier ? <>Vyber způsob tvorby a checkpoint v levém panelu.<br />Vlastní fotografie ani psaní zadání nejsou potřeba.</> : isReimagine ? <>Přidej obrázek v levém panelu a nastav odchylku.<br />Vznikne z něj varianta nebo metamorfóza, bez psaní promptu.</> : isVari ? <>Přidej obrázek, vyber modely a vzdálenost.<br />Z každého modelu vznikne sourozenec předlohy.</> : isCollage ? <>Přidej jeden až deset obrázků a vyber modely.<br />Obrazy splynou do jednoho organického díla.</> : <>Přidej vstupní obrázky, vyber checkpoint nebo LoRA<br />a nech své modely pracovat v cloudu.</>}
            </p>
            <button
              className="toolbar-button"
              onClick={() => isAtelier ? p.handleGenerateAtelier() : inputRef.current?.click()}
            >
              <Upload size={14} />
              {isAtelier ? "VYTVOŘIT STUDIE" : "PŘIDAT OBRÁZKY"}
            </button>
          </div>
        )}
        {count > visible && (
          <div ref={moreRef} className="load-more">
            <button onClick={() => setVisible((n) => n + 80)}>
              Zobrazit další · {visible} / {count}
            </button>
          </div>
        )}
      </main>
      <SettingsPanel p={p} isAtelier={isAtelier} isReimagine={isReimagine || isVari || isCollage} updateAtelier={updateAtelier} progressState={progressState} />
      <LibraryDialog open={libraryOpen} onClose={closeLibrary} suspended={Boolean(p.selectedImage) || compareOpen}
        items={p.libraryItems} models={p.models} actions={libraryActions} />
      {compareOpen && (
        <Compare
          items={unfiltered.filter((item) => item && selection.has(item.id))}
          modelName={modelNameFor}
          onClose={() => setCompareOpen(false)}
        />
      )}
      {p.selectedImage && (
        <ImageViewer
          image={p.selectedImage}
          onClose={() => p.setSelectedImage(null)}
          onNavigate={navigate}
          hasPrev={viewerIndex > 0}
          hasNext={viewerIndex >= 0 && viewerIndex < viewerPool.length - 1}
          onReuse={() => reuse(p.selectedImage)}
          onRepeat={() => repeat(p.selectedImage)}
          onDownload={p.downloadSelectedImage}
          gpuHourlyUsd={p.gpuHourlyUsd}
        />
      )}
      {context && (
        <ContextMenu
          at={context}
          onClose={() => setContext(null)}
          onOpen={() => open(context.item, items.findIndex((item) => item?.id === context.item.id))}
          onReuse={() => reuse(context.item)}
          onDownload={() => download(context.item)}
          onDelete={() => removeImage(context.item)}
        />
      )}
    </div>
  );
}
