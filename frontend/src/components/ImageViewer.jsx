import React, { useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ChevronLeft,
  ChevronRight,
  Columns2,
  ImagePlus,
  Maximize2,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { urlFor, sourceFor, duration, dateFor } from "../shared";
import { IconButton, Label } from "./controls";
import { sourceUrl } from "../api";

export function ImageViewer({
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
              ["Odhad ceny", settings.worker_seconds && (settings.gpu_hourly_usd || gpuHourlyUsd) ? `$${(settings.worker_seconds / 3600 * (settings.gpu_hourly_usd || gpuHourlyUsd)).toFixed(4)}` : undefined],
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
