import React, { useEffect, useRef, useState } from "react";
import { buildImageUrl, formatDuration, imageUrl, sourceUrl, thumbUrl } from "./api";
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Columns2,
  Grid2X2,
  ImagePlus,
  Images,
  Layers3,
  Maximize2,
  Moon,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  SlidersHorizontal,
  Sparkles,
  Sun,
  Trash2,
  Upload,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";

const urlFor = imageUrl;
const sourceFor = sourceUrl;
const thumbFor = thumbUrl;
const duration = formatDuration;
const dateFor = (date) =>
  date
    ? new Date(date).toLocaleString("cs-CZ", {
        day: "numeric",
        month: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";

export default function StudioView(p) {
  const [theme, setTheme] = useState(
    () => localStorage.getItem("img2img-theme") || "dark",
  );
  const [rightOpen, setRightOpen] = useState(true);
  const [progressReset, setProgressReset] = useState(false);
  useEffect(() => {
    if (p.isGenerating || p.job.status !== "completed") {setProgressReset(false); return;}
    const timer = setTimeout(() => setProgressReset(true), 2500);
    return () => clearTimeout(timer);
  }, [p.isGenerating, p.job.status, p.job.id]);
  const progressState = progressReset ? {...p, job: {...p.job, status:"idle", progress:0, queue_counts:{}, active_steps:[]}, progressValue:0, readyCount:0, outputCount:0, plannedOutputs:0, submittedOutputs:0} : p;

  const [libraryOpen, setLibraryOpen] = useState(false);
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
  const atelierItems = p.results.filter(item => item?.settings?.generation_type === "atelier");
  const items = tab === "library" ? p.libraryItems : isAtelier ? atelierItems : p.results;
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
      : (isAtelier ? atelierItems : p.results.filter(Boolean));
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
        <button className={isAtelier ? "active" : ""} onClick={() => setTab("atelier")} title="Ateliér — tvorba bez vstupní fotografie">
          <Sparkles /><span>ATELIÉR</span>
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
            <button
              aria-pressed={tab === "results"}
              onClick={() => setTab("results")}
            >
              Plátno <span>{p.results.filter(Boolean).length}</span>
            </button>
            <button
              aria-pressed={tab === "library"}
              onClick={() => setTab("library")}
            >
              Knihovna <span>{p.libraryItems.length}</span>
            </button>
            <button aria-pressed={isAtelier} onClick={() => setTab("atelier")}>Ateliér <span>{atelierItems.length}</span></button>
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
      {p.selectedImage && (
        <ImageViewer
          image={p.selectedImage}
          onClose={() => p.setSelectedImage(null)}
          onNavigate={navigate}
          hasPrev={viewerIndex > 0}
          hasNext={viewerIndex >= 0 && viewerIndex < viewerPool.length - 1}
          onReuse={() => reuse(p.selectedImage)}
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

function Label({ children }) {
  return <span className="control-label">{children}</span>;
}
function IconButton({ label, children, ...props }) {
  return (
    <button
      type="button"
      className="icon-button"
      aria-label={label}
      title={label}
      {...props}
    >
      {children}
    </button>
  );
}
function Select({ label, value, onChange, items }) {
  return (
    <label className="control-block">
      <Label>{label}</Label>
      <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>
        {items.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
    </label>
  );
}
function Range({ label, value, min, max, step, onChange, hint }) {
  return (
    <label className="control-block range-field">
      <span className="label-row">
        <Label>{label}</Label>
        <output>
          {Number(value).toFixed(step < 0.1 ? 2 : step < 1 ? 1 : 0)}
        </output>
      </span>
      <input
        type="range"
        aria-label={label}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        style={{ "--range-fill": `${(100 * (value - min)) / (max - min)}%` }}
      />
      {hint && <span className="help-text">{hint}</span>}
    </label>
  );
}
function Progress({
  progress,
  job,
  generating,
  startedAt,
  ready,
  total,
  submitting,
  submitted,
  planned,
}) {
  const [elapsed, setElapsed] = useState(0);
  const effectiveStart =
    startedAt || (job.started_at ? Date.parse(job.started_at) : null);
  const finishedDuration =
    job.finished_at && job.started_at
      ? (Date.parse(job.finished_at) - Date.parse(job.started_at)) / 1000
      : null;
  const shownElapsed =
    job.status === "idle"
      ? 0
      : !generating && finishedDuration !== null
        ? finishedDuration
        : elapsed;
  useEffect(() => {
    if (!generating || !effectiveStart) return;
    const tick = () =>
      setElapsed(Math.max(0, (Date.now() - effectiveStart) / 1000));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [generating, effectiveStart]);
  return (
    <section className={`progress-card ${generating ? "is-active" : ""}`}>
      <div className="progress-heading">
        <div>
          <Label>
            {submitting
              ? "ODESÍLÁNÍ DÁVKY"
              : generating
                ? job.status === "idle"
                  ? "OBNOVUJI DÁVKU"
                  : "GENERUJI OBRÁZKY"
                : job.status === "completed"
                  ? "DOKONČENO"
                  : job.status === "failed"
                    ? "ÚLOHA PŘERUŠENA"
                    : "PŘIPRAVENO TVOŘIT"}
          </Label>
          <p>
            {generating || job.status !== "idle"
              ? `${ready} / ${total} obrázků hotovo`
              : "Cloudové studio · SDXL"}
          </p>
        </div>
        <strong>
          {progress}
          <small>%</small>
        </strong>
      </div>
      <div className="sampling-progress" aria-label="Průběh výpočtových kroků">
        <Label>VÝPOČTOVÉ KROKY</Label>
        {job.active_steps?.length ? job.active_steps.map((step, index) => {
          const percent = Math.round(step.current / step.total * 100);
          return <div className="sampling-job" key={step.id}>
            <div className="sampling-count"><span>{job.active_steps.length > 1 ? `GPU ${index + 1} · ` : ""}{step.current} / {step.total} kroků</span><strong>{percent}%</strong></div>
            <div className="sampling-track" role="progressbar" aria-label={`Výpočtové kroky úlohy ${index + 1}`} aria-valuenow={step.current} aria-valuemax={step.total} aria-valuemin={0}>
              <div style={{width: `${percent}%`}} />
            </div>
          </div>;
        }) : <p className="sampling-wait">{generating ? "Čekání na výpočet · načítání GPU" : job.status === "completed" ? "Výpočet dokončen" : "Kroky se zobrazí při generování"}</p>}
      </div>
      <Label>CELKOVÝ POSTUP FRONTY</Label>
      <div
        className="progress-track"
        role="progressbar"
        aria-label="Průběh generování"
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div style={{ width: `${progress}%` }} />
      </div>
      <div className="progress-foot">
        <span>
          <Clock3 size={11} />
          {duration(shownElapsed)}
        </span>
        <span>
          {submitting
            ? `Ve frontě ${submitted} / ${planned}`
            : generating
              ? "GPU / fronta"
              : job.status === "completed"
                ? "Vše uloženo"
                : "Připraveno"}
        </span>
      </div>
      {generating && (
        <p className="progress-status" role="status">
          {job.message}
        </p>
      )}
    </section>
  );
}
function AtelierQueue({p}) {
  const counts = p.job.queue_counts || {};
  const active = p.isGenerating;
  const waiting = active && !p.isSubmitting && !(counts.running > 0);
  const failed = p.job.status === "failed";
  const done = p.job.status === "completed";
  const total = Math.max(p.outputCount, p.plannedOutputs || 0);
  const accepted = Math.max(p.submittedOutputs || 0, (counts.queued || 0) + (counts.running || 0) + (counts.completed || 0) + (counts.failed || 0));
  const title = p.isSubmitting ? "Přijímám tvoje zadání" : waiting ? "Zadání přijato · čekáme na GPU" : active ? "Ateliér právě tvoří" : failed ? "Část úloh se nepodařila" : done ? "Studie jsou hotové" : "Připraveno tvořit";
  return <section className={`atelier-queue ${active ? "is-active" : ""} ${waiting || p.isSubmitting ? "is-waiting" : ""} ${failed ? "has-error" : ""}`} aria-label="Stav fronty Ateliéru">
    <div className="atelier-queue-heading">
      <div className="atelier-queue-symbol">{active ? <Sparkles size={23} /> : <Check size={23} />}</div>
      <div className="atelier-queue-title" role="status" aria-live="polite"><span>FRONTA ATELIÉRU</span><h2>{title}</h2><p>{p.isSubmitting ? `${accepted} z ${total} výstupů potvrzeno serverem. Můžeš přidávat další zadání.` : waiting ? "Požadavky jsou uložené ve frontě. Nezadávej je znovu; výpočet začne po přidělení GPU." : active ? "Hotové obrazy se průběžně objevují níže a ukládají do knihovny." : failed ? "Podrobnosti chyby najdeš v průběhu úloh. Hotové obrazy zůstávají uložené." : done ? "Všechny úspěšné výsledky jsou na plátně a v knihovně." : "Vyber způsob tvorby a klikni na Vytvořit studie. Přijetí zadání uvidíš zde."}</p></div>
      <div className="atelier-queue-number"><strong>{active || done || failed ? p.progressValue : 0}</strong><span>%</span></div>
    </div>
    <div className="atelier-queue-track" role="progressbar" aria-label={p.isSubmitting ? "Přijetí zadání" : waiting ? "Čekání na přidělení GPU" : "Celkový průběh Ateliéru"} aria-valuemin={0} aria-valuemax={100} aria-valuenow={waiting ? undefined : p.isSubmitting ? Math.round(accepted / Math.max(total, 1) * 100) : p.progressValue} aria-valuetext={waiting ? "Zadání přijato, čekání na GPU; výpočet ještě nezačal" : undefined}>
      <div className="atelier-queue-fill" style={{width: `${p.isSubmitting ? accepted / Math.max(total, 1) * 100 : p.progressValue}%`}} />
      {(waiting || p.isSubmitting) && <div className="atelier-queue-scan" />}
    </div>
    <div className="atelier-queue-stats">
      <span><i className="queue-dot" />Přijato <b>{accepted}</b></span>
      <span>Čeká <b>{counts.queued || 0}</b></span>
      <span>Počítá se <b>{counts.running || 0}</b></span>
      <span>Hotovo <b>{p.readyCount} / {total}</b></span>
      {counts.failed > 0 && <span className="queue-failed">Chyba <b>{counts.failed}</b></span>}
    </div>
    {p.job.active_steps?.length > 0 && <div className="atelier-queue-steps">{p.job.active_steps.map((step, i) => <div key={step.id}><span>Výpočet {i + 1} · {step.current} / {step.total} kroků</span><div className="atelier-step-track"><div style={{width: `${step.current / step.total * 100}%`}} /></div></div>)}</div>}
  </section>;
}
function AtelierControls({atelier: a, update, models, archives = [], archiveStatus, reloadArchives, generating, onGenerate}) {
  const choices = models.filter(model => model.id.startsWith("tuymans_") || ["tuy_small", "hofmann_sdxl"].includes(model.id));
  const modes = [
    {id: "noise", name: "Volná studie", description: "Nový obraz přímo z šumu. Bez námětu i bez promptu; obsah vybírá samotný checkpoint."},
    {id: "subject", name: "Automatický námět", description: "Aplikace vybere střídmý námět a vytvoří obraz checkpointem. Nic nepíšeš."},
    {id: "archive", name: "Archiv → fúze", description: "Náhodný obraz ze zdrojového archivu přemaluje libovolný zvolený checkpoint. Jeden obraz na výstup, bez tréninku."},
    {id: "photo", name: "Foto → malba", description: "SDXL Base vytvoří fotografický předobraz a vybraný checkpoint jej přemaluje. Dva průchody GPU; denoise až 0,99."},
  ];
  const total = Number(a.count || 0) * a.modelIds.length;
  return <>
    <button className="primary-button generate" disabled={!a.modelIds.length || !choices.length || (a.mode === "archive" && !archives.some(item => item.id === (a.archive || "hofmann")))} onClick={onGenerate}>
      <Sparkles size={16} />{generating ? "PŘIDAT STUDIE DO FRONTY" : "VYTVOŘIT STUDIE"}
    </button>
    <div className="control-block atelier-modes">
      <Label>ZPŮSOB TVORBY</Label>
      {modes.map(mode => <button key={mode.id} className="atelier-mode" aria-pressed={a.mode === mode.id} onClick={() => update({mode: mode.id})}>
        <span>{mode.name}</span><small>{mode.description}</small>
      </button>)}
    </div>
    <Range label="POČET STUDIÍ NA MODEL" min={1} max={10} step={1} value={a.count}
      onChange={count => update({count})}
      hint={`${a.count} studií × ${a.modelIds.length} modelů = ${total} výstupů`} />
    {a.mode === "archive" && <><Select label="ZDROJOVÝ ARCHIV · OBSAH" value={a.archive || "hofmann"} onChange={archive => update({archive})} items={archives.length ? archives.map(item => ({id:item.id,name:`${item.name} · ${item.count} obrazů`})) : [{id:a.archive || "hofmann",name: archiveStatus === "loading" ? "Načítám archivy…" : "Archiv se nepodařilo načíst"}]} />{archiveStatus === "error" && <button className="text-button" onClick={reloadArchives}>Znovu načíst archivy</button>}<p className="help-text">Archiv vybírá předlohu, checkpoint určuje přemalování. Stejná předloha i seed pro všechny modely. Zachovává se poměr stran; rozlišení níže je maximální rámeček.</p></>}
    {!["noise", "archive"].includes(a.mode) && <Select label="OKRUH NÁMĚTŮ" value={a.theme} onChange={theme => update({theme})}
      items={[{id:"all",name:"Všechny okruhy"},{id:"face",name:"Tváře a výřezy"},{id:"figure",name:"Postavy a gesta"},{id:"interior",name:"Interiéry"},{id:"object",name:"Předměty"},{id:"landscape",name:"Krajina a stavby"}]} />}
    <div className="control-block"><Label>CHECKPOINTY · MALÍŘSKÉ ZPRACOVÁNÍ</Label>
      <div className="checkpoint-options" role="group" aria-label="Modely Ateliéru">{choices.map(model => <button key={model.id} aria-pressed={a.modelIds.includes(model.id)} onClick={() => update({modelIds: a.modelIds.includes(model.id) ? (a.modelIds.length > 1 ? a.modelIds.filter(id => id !== model.id) : a.modelIds) : [...a.modelIds, model.id]})}>
        <span>{model.name}</span>{a.modelIds.includes(model.id) && <Check size={14} />}
      </button>)}</div>
      <button className="text-button" onClick={() => update({modelIds: ["tuymans_modal_800", "tuymans_modal_1600", "tuymans_modal_2400"].filter(id => choices.some(model => model.id === id))})}>Porovnat 800 / 1600 / 2400</button>
      <p className="help-text">Každý námět i seed se použije na všechny vybrané modely. Výsledky se ukládají také na plátno a do knihovny.</p>
    </div>
    <Select label="ROZLIŠENÍ PRO MODEL" value={a.ratio === "random" ? "random" : `${a.width}x${a.height}`} onChange={value => {if(value === "random") {update({ratio:"random"}); return;} const [width,height] = value.split("x").map(Number); update({width,height,ratio:"fixed"});}}
      items={[{id:"random",name:"Random · různé poměry stran"},{id:"1024x1024",name:"1024 × 1024 · čtverec"},{id:"832x1216",name:"832 × 1216 · na výšku"},{id:"1216x832",name:"1216 × 832 · na šířku"},{id:"1536x1536",name:"1536 × 1536 · experiment"}]} />
    <Range label="ZVĚTŠENÍ HOTOVÉHO OBRAZU" min={1} max={4} step={0.1} value={a.scale} onChange={scale => update({scale})}
      hint={a.ratio === "random" ? "Náhodné čtvercové, svislé i vodorovné formáty · bez AI zvětšování" : a.mode === "archive" ? `${a.scale}× Lanczos po přemalování · rozměry podle předlohy, bez AI dokreslení` : `${Math.round(a.width*a.scale)} × ${Math.round(a.height*a.scale)} px · pouze Lanczos, bez AI dokreslení`} />
    <p className="help-text">Archiv používá náhodně vybrané předlohy. Ostatní automatické náměty čerpají ze startovní sady.</p>
  </>;
}

function ImageCard({
  item,
  modelName,
  index,
  generating,
  progress,
  selected,
  isLibrary,
  selectMode,
  isSaved,
  onSave,
  onOpen,
  onSelect,
  onLibraryDrop,
  onDownload,
  onReuse,
  onDelete,
  canDelete,
  onContext,
}) {
  const libraryMode = isLibrary || Boolean(onLibraryDrop);
  const checkpointName = modelName || item?.settings?.model_name || item?.model_id || "";
  const modalStep = (item?.model_id || item?.settings?.model_id || "").match(/^tuymans_modal_(\d+)$/)?.[1];
  return (
    <article
      className={`image-card ${selected ? "selected" : ""} ${libraryMode ? "is-library-card" : ""}`}
      onContextMenu={onContext}
      draggable={Boolean(item)}
      onDragOver={(event) => {
        if (
          libraryMode &&
          event.dataTransfer.types.includes("application/x-library-order")
        )
          event.preventDefault();
      }}
      onDrop={(event) => {
        const sourceId = event.dataTransfer.getData(
          "application/x-library-order",
        );
        if (sourceId) {
          event.preventDefault();
          onLibraryDrop?.(sourceId);
        }
      }}
      onDragStart={(event) => {
        if (item) {
          if (libraryMode) {
            event.dataTransfer.setData("application/x-library-order", item.id);
            event.dataTransfer.effectAllowed = "move";
          } else {
            event.dataTransfer.setData(
              "application/x-img2img",
              JSON.stringify(item),
            );
            event.dataTransfer.effectAllowed = "copy";
          }
        }
      }}
    >
      <div
        className="card-image"
        role="button"
        tabIndex={item ? 0 : -1}
        aria-label={
          item
            ? `${selectMode ? "Vybrat" : "Zvětšit"} obrázek ${index + 1}`
            : `Výstup ${index + 1} čeká`
        }
        onClick={(event) => {
          if (onSelect && (selectMode || event.metaKey || event.ctrlKey || event.shiftKey)) onSelect();
          else onOpen?.();
        }}
        onKeyDown={(event) => {
          if (
            event.target === event.currentTarget &&
            ["Enter", " "].includes(event.key)
          ) {
            event.preventDefault();
            (selectMode && onSelect ? onSelect : onOpen)?.();
          }
        }}
      >
        {item ? (
          <img
            src={thumbFor(item)}
            alt={
              item.source_name ||
              item.settings?.source_name ||
              `Výsledek ${index + 1}`
            }
            loading="lazy"
            decoding="async"
          />
        ) : (
          <div className="pending-card">
            <div className="pending-line">
              <span style={{ width: `${progress}%` }} />
            </div>
            <span>{generating ? "GENERUJI…" : "NEDOKONČENO"}</span>
          </div>
        )}
        {item && <span className="card-number">{index + 1}</span>}
        {modalStep && <span className="card-model-badge" title={checkpointName}>Modal {modalStep}</span>}
      </div>
      {item && (
        <footer>
          <div className="card-caption">
            <span>{item.width} × {item.height}</span>
            <small className="card-model" title={checkpointName}>{modalStep ? `Modal ${modalStep}` : checkpointName}</small>
          </div>
          <div className="card-actions">
            <IconButton
              label={`Použít obrázek ${index + 1} jako vstup`}
              disabled={!canDelete}
              onClick={onReuse}
            >
              <ImagePlus />
            </IconButton>
            <IconButton
              label={`Stáhnout obrázek ${index + 1}`}
              onClick={onDownload}
            >
              <ArrowDownToLine />
            </IconButton>
            {onSave && <IconButton label={isSaved ? `Obrázek ${index + 1} je v knihovně` : `Uložit obrázek ${index + 1} do knihovny`}
              disabled={isSaved} onClick={onSave}>{isSaved ? <Check /> : <Plus />}</IconButton>}
            {onDelete && <IconButton
              label={`Odstranit obrázek ${index + 1}`}
              disabled={!canDelete}
              onClick={onDelete}
            >
              <Trash2 />
            </IconButton>}
          </div>
        </footer>
      )}
    </article>
  );
}

function ImageViewer({
  image,
  onClose,
  onNavigate,
  hasPrev,
  hasNext,
  onReuse,
  onDownload,
  gpuHourlyUsd,
}) {
  const [mode, setMode] = useState("details"),
    [split, setSplit] = useState(50),
    [zoom, setZoom] = useState(1),
    [pan, setPan] = useState({ x: 0, y: 0 });
  const stageRef = useRef(null),
    dialogRef = useRef(null),
    closeRef = useRef(null),
    drag = useRef(null);
  const clickStart = useRef(null), moved = useRef(false);
  const source = sourceFor(image),
    settings = image.settings || {},
    src = urlFor(image);
  useEffect(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setSplit(50);
    if (!sourceFor(image)) setMode("details");
  }, [image.id]);
  useEffect(() => {
    const previous = document.activeElement;
    closeRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
      previous?.focus?.();
    };
  }, []);
  useEffect(() => {
    const key = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
      if (["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName))
        return;
      if (event.key === "ArrowLeft" && hasPrev) onNavigate(-1);
      if (event.key === "ArrowRight" && hasNext) onNavigate(1);
      if (event.key === "Tab") {
        const nodes = [
          ...dialogRef.current.querySelectorAll(
            "button:not(:disabled),input,a[href]",
          ),
        ].filter((node) => node.getClientRects().length);
        if (event.shiftKey && document.activeElement === nodes[0]) {
          event.preventDefault();
          nodes.at(-1)?.focus();
        } else if (!event.shiftKey && document.activeElement === nodes.at(-1)) {
          event.preventDefault();
          nodes[0]?.focus();
        }
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [hasPrev, hasNext, onNavigate, onClose]);
  useEffect(() => {
    const stage = stageRef.current;
    const wheel = (event) => {
      event.preventDefault();
      if (mode === "compare") return;
      setZoom((current) =>
        Math.max(1, Math.min(5, current - event.deltaY * 0.003)),
      );
    };
    stage.addEventListener("wheel", wheel, { passive: false });
    return () => stage.removeEventListener("wheel", wheel);
  }, [mode]);
  const changeZoom = (value) => {
    setZoom(Math.max(1, Math.min(5, value)));
    if (value <= 1) setPan({ x: 0, y: 0 });
  };
  return (
    <div
      className="image-viewer"
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label={`Detail obrázku ${image.filename || ""}`}
    >
      <div
        className="viewer-stage"
        ref={stageRef}
        onClick={(event) => event.target === event.currentTarget && onClose()}
      >
        <div className="viewer-toolbar">
          <IconButton
            label="Zmenšit"
            disabled={zoom <= 1 || mode === "compare"}
            onClick={() => changeZoom(zoom - 0.5)}
          >
            <ZoomOut />
          </IconButton>
          <button onClick={() => changeZoom(1)}>
            {Math.round(zoom * 100)} %
          </button>
          <IconButton
            label="Zvětšit"
            disabled={zoom >= 5 || mode === "compare"}
            onClick={() => changeZoom(zoom + 0.5)}
          >
            <ZoomIn />
          </IconButton>
          <IconButton
            label="Přizpůsobit obrazovce"
            onClick={() => changeZoom(1)}
          >
            <Maximize2 />
          </IconButton>
        </div>
        {hasPrev && (
          <button
            className="viewer-nav previous"
            aria-label="Předchozí obrázek"
            onClick={() => onNavigate(-1)}
          >
            <ChevronLeft />
          </button>
        )}
        {hasNext && (
          <button
            className="viewer-nav next"
            aria-label="Další obrázek"
            onClick={() => onNavigate(1)}
          >
            <ChevronRight />
          </button>
        )}
        <div
          className={`viewer-picture ${mode === "compare" && source ? "compare-picture" : ""}`}
          style={{
            transform: `translate(${zoom > 1 ? pan.x : 0}px, ${zoom > 1 ? pan.y : 0}px) scale(${mode === "compare" ? 1 : zoom})`,
            cursor:
              mode === "compare" ? "default" : zoom > 1 ? "grab" : "zoom-out",
          }}
          onClick={() => { if (mode !== "compare" && !moved.current) onClose(); }}
          onPointerDown={(event) => {
            clickStart.current = {x: event.clientX, y: event.clientY};
            moved.current = false;
            if (zoom <= 1 || mode === "compare") return;
            drag.current = {
              x: event.clientX - pan.x,
              y: event.clientY - pan.y,
            };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            if (clickStart.current && Math.hypot(event.clientX - clickStart.current.x, event.clientY - clickStart.current.y) > 4) moved.current = true;
            if (drag.current)
              setPan({
                x: event.clientX - drag.current.x,
                y: event.clientY - drag.current.y,
              });
          }}
          onPointerUp={() => {
            clickStart.current = null;
            drag.current = null;
          }}
          onPointerCancel={() => {
            clickStart.current = null;
            moved.current = true;
            drag.current = null;
          }}
        >
          <img src={src} alt="Zvětšený výsledek" draggable={false} />
          {mode === "compare" && source && (
            <>
              <img
                className="comparison-source"
                src={sourceUrl(image)}
                alt="Původní vstup"
                style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}
                draggable={false}
              />
              <div className="comparison-line" style={{ left: `${split}%` }}>
                <span>
                  <ChevronLeft size={13} />
                  <ChevronRight size={13} />
                </span>
              </div>
              <div className="comparison-labels">
                <span>VSTUP</span>
                <span>VÝSLEDEK</span>
              </div>
              <input
                className="comparison-slider"
                type="range"
                aria-label="Porovnání vstupu a výsledku"
                min="0"
                max="100"
                value={split}
                onChange={(event) => setSplit(Number(event.target.value))}
              />
            </>
          )}
        </div>
        <p className="viewer-help">
          {mode === "compare"
            ? "Posuvníkem porovnej původní vstup a výsledek"
            : "Kliknutí: zavřít · kolečko: zoom · tažení: posun · ← → obrázky"}
        </p>
      </div>
      <aside className="viewer-details">
        <header>
          <div className="viewer-tabs">
            <button
              aria-pressed={mode === "details"}
              onClick={() => setMode("details")}
            >
              DETAILY
            </button>
            <button
              disabled={!source}
              aria-pressed={mode === "compare"}
              onClick={() => {
                setMode("compare");
                changeZoom(1);
              }}
            >
              POROVNAT
            </button>
          </div>
          <button
            ref={closeRef}
            className="icon-button"
            aria-label="Zavřít detail"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        <div className="viewer-details-content">
          <div className="detail-topline">
            <IconButton label="Stáhnout obrázek" onClick={onDownload}>
              <ArrowDownToLine />
            </IconButton>
            <time>{dateFor(image.created_at)}</time>
          </div>
          <h2>
            {image.source_name ||
              settings.source_name ||
              image.filename ||
              "Výsledek"}
          </h2>
          <div className="detail-tags">
            {[
              image.width && `${image.width} × ${image.height}`,
              settings.model_name || image.model_id || settings.model_id,
              image.lora_id && image.lora_id !== "none" ? image.lora_id : null,
            ]
              .filter(Boolean)
              .map((tag) => (
                <span key={tag}>{tag}</span>
              ))}
          </div>
          <div className="detail-section">
            <Label>PARAMETRY GENEROVÁNÍ</Label>
            {[
              ["Způsob tvorby", settings.generation_type === "atelier" ? ({noise: "Volná studie", subject: "Automatický námět", photo: "Foto → malba", archive: "Archiv → fúze"}[settings.atelier_mode]) : undefined],
              ["Námět", settings.subject_title],
              ["Zdrojový archiv", settings.archive_name],
              ["Denoise", settings.denoise],
              ["CFG", settings.cfg ?? settings.guidance_scale],
              ["Kroky", settings.steps],
              ["Skutečné kroky", settings.actual_steps],
              ["Režim", settings.render_mode],
              ["Vedení modelu", settings.conditioning_mode],
              ["Kroky dokreslení", settings.actual_detail_steps || undefined],
              ["Denoise dokreslení", settings.render_mode === "detail" ? settings.detail_strength : undefined],
              ["Rozvrh šumu", settings.schedule],
              ["Prompt", settings.prompt || undefined],
              ["Negativní prompt", settings.negative_prompt || undefined],
              ["Síla LoRA", settings.lora_strength],
              ["Sampler", settings.sampler],
              ["Seed", settings.seed],
              // Real server-measured GPU/wall seconds for this job, not an estimate.
              ["Čas na GPU", settings.worker_seconds ? duration(settings.worker_seconds) : undefined],
              ["Odhad ceny", settings.worker_seconds && gpuHourlyUsd ? `$${(settings.worker_seconds / 3600 * gpuHourlyUsd).toFixed(4)}` : undefined],
            ]
              .filter(([, value]) => value !== undefined && value !== null)
              .map(([key, value]) => (
                <div key={key} className="detail-value">
                  <span>{key}</span>
                  <strong>{String(value)}</strong>
                </div>
              ))}
          </div>
          {source && (
            <div className="detail-section">
              <Label>PŮVODNÍ VSTUP</Label>
              <button
                className="source-preview"
                onClick={() => setMode("compare")}
              >
                <img
                  src={sourceUrl(image)}
                  alt="Zdrojový obrázek"
                />
                <span>
                  <Columns2 size={14} />
                  Porovnat se vstupem
                </span>
              </button>
            </div>
          )}
        </div>
        <footer>
          <button
            className="primary-button"
            disabled={image.context === "input"}
            onClick={onReuse}
          >
            <ImagePlus size={16} />
            POUŽÍT JAKO VSTUP
          </button>
          <button className="toolbar-button" onClick={onDownload}>
            <ArrowDownToLine size={14} />
            STÁHNOUT ORIGINÁL
          </button>
        </footer>
      </aside>
    </div>
  );
}
