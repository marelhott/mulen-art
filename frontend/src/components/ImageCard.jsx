import React from "react";
import { creationMode } from "../studioTools";
import {
  ArrowDownToLine,
  Check,
  ImagePlus,
  Plus,
  Trash2,
} from "lucide-react";
import { thumbFor, urlFor } from "../shared";
import { RetryImage } from "./RetryImage";
import { IconButton } from "./controls";

export function ImageCard({
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
  const mode = creationMode(item);
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
          <RetryImage
            src={thumbFor(item)}
            fallbackSrc={urlFor(item)}
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
        {mode && <span className="card-mode-badge" title="Způsob tvorby">{mode}</span>}
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
