from __future__ import annotations

import base64
from datetime import datetime, UTC
import json
import os
import re
import time
from pathlib import Path
import threading
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from PIL import Image, ImageOps

from app_runtime.core import generate, get_options, is_cuda_oom


def resolve_outputs_dir() -> Path:
    configured = os.getenv("OUTPUTS_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).parent.parent / "outputs"


app = FastAPI(title="Img2Img Runtime", version="0.1.0")
JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
GENERATION_LOCK = threading.Lock()
THUMBNAIL_LOCK = threading.Lock()
OUTPUTS_URL_PREFIX = "/library"
THUMBS_URL_PREFIX = "/thumb"
OUTPUTS_DIR = resolve_outputs_dir()
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
THUMBS_DIR = OUTPUTS_DIR / "thumbs"
# The gallery slider reaches 440 CSS px, so 800 px stays sharp on a 2x display.
THUMB_WIDTH = int(os.getenv("THUMB_WIDTH", "800"))
THUMB_QUALITY = int(os.getenv("THUMB_QUALITY", "78"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/options")
def api_options():
    from .archives import archive_options
    return {**get_options(), "archives": archive_options()}


@app.get("/api/history")
def api_history():
    return {"items": load_history_items(), "deleted_ids": load_deleted_ids()}


@app.post("/api/library/{item_id}")
def api_library_save(item_id: str):
    return set_library_membership(item_id, True)


@app.get("/api/library")
def api_library():
    return {"items": load_library_items()}


@app.delete("/api/library/{item_id}")
def api_library_delete(item_id: str):
    return set_library_membership(item_id, False)


def set_library_membership(item_id: str, saved: bool):
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]+", item_id):
        raise HTTPException(status_code=404, detail="Image not found.")
    metadata_path = OUTPUTS_DIR / f"{item_id}.json"
    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="Image not found.")
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not data.get("filename") or not (OUTPUTS_DIR / data["filename"]).is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    data["saved_to_library"] = saved
    data["deleted"] = not saved
    if saved:
        data.pop("deleted_at", None)
    else:
        data["deleted_at"] = now_iso()
    temporary = metadata_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
    temporary.replace(metadata_path)
    _RECORD_CACHE.pop(str(metadata_path), None)
    _LISTING_CACHE.clear()
    return {"ok": True, "id": item_id, "item": data}


def api_library_order(ids: list[str]):
    if any(not isinstance(item, str) for item in ids):
        raise HTTPException(status_code=400, detail="Invalid library order.")
    existing = {item["id"] for item in load_library_items()}
    if len(ids) != len(set(ids)) or not set(ids).issubset(existing):
        raise HTTPException(status_code=400, detail="Library order contains invalid IDs.")
    (OUTPUTS_DIR / "library-order.json").write_text(json.dumps(ids), encoding="utf-8")
    return {"ids": ids}


@app.post("/api/generate")
def api_generate(payload: dict):
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "status": "queued",
        "progress": 0.0,
        "message": "Queued",
        "logs": [build_log("Queued", 0.0)],
        "result": None,
        "error": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "request": {
            "model_id": payload.get("model_id", "tuymans_sdxl"),
            "lora_id": payload.get("lora_id", "none"),
            "num_images": payload.get("num_images", 1),
        },
    }
    with JOBS_LOCK:
        JOBS[job_id] = job

    thread = threading.Thread(target=run_job, args=(job_id, payload), daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def api_job_status(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        return job


@app.get("/thumb/{filename}")
@app.head("/thumb/{filename}")
def api_thumbnail(filename: str, request: Request):
    import re
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.webp", filename):
        raise HTTPException(404, "Thumbnail not found.")
    with THUMBNAIL_LOCK:
        stem = Path(filename).stem
        source = next((p for p in OUTPUTS_DIR.glob(f"{stem}.*")
                       if p.suffix.lower() in {".png", ".webp"}), None)
        target = ensure_thumbnail(source.name) if source else None
        if target is None:
            raise HTTPException(404, "Thumbnail not found.")
        headers = {"Cache-Control": "private, max-age=31536000, immutable",
                   "Content-Length": str(target.stat().st_size)}
        return Response(None if request.method == "HEAD" else target.read_bytes(),
                        media_type="image/webp", headers=headers)


app.mount(OUTPUTS_URL_PREFIX, StaticFiles(directory=OUTPUTS_DIR), name="library")

dist_dir = Path(__file__).parent.parent / "frontend" / "dist"
if dist_dir.exists():
    app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")


def run_job(job_id: str, payload: dict[str, Any]) -> None:
    update_job(job_id, status="waiting", progress=0.01, message="Waiting for GPU slot")

    try:
        with GENERATION_LOCK:
            update_job(job_id, status="running", progress=0.03, message="GPU slot acquired")
            result = generate(payload, progress_callback=lambda progress, message: on_progress(job_id, progress, message))
            result["library_items"] = persist_generated_images(result)
            update_job(
                job_id,
                status="completed",
                progress=1.0,
                message="Completed",
                result=result,
            )
    except Exception as exc:
        status_code = 507 if is_cuda_oom(exc) else 500
        update_job(
            job_id,
            status="failed",
            progress=1.0,
            message="Failed",
            error={"detail": str(exc), "status_code": status_code},
        )


def on_progress(job_id: str, progress: float, message: str) -> None:
    update_job(job_id, status="running", progress=progress, message=message)


def update_job(
    job_id: str,
    *,
    status: str | None = None,
    progress: float | None = None,
    message: str | None = None,
    result: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return

        if status is not None:
            job["status"] = status
        if progress is not None:
            job["progress"] = min(max(progress, 0.0), 1.0)
        if message is not None:
            job["message"] = message
            if not job["logs"] or job["logs"][-1]["message"] != message:
                job["logs"].append(build_log(message, job["progress"]))
                job["logs"] = job["logs"][-120:]
        if result is not None:
            job["result"] = result
        if error is not None:
            job["error"] = error
        job["updated_at"] = now_iso()


def build_log(message: str, progress: float) -> dict[str, Any]:
    return {
        "timestamp": now_iso(),
        "progress": round(min(max(progress, 0.0), 1.0), 4),
        "message": message,
    }


def persist_generated_images(result: dict[str, Any]) -> list[dict[str, Any]]:
    meta = result.get("meta", {})
    saved_items = []

    for index, image in enumerate(result.get("images", []), start=1):
        meta = {**result.get("meta", {}), **image.get("generation_meta", {})}
        raw = base64.b64decode(image["image_base64"])
        extension = image.get("format", "png").lower()
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        # A checkpoint mix id contains ":", "=" and ","; file names (and gallery URLs) allow only [A-Za-z0-9_-].
        model_part = re.sub(r"[^A-Za-z0-9_-]+", "_", str(meta.get("model_id", "model"))).strip("_")[:90] or "model"
        stem = f"{timestamp}_{index:02d}_{model_part}"
        image_name = f"{stem}.{extension}"
        image_path = OUTPUTS_DIR / image_name
        image_path.write_bytes(raw)
        try:
            ensure_thumbnail(image_name)  # the gallery never has to decode the full image on the gateway
        except Exception:
            pass  # the gateway still builds it on demand

        record = {
            "id": stem,
            "filename": image_name,
            "url": f"{OUTPUTS_URL_PREFIX}/{image_name}",
            "thumb_url": f"{THUMBS_URL_PREFIX}/{thumb_filename(image_name)}",
            "width": image.get("width"),
            "height": image.get("height"),
            "format": extension,
            "created_at": now_iso(),
            "model_id": meta.get("model_id"),
            "lora_id": meta.get("lora_id"),
            "settings": meta,
            "saved_to_library": False,
        }
        metadata_path = OUTPUTS_DIR / f"{stem}.json"
        metadata_path.write_text(json.dumps(record, ensure_ascii=True, indent=2), encoding="utf-8")
        saved_items.append(record)

    return saved_items


_RECORD_CACHE: dict[str, tuple[int, int, int, Any]] = {}


def read_record(path: Path) -> Any:
    """Parse a metadata JSON once per (mtime, size); the gallery rescans on every request."""
    stat = path.stat()
    # Writers replace the file atomically, so the inode changes even when mtime and size do not.
    key = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
    cached = _RECORD_CACHE.get(str(path))
    if cached and cached[:3] == key:
        data = cached[3]
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        _RECORD_CACHE[str(path)] = (*key, data)
    return dict(data) if isinstance(data, dict) else data


def warm_records(paths: list[Path]) -> None:
    """Read not-yet-cached records concurrently. On a cold container every file is a network round trip, and
    reading hundreds one after another took ~50 s; 32 at a time takes a couple of seconds."""
    cold = [path for path in paths if str(path) not in _RECORD_CACHE]
    if len(cold) < 8:
        return
    from concurrent.futures import ThreadPoolExecutor

    def read(path):
        try:
            read_record(path)
        except (OSError, ValueError):
            pass
    with ThreadPoolExecutor(max_workers=32) as pool:
        list(pool.map(read, cold))


def metadata_paths() -> list[Path]:
    paths = list(OUTPUTS_DIR.glob("*.json"))
    if len(_RECORD_CACHE) > len(paths) + 256:  # forget records of files that vanished
        live = {str(path) for path in paths}
        for key in [key for key in _RECORD_CACHE if key not in live]:
            del _RECORD_CACHE[key]
    return paths


# One scan of the metadata files answers both /api/history lists. Every write replaces or adds a
# file, which bumps the directory mtime, so that mtime (plus explicit clears) is a safe cache key.
_LISTING_CACHE: dict[str, Any] = {}


def scan_records() -> tuple[list[dict[str, Any]], list[str]]:
    try:
        stamp = OUTPUTS_DIR.stat().st_mtime_ns
    except OSError:
        return [], []
    # The 5 s ceiling is a safety net for filesystems that do not bump directory mtimes promptly.
    if _LISTING_CACHE.get("key") == (str(OUTPUTS_DIR), stamp) and time.monotonic() - _LISTING_CACHE["at"] < 5:
        return _LISTING_CACHE["value"]
    items, deleted = [], []
    paths = metadata_paths()
    warm_records(paths)
    for metadata_path in sorted(paths, reverse=True):
        try:
            data = read_record(metadata_path)
            if not isinstance(data, dict) or "filename" not in data:
                continue
            if data.get("deleted", False):
                deleted.append(data["id"])
                continue
            if not (OUTPUTS_DIR / data["filename"]).exists():
                continue
            if "url" not in data:
                data["url"] = f"{OUTPUTS_URL_PREFIX}/{data['filename']}"
            data["thumb_url"] = f"{THUMBS_URL_PREFIX}/{thumb_filename(data['filename'])}"
            items.append(data)
        except Exception:
            continue
    _LISTING_CACHE.update(key=(str(OUTPUTS_DIR), stamp), value=(items, deleted), at=time.monotonic())
    return items, deleted


def load_deleted_ids():
    return list(scan_records()[1])


def purge_deleted(days: int = 30, now: float | None = None) -> int:
    """Really remove images the user deleted more than `days` ago (file, thumbnail, record)."""
    now = time.time() if now is None else now
    removed = 0
    for path in metadata_paths():
        try:
            data = read_record(path)
            if not isinstance(data, dict) or not data.get("deleted"):
                continue
            stamp = data.get("deleted_at")
            deleted_at = datetime.fromisoformat(stamp).timestamp() if stamp else path.stat().st_mtime
            if now - deleted_at < days * 86400:
                continue
            filename = data.get("filename")
            if filename and re.fullmatch(r"[A-Za-z0-9_.-]+", filename):
                (OUTPUTS_DIR / filename).unlink(missing_ok=True)
                thumb_path(filename).unlink(missing_ok=True)
            path.unlink(missing_ok=True)
            _RECORD_CACHE.pop(str(path), None)
            removed += 1
        except (OSError, ValueError, KeyError):
            continue
    if removed:
        _LISTING_CACHE.clear()
    return removed


def thumb_filename(filename: str) -> str:
    return f"{Path(filename).stem}.webp"


def thumb_path(filename: str) -> Path:
    return THUMBS_DIR / thumb_filename(filename)


def ensure_thumbnail(filename: str) -> Path | None:
    """Create a small WebP preview once per image. Returns None if the source is missing."""
    source = OUTPUTS_DIR / filename
    if not source.is_file():
        return None
    target = thumb_path(filename)
    try:
        if target.is_file() and target.stat().st_mtime_ns >= source.stat().st_mtime_ns:
            # Also re-render when the configured preview width changed.
            with Image.open(target) as cached:
                width, cached_height = cached.size
            with Image.open(source) as raw:
                source_width, _ = raw.size
            if width == min(THUMB_WIDTH, source_width) and cached_height > 0:
                return target
    except OSError:
        pass
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
        if image.width > THUMB_WIDTH:
            ratio = THUMB_WIDTH / image.width
            image = image.resize((THUMB_WIDTH, max(1, round(image.height * ratio))), Image.Resampling.LANCZOS)
        temporary = target.with_suffix(f".{uuid.uuid4().hex[:8]}.tmp")  # unique: concurrent requests must not share a temp file
        image.save(temporary, "WEBP", quality=THUMB_QUALITY, method=4)
    os.replace(temporary, target)
    return target


def load_history_items() -> list[dict[str, Any]]:
    return [dict(item) for item in scan_records()[0]]


def load_library_items() -> list[dict[str, Any]]:
    # The library holds only what was explicitly saved. Records written before the
    # canvas/library split have no flag (or null) and stay saved for continuity.
    items = [item for item in load_history_items() if item.get("saved_to_library") is not False]
    try:
        order = json.loads((OUTPUTS_DIR / "library-order.json").read_text(encoding="utf-8"))
        positions = {item_id: index for index, item_id in enumerate(order)}
        items.sort(key=lambda item: positions.get(item["id"], len(positions)))
    except (OSError, ValueError, TypeError):
        pass
    return items


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
