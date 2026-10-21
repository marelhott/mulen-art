import React, { useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronRight,
  Grid2X2,
  ImagePlus,
  Images,
  Layers3,
  Maximize2,
  Moon,
  PanelRightClose,
  PanelRightOpen,
  Columns2,
  Plus,
  Search,
  SlidersHorizontal,
  Sparkles,
  Sun,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { urlFor } from "./shared";
import { buildImageUrl } from "./api";
import { filterItems } from "./studioTools";
import { TEXT } from "./texts";
import { Compare } from "./components/Compare";
import { AtelierControls, AtelierQueue } from "./components/Atelier";
import { ImageCard } from "./components/ImageCard";
import { ImageViewer } from "./components/ImageViewer";
import { Progress } from "./components/Progress";
import { IconButton, Label, Range, Select } from "./components/controls";

export default function StudioView(p) {
  const [theme, setTheme] = useState(
    () => localStorage.getItem("img2img-theme") || "dark",
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
  const [tab, setTab] = useState("results");
  const isAtelier = tab === "atelier";
  const updateAtelier = patch => p.setAtelier(current => ({...current, ...patch}));
  const [thumbSize, setThumbSize] = useState(
    () => Number(localStorage.getItem("img2img-thumb-size")) || 0,
  );
  const [selection, setSelection] = useState(new Set());
  const [selecting, setSelecting] = useState(false);
  const [exporting, setExporting] = useState(false);
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
  useEffect(() => {
    if (!libraryOpen) return;
    const key = (event) => {
      if (event.key === "Escape") {
        setLibraryOpen(false);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [libraryOpen]);
  // Two separate feeds: canvas (img2img) and Atelier; the library holds both. Pending placeholders
  // (null) belong to the kind of job currently running.
  const isAtelierItem = (item) => item?.settings?.generation_type === "atelier";
  const atelierItems = p.results.filter((item) => (item ? isAtelierItem(item) : p.pendingMode === "atelier"));
  const canvasItems = p.results.filter((item) => (item ? !isAtelierItem(item) : p.pendingMode !== "atelier"));
  const unfiltered = tab === "library" ? p.libraryItems : isAtelier ? atelierItems : canvasItems;
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
    localStorage.setItem("img2img-theme", theme);
  }, [theme]);
  useEffect(() => {
    localStorage.setItem("img2img-thumb-size", String(thumbSize));
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
  useEffect(() => {
    if (!context) return;
    const dismiss = () => setContext(null);
    window.addEventListener("click", dismiss);
    window.addEventListener("blur", dismiss);
    return () => {
      window.removeEventListener("click", dismiss);
      window.removeEventListener("blur", dismiss);
    };
  }, [context]);

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
  const addFiles = (files) =>
    p.handleFileChange({ target: { files, value: "" } });
  async function reuse(item) {
    try {
      const response = await fetch(urlFor(item));
      if (!response.ok) throw new Error("Obrázek se nepodařilo načíst.");
      const blob = await response.blob();
      addFiles([
        new File([blob], item.filename || "vysledek.png", { type: blob.type }),
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
      addFiles([new File([blob], item.settings?.source_name || "vstup.png", { type: blob.type })]);
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
      }
      const blob = await zip.generateAsync({ type: "blob" });
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
    }
  }
  const download = (item) => p.downloadLibraryImage(item);
  const viewerPool =
    p.selectedImage?.context === "library"
      ? p.libraryItems
      : (isAtelier ? atelierItems : canvasItems).filter(Boolean);
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

  return (
    <div className={`studio ${rightOpen ? "" : "right-hidden"}`}>
      <nav className="icon-rail" aria-label="Navigace studia">
        <a href="#" className="brand-symbol" aria-label="Mulen IMG2IMG">
          <Sparkles size={23} />
        </a>
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
          MULEN <span>IMG2IMG</span>
          <small>SDXL STUDIO</small>
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
        </div>
      </header>
      <aside className="left-panel control-panel">
        {isAtelier ? <AtelierControls atelier={p.atelier} update={updateAtelier} models={p.models} archives={p.archives} archiveStatus={p.archiveStatus} reloadArchives={p.reloadArchives} generating={p.isGenerating} onGenerate={p.handleGenerateAtelier} /> : <>
        <button
          className="primary-button generate"
          disabled={!p.inputItems.length}
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
                ? `${p.inputItems.length} × ${p.numImages || "—"} × ${p.generationMode === "lora" ? 1 : p.selectedModelIds.length} modelů`
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
            onDragLeave={() => setDragging(false)}
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
          <div className="control-block">
            <Label>MODELY · VÝBĚR VÍCE</Label>
            <div className="checkpoint-options" role="group" aria-label="Checkpointy">
              {p.models.filter(item => item.kind !== "base").map(item => {
                const active = p.selectedModelIds.includes(item.id);
                return <button key={item.id} aria-pressed={active} onClick={() => p.setSelectedModelIds(current => active ? (current.length > 1 ? current.filter(id => id !== item.id) : current) : [...current, item.id])}>
                  <span>{item.name}</span>{active && <Check size={14} />}
                </button>;
              })}
            </div>
            <p className="help-text">Každý vstup × každý model. Stejný seed; více modelů = více výpočtů.</p>
          </div>
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
        <div className="control-block resolution">
          <Label>VSTUP PŘED GENEROVÁNÍM</Label>
          <Range label="ZVĚTŠENÍ VSTUPU" min={1} max={4} step={0.05} value={p.inputScale} onChange={p.setInputScale}
            hint="Lanczos před SDXL · vyšší rozměry mohou změnit styl a prodloužit výpočet. Max. strana 1536 px." />
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
            hint="Lanczos až po SDXL · bez AI dokreslování, nemění hotový obraz."
          />
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
              {tab === "library" ? "KNIHOVNA OBRÁZKŮ" : isAtelier ? "ATELIÉR · NOVÉ STUDIE" : "PLÁTNO · HISTORIE GENEROVÁNÍ"}
            </h1>
            <p>
              {tab === "library"
                ? `${items.length} uložených obrázků`
                : p.isGenerating
                  ? `Celá fronta: ${p.readyCount} / ${p.outputCount} hotovo`
                  : isAtelier ? `${atelierItems.length} studií · bez vlastní vstupní fotografie` : `${p.results.filter(Boolean).length} vygenerovaných obrázků · historie zůstává na plátně`}
            </p>
          </div>
          <button
            className="toolbar-button"
            disabled={!items.some(Boolean) || exporting}
            onClick={() => exportImages()}
          >
            <ArrowDownToLine size={14} />
            {exporting ? "BALÍM…" : "EXPORTOVAT VŠE"}
          </button>
        </div>
        {isAtelier && <AtelierQueue p={progressState} />}
        <div className="gallery-tools">
          <div className="segmented tabs">
            <button aria-pressed={isAtelier} onClick={() => setTab("atelier")}>Ateliér <span>{atelierItems.filter(Boolean).length}</span></button>
            <button
              aria-pressed={tab === "results"}
              onClick={() => setTab("results")}
            >
              Plátno <span>{canvasItems.filter(Boolean).length}</span>
            </button>
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
            {p.error}
          </div>
        )}
        <div className="canvas-actions">
          <button className={`toolbar-button ${selecting ? "active" : ""}`} aria-pressed={selecting}
            onClick={() => {setSelecting(!selecting); setSelection(new Set());}}>
            <Check size={13} /> {selecting ? "Ukončit výběr" : "Vybrat více"}
          </button>
          <span className="help-text">Kliknutím zvětšíš · ve výběru označíš rámečkem</span>
        </div>
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
        {tab !== "atelier" && unfiltered.filter(Boolean).length > 1 && (
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
                  modelName={p.models.find(model => model.id === (item?.model_id || item?.settings?.model_id))?.name}
                  index={index}
                  generating={p.isGenerating}
                  progress={p.progressValue}
                  selected={selection.has(item?.id)}
                  isLibrary={tab === "library"}
                  selectMode={selecting}
                  isSaved={p.libraryItems.some((saved) => saved.id === item?.id)}
                  onSave={tab !== "library" ? async () => {
                    try { await p.saveLibraryItem(item.id); } catch (error) { p.setError(error.message); }
                  } : undefined}
                  onOpen={() => item && open(item, index)}
                  onSelect={() => item && toggleSelection(item.id)}
                  onLibraryDrop={
                    tab === "library"
                      ? (sourceId) => item && moveLibraryItem(sourceId, item.id)
                      : undefined
                  }
                  onDownload={() => download(item)}
                  onReuse={() => reuse(item)}
                  onDelete={() => removeImage(item)}
                  canDelete={true}
                  onContext={(event) => {
                    event.preventDefault();
                    if (item)
                      setContext({
                        item,
                        x: Math.min(event.clientX, window.innerWidth - 210),
                        y: Math.min(event.clientY, window.innerHeight - 180),
                      });
                  }}
                />
              );
            })}
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
              {isAtelier ? <>Vyber způsob tvorby a checkpoint v levém panelu.<br />Vlastní fotografie ani psaní zadání nejsou potřeba.</> : <>Přidej vstupní obrázky, vyber checkpoint nebo LoRA<br />a nech své modely pracovat v cloudu.</>}
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
      <aside className="right-panel control-panel">
        <Progress
          progress={progressState.progressValue}
          job={progressState.job}
          generating={p.isGenerating}
          startedAt={p.startedAt}
          ready={progressState.readyCount}
          total={progressState.outputCount}
          submitting={p.isSubmitting}
          submitted={progressState.submittedOutputs}
          planned={progressState.plannedOutputs}
          onCancel={p.handleCancel}
        />
        <div className="settings-heading">
          <SlidersHorizontal size={13} />
          <Label>NASTAVENÍ GENEROVÁNÍ</Label>
        </div>
        <p className="engine-hint">{isAtelier ? "Ateliér tvoří nové obrazy. Zvětšení hotového výsledku je pouze Lanczos, bez AI dokreslování. Stejné seedy umožňují porovnat checkpointy." : "Původní generování v jednom průchodu. Hotový obraz se zvětšuje pouze interpolací Lanczos, bez AI dokreslování a přidávání detailů."}</p>
        {(!isAtelier || ["photo", "archive"].includes(p.atelier.mode)) && <Range
          label="DENOISE"
          min={0.05}
          max={isAtelier ? 0.99 : 1}
          step={0.01}
          value={isAtelier ? p.atelier.denoise : p.denoise}
          onChange={value => isAtelier ? updateAtelier({denoise: value}) : p.setDenoise(value)}
          hint="Méně zachová předlohu · více ji promění"
        />}
        <Range
          label="CFG"
          min={0.5}
          max={20}
          step={0.1}
          value={isAtelier ? p.atelier.cfg : p.cfg}
          onChange={value => isAtelier ? updateAtelier({cfg: value}) : p.setCfg(value)}
        />
        <Range
          label="KROKY"
          min={1}
          max={80}
          step={1}
          value={isAtelier ? p.atelier.steps : p.steps}
          onChange={value => isAtelier ? updateAtelier({steps: value}) : p.setSteps(value)}
        />
        <Select label="SAMPLER" value={isAtelier ? p.atelier.sampler : p.engine.sampler}
          onChange={(sampler) => isAtelier ? updateAtelier({sampler, schedule: ["euler_a","ddim"].includes(sampler) ? "normal" : p.atelier.schedule}) : p.setEngine((e)=>({...e, sampler, schedule: ["euler_a","ddim"].includes(sampler) ? "normal" : e.schedule}))}
          items={[{id:"dpmpp_2m",name:"DPM++ 2M"},{id:"dpmpp_2m_sde",name:"DPM++ 2M SDE"},{id:"euler_a",name:"Euler a"},{id:"ddim",name:"DDIM"}]} />
        {["dpmpp_2m", "dpmpp_2m_sde"].includes(isAtelier ? p.atelier.sampler : p.engine.sampler) && <Select label="ROZVRH ŠUMU" value={isAtelier ? p.atelier.schedule : p.engine.schedule}
          onChange={(schedule)=>isAtelier ? updateAtelier({schedule}) : p.setEngine((e)=>({...e,schedule}))}
          items={[{id:"karras",name:"Karras"},{id:"normal",name:"Normal"}]} />}
        <label className="control-block engine-field"><Label>SEED · −1 = NÁHODNÝ</Label>
          <input aria-label="Seed" type="number" min="-1" max="4294967295" step="1" value={isAtelier ? p.atelier.seed : p.engine.seed}
            onChange={(event)=>isAtelier ? updateAtelier({seed:event.target.value}) : p.setEngine((e)=>({...e,seed:event.target.value}))} />
        </label>
        <section className="control-block preset-block">
          <Label>ULOŽENÁ NASTAVENÍ</Label>
          <select
            aria-label="Uložená nastavení"
            value={p.selectedPresetId}
            onChange={p.handlePresetSelect}
          >
            <option value="">Vybrat nastavení</option>
            {p.presets.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
          <input
            aria-label="Název nastavení"
            value={p.presetName}
            onChange={(event) => p.setPresetName(event.target.value)}
            placeholder="Název nastavení"
          />
          <div className="preset-actions">
            <button className="toolbar-button" onClick={p.handleSavePreset}>
              ULOŽIT
            </button>
            <IconButton
              label="Odstranit nastavení"
              disabled={!p.selectedPresetId}
              onClick={p.handleDeletePreset}
            >
              <Trash2 />
            </IconButton>
          </div>
        </section>
        <details className="activity-log">
          <summary>
            PRŮBĚH ÚLOH <span>{p.visibleLogs.length}</span>
          </summary>
          {p.visibleLogs.length ? (
            p.visibleLogs.map((entry, index) => (
              <div key={index}>
                <time>
                  {new Date(entry.timestamp).toLocaleTimeString("cs-CZ")}
                </time>
                <span>{entry.message}</span>
              </div>
            ))
          ) : (
            <p>Žádná aktivní úloha</p>
          )}
        </details>

        <div className="cloud-note">
          <span className="online-dot" />
          <p>
            Výpočty běží na Modalu.
            <br />
            GPU se po nečinnosti vypíná.
            {p.usageText && (<><br /><span className="usage-text">{p.usageText}</span></>)}
          </p>
        </div>
      </aside>
      {libraryOpen && (
        <div className="modal-backdrop" onClick={() => setLibraryOpen(false)}>
          <section
            className="library-dialog"
            role="dialog"
            aria-modal="true"
            aria-label="Knihovna obrázků"
            onClick={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <h2>Knihovna</h2>
                <p>
                  {p.libraryItems.length} výsledků · přetáhni nebo přidej do
                  vstupů
                </p>
              </div>
              <IconButton
                label="Zavřít knihovnu"
                onClick={() => setLibraryOpen(false)}
              >
                <X />
              </IconButton>
            </header>
            <div className="library-dialog-grid">
              {p.libraryItems.map((item, index) => (
                <ImageCard
                  key={item.id}
                  item={item}
                  modelName={p.models.find(model => model.id === (item?.model_id || item?.settings?.model_id))?.name}
                  index={index}
                  onOpen={() => p.openLibraryImage(item)}
                  onDownload={() => download(item)}
                  onReuse={() => reuse(item)}
                  onDelete={() => removeImage(item)}
                  canDelete={true}
                />
              ))}
            </div>
          </section>
        </div>
      )}
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
        <div
          className="context-menu"
          role="menu"
          style={{ left: context.x, top: context.y }}
        >
          <button
            role="menuitem"
            onClick={() => {
              open(context.item, items.findIndex((item) => item?.id === context.item.id));
              setContext(null);
            }}
          >
            <Maximize2 />
            Zvětšit
          </button>
          <button
            role="menuitem"
            disabled={false}
            onClick={() => reuse(context.item)}
          >
            <ImagePlus />
            Použít jako vstup
          </button>
          <button role="menuitem" onClick={() => download(context.item)}>
            <ArrowDownToLine />
            Stáhnout
          </button>
          <button
            role="menuitem"
            disabled={false}
            onClick={() => {
              removeImage(context.item);
              setContext(null);
            }}
          >
            <Trash2 />
            Smazat obrázek
          </button>
        </div>
      )}
    </div>
  );
}
