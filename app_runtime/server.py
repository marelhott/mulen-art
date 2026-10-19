from __future__ import annotations

import base64
from datetime import datetime, UTC
import json
import os
from pathlib import Path
import threading
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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
OUTPUTS_URL_PREFIX = "/library"
OUTPUTS_DIR = resolve_outputs_dir()
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

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
    return get_options()


@app.get("/api/library")
def api_library():
    return {"items": load_library_items()}


@app.delete("/api/library/{item_id}")
def api_library_delete(item_id: str):
    metadata_path = OUTPUTS_DIR / f"{item_id}.json"
    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="Library item not found.")

    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Invalid library metadata: {exc}") from exc

    image_name = data.get("filename")
    image_path = OUTPUTS_DIR / image_name if image_name else None

    try:
        metadata_path.unlink(missing_ok=True)
        if image_path is not None:
            image_path.unlink(missing_ok=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete library item: {exc}") from exc

    return {"ok": True, "id": item_id}


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
        raw = base64.b64decode(image["image_base64"])
        extension = image.get("format", "png").lower()
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        stem = f"{timestamp}_{index:02d}_{meta.get('model_id', 'model')}"
        image_name = f"{stem}.{extension}"
        image_path = OUTPUTS_DIR / image_name
        image_path.write_bytes(raw)

        record = {
            "id": stem,
            "filename": image_name,
            "url": f"{OUTPUTS_URL_PREFIX}/{image_name}",
            "width": image.get("width"),
            "height": image.get("height"),
            "format": extension,
            "created_at": now_iso(),
            "model_id": meta.get("model_id"),
            "lora_id": meta.get("lora_id"),
            "settings": meta,
        }
        metadata_path = OUTPUTS_DIR / f"{stem}.json"
        metadata_path.write_text(json.dumps(record, ensure_ascii=True, indent=2), encoding="utf-8")
        saved_items.append(record)

    return saved_items


def load_library_items() -> list[dict[str, Any]]:
    items = []
    for metadata_path in sorted(OUTPUTS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
            image_path = OUTPUTS_DIR / data["filename"]
            if not image_path.exists():
                continue
            if "url" not in data:
                data["url"] = f"{OUTPUTS_URL_PREFIX}/{data['filename']}"
            items.append(data)
        except Exception:
            continue
    try:
        order = json.loads((OUTPUTS_DIR / "library-order.json").read_text(encoding="utf-8"))
        positions = {item_id: index for index, item_id in enumerate(order)}
        items.sort(key=lambda item: positions.get(item["id"], len(positions)))
    except (OSError, ValueError, TypeError):
        pass
    return items


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
