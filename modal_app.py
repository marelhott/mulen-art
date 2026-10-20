"""Deploy with: .venv/bin/modal deploy modal_app.py (after building frontend)."""
import os
from pathlib import Path
import modal

APP_NAME = "img2img-studio"
app = modal.App(APP_NAME)
models = modal.Volume.from_name("img2img-models", create_if_missing=True)
outputs = modal.Volume.from_name("img2img-outputs", create_if_missing=True)
jobs = modal.Dict.from_name("img2img-jobs", create_if_missing=True)
state = modal.Volume.from_name("img2img-state", create_if_missing=True)
base_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi==0.115.6", "pillow==11.1.0")
    .env({"MODEL_CONFIG_PATH": "/app/config/models.json", "OUTPUTS_DIR": "/outputs"})
    .add_local_python_source("app_runtime")
    .add_local_dir("config", "/app/config")
)
gpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements("app_runtime/requirements.txt")
    .env({
        "MODEL_CONFIG_PATH": "/app/config/models.json", "OUTPUTS_DIR": "/outputs",
        "HF_HOME": "/models/huggingface-cache", "MAX_IMAGE_SIDE": "1536",
        "TOKENIZERS_PARALLELISM": "false",
    })
    .add_local_python_source("app_runtime")
    .add_local_dir("config", "/app/config")
)

@app.function(
    image=gpu_image, gpu="L4", cpu=2, memory=16384,
    volumes={"/models": models, "/outputs": outputs},
    min_containers=0, max_containers=10, scaledown_window=20,
    timeout=1200, retries=0,
)
def generate_image(job_id: str, payload: dict):
    import time
    from app_runtime.core import generate
    from app_runtime.server import persist_generated_images, now_iso
    record = jobs[job_id]
    started = time.monotonic()
    last_update = 0.0
    library_items = []
    first_image_seconds = None

    def image_ready(image, meta):
        nonlocal record, first_image_seconds
        meta = {**meta, "source_name": meta.get("source_name") or payload.get("source_name", "Input image"), "source_url": meta.get("source_url") or payload.get("source_url")}
        items = persist_generated_images({"images": [image], "meta": dict(meta)})
        outputs.commit()
        library_items.extend(items)
        if first_image_seconds is None:
            first_image_seconds = round(time.monotonic() - started, 2)
        record = {**record, "status": "running", "partial_images": list(library_items),
                  "first_image_seconds": first_image_seconds, "updated_at": now_iso()}
        jobs[job_id] = record

    def progress(value, message):
        nonlocal last_update, record
        now = time.monotonic()
        if now - last_update < 1 and value < 1:
            return
        last_update = now
        record = {**record, "status": "running", "progress": min(value, 0.98),
                  "message": message, "updated_at": now_iso()}
        record["logs"] = (record["logs"] + [{"timestamp": now_iso(), "progress": min(value, 0.98), "message": message}])[-30:]
        jobs[job_id] = record

    try:
        models.reload()
        outputs.reload()
        progress(0.01, "Loading model on cloud GPU")
        result = generate(payload, progress_callback=progress, image_callback=image_ready)
        result["meta"]["source_name"] = result["meta"].get("source_name") or payload.get("source_name", "Input image")
        result["meta"]["source_url"] = result["meta"].get("source_url") or payload.get("source_url")
        if not library_items:  # Local demo tests do not emit incremental images.
            library_items = persist_generated_images(result)
            outputs.commit()
        result["images"] = library_items
        result["library_items"] = library_items
        result["meta"]["worker_seconds"] = round(time.monotonic() - started, 2)
        result["meta"]["first_image_seconds"] = first_image_seconds
        jobs[job_id] = {**record, "status": "completed", "progress": 1,
                        "message": "Completed", "updated_at": now_iso(), "result": result}
    except Exception as exc:
        jobs[job_id] = {**record, "status": "failed",
                        "message": "Failed", "updated_at": now_iso(),
                        "error": {"detail": str(exc)}}
        raise


def web_secret():
    """Only deployment reads the local credential; cloud uses the Modal Secret."""
    if modal.is_local():
        import json
        credentials_path = Path(".modal-app-credentials.json")
        if not credentials_path.exists():
            raise RuntimeError("Run .venv/bin/python scripts/prepare_modal.py first.")
        return modal.Secret.from_dict(json.loads(credentials_path.read_text()))
    return modal.Secret.from_name("img2img-web")


@app.function(
    image=base_image.add_local_dir("frontend/dist", "/app/frontend/dist"),
    volumes={"/outputs": outputs, "/state": state},
    min_containers=0, max_containers=1, scaledown_window=20,
    cpu=0.25, memory=512,
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app(label="i")
def web():
    from app_runtime.cloud_server import create_app, VolumeUsage
    return create_app(
        jobs=jobs, usage=VolumeUsage("/state/usage.json", state), submit=lambda job_id, payload: generate_image.spawn(job_id, payload).object_id,
        refresh=outputs.reload, commit=outputs.commit,
        username=None, password=None, auth_enabled=False,
        frontend_dir="/app/frontend/dist",
    )
