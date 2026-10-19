import React, { useEffect, useRef, useState } from "react";
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

const urlFor = (item) =>
  item?.src ||
  (item?.url
    ? /^(https?:|data:|blob:)/.test(item.url)
      ? item.url
      : `${import.meta.env.VITE_API_URL || ""}${item.url}`
    : item?.image_base64
      ? `data:image/${item.format || "png"};base64,${item.image_base64}`
      : "");
const sourceFor = (item) => item?.source_url || item?.settings?.source_url;
const duration = (seconds) =>
  seconds < 60
    ? `${Math.floor(seconds)} s`
    : `${Math.floor(seconds / 60)} min ${Math.floor(seconds % 60)} s`;
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
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [tab, setTab] = useState("results");
  const [thumbSize, setThumbSize] = useState(
    () => Number(localStorage.getItem("img2img-thumb-size")) || 0,
  );
  const [selection, setSelection] = useState(new Set());
  const [exporting, setExporting] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [context, setContext] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [visible, setVisible] = useState(80);
  const inputRef = useRef(null),
    moreRef = useRef(null);
  useEffect(() => {
    if (!libraryOpen && !deleteTarget) return;
    const key = (event) => {
      if (event.key === "Escape") {
        setLibraryOpen(false);
        setDeleteTarget(null);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [libraryOpen, deleteTarget]);
  const items = tab === "library" ? p.libraryItems : p.results;
  const count = tab === "library" ? items.length : p.outputCount;
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
    } catch (error) {
      p.setError(error.message);
    }
  }
  async function drop(event) {
    event.preventDefault();
    setDragging(false);
    if (p.isGenerating) return;
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
      : p.results.filter(Boolean);
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
          title="Výsledky"
        >
          <Grid2X2 />
          <span>STUDIO</span>
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
        <button
          className="primary-button generate"
          disabled={p.isGenerating || !p.inputItems.length}
          onClick={() => {
            setTab("results");
            p.handleGenerate();
          }}
        >
          <Sparkles size={16} />
          {p.isSubmitting
            ? "ODESÍLÁM DO FRONTY"
            : p.isGenerating
              ? p.job.status === "idle"
                ? "OBNOVUJI DÁVKU"
                : "GENERUJI"
              : "GENEROVAT"}
        </button>
        <div className="control-block">
          <div className="label-row">
            <Label>VARIANTY NA VSTUP</Label>
            <span>
              {p.inputItems.length
                ? `${p.inputItems.length} × ${p.numImages || "—"}`
                : "na každý obrázek"}
            </span>
          </div>
          <div className="count-control">
            <button
              aria-label="Méně variant"
              disabled={p.isGenerating || p.numImages <= 1}
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
              disabled={p.isGenerating}
              onChange={(event) =>
                p.setNumImages(
                  event.target.value === "" ? "" : Number(event.target.value),
                )
              }
            />
            <button
              aria-label="Více variant"
              disabled={p.isGenerating}
              onClick={() => p.setNumImages(Number(p.numImages || 0) + 1)}
            >
              +
            </button>
          </div>
          <div className="count-presets">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                disabled={p.isGenerating}
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
              disabled={p.isGenerating}
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
                      disabled={p.isGenerating}
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
                  disabled={p.isGenerating}
                  onClick={() => inputRef.current.click()}
                >
                  <Plus size={18} />
                </button>
              </div>
            ) : (
              <button
                className="upload-empty"
                disabled={p.isGenerating}
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
              disabled={p.isGenerating}
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
          <Select
            label="VLASTNÍ CHECKPOINT"
            value={p.modelId}
            onChange={p.setModelId}
            items={p.models.filter((item) => item.kind !== "base")}
          />
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
          <Label>ROZLIŠENÍ</Label>
          <div className="resolution-values">
            <span>
              VSTUP
              <strong>
                {p.inputItems.length > 1
                  ? "Každý samostatně"
                  : `${p.imageSize.width} × ${p.imageSize.height}`}
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
            label="ZVĚTŠENÍ"
            min={0.5}
            max={4}
            step={0.05}
            value={p.resizeScale}
            onChange={p.setResizeScale}
          />
        </div>
        <button className="library-launch" onClick={() => setLibraryOpen(true)}>
          <Images size={18} />
          <span>
            KNIHOVNA<small>Přetáhni výsledek do vstupů</small>
          </span>
          <ChevronRight size={15} />
        </button>
      </aside>
      <main className="workspace" ref={workspaceRef}>
        <div className="workspace-toolbar">
          <div>
            <h1>
              <span className="heading-glow" />
              {tab === "library" ? "KNIHOVNA OBRÁZKŮ" : "VÝSLEDKY GENEROVÁNÍ"}
            </h1>
            <p>
              {tab === "library"
                ? `${items.length} uložených obrázků`
                : p.isGenerating
                  ? `${p.readyCount} / ${p.outputCount} hotovo · ${p.sourceCount} vstupů`
                  : p.readyCount
                    ? `${p.readyCount} uložených výsledků`
                    : "Tvoje modely. Tvoje obrazy."}
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
        <div className="gallery-tools">
          <div className="segmented tabs">
            <button
              aria-pressed={tab === "results"}
              onClick={() => setTab("results")}
            >
              Výsledky
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
                  index={index}
                  generating={p.isGenerating}
                  progress={p.progressValue}
                  selected={selection.has(item?.id)}
                  onOpen={() => item && open(item, index)}
                  onSelect={() => item && toggleSelection(item.id)}
                  onDownload={() => download(item)}
                  onReuse={() => reuse(item)}
                  onDelete={() => setDeleteTarget(item)}
                  canDelete={!p.isGenerating}
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
              Přidej vstupní obrázky, vyber checkpoint nebo LoRA
              <br />a nech své modely pracovat v cloudu.
            </p>
            <button
              className="toolbar-button"
              onClick={() => inputRef.current.click()}
            >
              <Upload size={14} />
              PŘIDAT OBRÁZKY
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
          progress={p.progressValue}
          job={p.job}
          generating={p.isGenerating}
          startedAt={p.startedAt}
          ready={p.readyCount}
          total={p.outputCount}
          submitting={p.isSubmitting}
          submitted={p.submittedOutputs}
          planned={p.plannedOutputs}
        />
        <div className="settings-heading">
          <SlidersHorizontal size={13} />
          <Label>NASTAVENÍ GENEROVÁNÍ</Label>
        </div>
        <Range
          label="DENOISE"
          min={0.05}
          max={1}
          step={0.01}
          value={p.denoise}
          onChange={p.setDenoise}
          hint="Méně zachová vstup · více jej promění"
        />
        <Range
          label="CFG"
          min={1}
          max={20}
          step={0.1}
          value={p.cfg}
          onChange={p.setCfg}
        />
        <Range
          label="KROKY"
          min={1}
          max={80}
          step={1}
          value={p.steps}
          onChange={p.setSteps}
        />
        <Select
          label="RYCHLOST"
          value={
            p.steps === 15 ? "preview" : p.steps === 25 ? "standard" : "custom"
          }
          onChange={(value) =>
            value !== "custom" && p.setSteps(value === "preview" ? 15 : 25)
          }
          items={[
            { id: "preview", name: "Rychlý náhled · 15 kroků" },
            { id: "standard", name: "Standard · 25 kroků" },
            ...(p.steps !== 15 && p.steps !== 25
              ? [{ id: "custom", name: `Vlastní · ${p.steps} kroků` }]
              : []),
          ]}
        />
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
        <OverallProgress
          progress={p.progressValue}
          job={p.job}
          active={p.isGenerating || p.isSubmitting}
          ready={p.readyCount}
          total={p.outputCount}
        />
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
                  index={index}
                  onOpen={() => p.openLibraryImage(item)}
                  onDownload={() => download(item)}
                  onReuse={() => reuse(item)}
                  onDelete={() => setDeleteTarget(item)}
                  canDelete={!p.isGenerating}
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
              p.openLibraryImage(context.item);
              setContext(null);
            }}
          >
            <Maximize2 />
            Zvětšit
          </button>
          <button
            role="menuitem"
            disabled={p.isGenerating}
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
            disabled={p.isGenerating}
            onClick={() => setDeleteTarget(context.item)}
          >
            <Trash2 />
            Odstranit
          </button>
        </div>
      )}
      {deleteTarget && (
        <div className="modal-backdrop confirm-backdrop">
          <section
            role="alertdialog"
            aria-modal="true"
            aria-label="Odstranit obrázek?"
            className="confirm-dialog"
          >
            <h2>Odstranit obrázek?</h2>
            <p>Výsledek se odstraní z galerie i knihovny.</p>
            <div>
              <button
                className="toolbar-button"
                onClick={() => setDeleteTarget(null)}
              >
                Zrušit
              </button>
              <button
                className="danger-button"
                onClick={async () => {
                  try {
                    await p.deleteLibraryItem(deleteTarget.id);
                    setDeleteTarget(null);
                  } catch (error) {
                    p.setError(error.message);
                  }
                }}
              >
                Odstranit
              </button>
            </div>
          </section>
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
      <select value={value} onChange={(event) => onChange(event.target.value)}>
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
function OverallProgress({ progress, job, active, ready, total }) {
  const idle = job.status === "idle" && !active;
  const value = idle ? 0 : Math.min(100, Math.max(0, Number(progress) || 0));
  const circumference = 2 * Math.PI * 74;
  const complete = job.status === "completed";
  return (
    <section
      className={`overall-progress ${active ? "is-active" : ""} ${complete ? "is-complete" : ""}`}
      aria-label="Celkový postup dávky"
    >
      <div
        className="overall-orbit"
        role="progressbar"
        aria-label="Celkový postup"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <svg viewBox="0 0 200 200" aria-hidden="true">
          <circle className="orbit-guide" cx="100" cy="100" r="91" />
          <circle className="orbit-track" cx="100" cy="100" r="74" />
          <circle
            className="orbit-fill"
            cx="100"
            cy="100"
            r="74"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - value / 100)}
          />
          {active && (
            <g className="orbit-satellite">
              <circle cx="100" cy="9" r="3" />
            </g>
          )}
        </svg>
        <div className="orbit-center">
          <strong>
            {Math.round(value)}
            <small>%</small>
          </strong>
          <span>
            {active
              ? "PROBÍHÁ"
              : complete
                ? "DOKONČENO"
                : job.status === "failed"
                  ? "PŘERUŠENO"
                  : "PŘIPRAVENO"}
          </span>
        </div>
      </div>
      <p>
        {idle
          ? "Prostor pro další nápad"
          : `${ready} z ${total} obrázků hotovo`}
      </p>
      <span className="overall-caption">
        {active
          ? "Každý krok blíž výsledku"
          : complete
            ? "Výsledky najdeš v galerii"
            : job.status === "failed"
              ? "Podrobnosti v průběhu úloh"
              : "Celkový postup se zobrazí zde"}
      </span>
    </section>
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
function ImageCard({
  item,
  index,
  generating,
  progress,
  selected,
  onOpen,
  onSelect,
  onDownload,
  onReuse,
  onDelete,
  canDelete,
  onContext,
}) {
  return (
    <article
      className={`image-card ${selected ? "selected" : ""}`}
      onContextMenu={onContext}
      draggable={Boolean(item)}
      onDragStart={(event) => {
        if (item) {
          event.dataTransfer.setData(
            "application/x-img2img",
            JSON.stringify(item),
          );
          event.dataTransfer.effectAllowed = "copy";
        }
      }}
    >
      <div
        className="card-image"
        role="button"
        tabIndex={item ? 0 : -1}
        aria-label={
          item ? `Zvětšit obrázek ${index + 1}` : `Výstup ${index + 1} čeká`
        }
        onClick={onOpen}
        onKeyDown={(event) => {
          if (
            event.target === event.currentTarget &&
            ["Enter", " "].includes(event.key)
          ) {
            event.preventDefault();
            onOpen();
          }
        }}
      >
        {item ? (
          <img
            src={urlFor(item)}
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
        {item && onSelect && (
          <button
            className={`select-image ${selected ? "is-selected" : ""}`}
            aria-label={`Vybrat obrázek ${index + 1}`}
            aria-pressed={Boolean(selected)}
            onClick={(event) => {
              event.stopPropagation();
              onSelect();
            }}
          >
            {selected ? <Check size={12} /> : null}
          </button>
        )}
        {item && <span className="card-number">{index + 1}</span>}
      </div>
      {item && (
        <footer>
          <div
            className="card-caption"
            title={
              item.source_name || item.settings?.source_name || item.filename
            }
          >
            {item.source_name ||
              item.settings?.source_name ||
              item.model_id ||
              "SDXL"}
            <span>
              {item.width} × {item.height}
            </span>
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
            <IconButton
              label={`Odstranit obrázek ${index + 1}`}
              disabled={!canDelete}
              onClick={onDelete}
            >
              <Trash2 />
            </IconButton>
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
}) {
  const [mode, setMode] = useState("details"),
    [split, setSplit] = useState(50),
    [zoom, setZoom] = useState(1),
    [pan, setPan] = useState({ x: 0, y: 0 });
  const stageRef = useRef(null),
    dialogRef = useRef(null),
    closeRef = useRef(null),
    drag = useRef(null);
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
              mode === "compare" ? "default" : zoom > 1 ? "grab" : "zoom-in",
          }}
          onDoubleClick={() =>
            mode !== "compare" && changeZoom(zoom === 1 ? 2 : 1)
          }
          onPointerDown={(event) => {
            if (zoom <= 1 || mode === "compare") return;
            drag.current = {
              x: event.clientX - pan.x,
              y: event.clientY - pan.y,
            };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            if (drag.current)
              setPan({
                x: event.clientX - drag.current.x,
                y: event.clientY - drag.current.y,
              });
          }}
          onPointerUp={() => {
            drag.current = null;
          }}
          onPointerCancel={() => {
            drag.current = null;
          }}
        >
          <img src={src} alt="Zvětšený výsledek" draggable={false} />
          {mode === "compare" && source && (
            <>
              <img
                className="comparison-source"
                src={`${import.meta.env.VITE_API_URL || ""}${source}`}
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
            : "Kolečko / dvojklik: zoom · tažení: posun · ← → obrázky · Esc zavřít"}
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
              image.model_id || settings.model_id,
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
              ["Denoise", settings.denoise],
              ["CFG", settings.cfg ?? settings.guidance_scale],
              ["Kroky", settings.steps],
              ["Síla LoRA", settings.lora_strength],
              ["Sampler", settings.sampler],
              ["Seed", settings.seed],
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
                  src={`${import.meta.env.VITE_API_URL || ""}${source}`}
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
