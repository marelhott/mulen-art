"""Deploy with: .venv/bin/modal deploy modal_app.py (after building frontend)."""
import os
import modal

APP_NAME = "img2img-studio"
app = modal.App(APP_NAME)
models = modal.Volume.from_name("img2img-models", create_if_missing=True)
archives = modal.Volume.from_name("img2img-archives")
outputs = modal.Volume.from_name("img2img-outputs", create_if_missing=True)
jobs = modal.Dict.from_name("img2img-jobs", create_if_missing=True)
# One entry per admitted GPU job (job_id -> {"ts", "call_id"}); enforces the global GPU cap below.
slots = modal.Dict.from_name("img2img-slots", create_if_missing=True)
# Jobs waiting for a slot: pending maps job_id -> submit time (small, cheap to list); the
# potentially large payloads live in a separate Dict so ordering never downloads them.
pending = modal.Dict.from_name("img2img-pending", create_if_missing=True)
payloads = modal.Dict.from_name("img2img-payloads", create_if_missing=True)
state = modal.Volume.from_name("img2img-state", create_if_missing=True)
base_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi==0.115.6", "pillow==11.1.0")
    .env({"MODEL_CONFIG_PATH": "/app/config/models.json", "OUTPUTS_DIR": "/outputs", "ARCHIVE_ROOT": "/archives/atelier-archives",
          # Fallback rate (Modal L4); per-image estimates use the GPU that actually ran the job.
          "GPU_HOURLY_USD": "0.80"})
    .add_local_python_source("app_runtime")
    .add_local_dir("config", "/app/config")
)
gpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements("app_runtime/requirements.txt")
    .env({
        "MODEL_CONFIG_PATH": "/app/config/models.json", "OUTPUTS_DIR": "/outputs", "ARCHIVE_ROOT": "/archives/atelier-archives",
        "HF_HOME": "/models/huggingface-cache", "MAX_IMAGE_SIDE": "1536",
        "TOKENIZERS_PARALLELISM": "false",
        # Published Modal L4 rate, used only to show a per-image cost estimate in the UI.
        "GPU_HOURLY_USD": "0.80",
    })
    .add_local_python_source("app_runtime")
    .add_local_dir("config", "/app/config")
)

# GPU concurrency: Modal autoscales each distinct model_id parameter as its own container pool,
# so max_containers bounds ONE model's pool, not the whole app. The app-wide cost cap is enforced
# here instead: at most MAX_GPU_JOBS jobs run at once across all models (one job = one GPU
# container; idle containers inside scaledown_window can briefly add to that). Everything beyond
# it WAITS in `pending` (FIFO) so a 252-job batch still queues, and the single-instance
# `dispatch` function (max_containers=1 => serialized, so the Dict needs no locking) starts the
# next job whenever a slot frees. MAX_BACKLOG_JOBS only guards against runaway submit loops.
MAX_GPU_JOBS = 10
MAX_BACKLOG_JOBS = int(os.environ.get("MAX_BACKLOG_JOBS", "1000"))
SLOT_TTL_SECONDS = 1200 + 300  # worker timeout + slack; reclaims slots leaked by a crashed worker
SNAPSHOT = os.environ.get("MODAL_GPU_SNAPSHOT") == "1"  # alpha GPU memory snapshot, opt-in at deploy time


def store_size(store):
    # modal.Dict has no __len__; it exposes .len() instead.
    return store.len() if hasattr(store, "len") else len(store)


def release_slot(store, job_id):
    try:
        store.pop(job_id)
    except KeyError:
        pass


def release_slot_for_call(store, call_id):
    for key, entry in list(store.items()):
        if entry.get("call_id") == call_id:
            release_slot(store, key)


def drain_pending(pending, payloads, slots, spawn, is_cancelled, on_started, on_failed,
                  cap=MAX_GPU_JOBS, ttl=SLOT_TTL_SECONDS, now=None):
    """Start queued jobs, oldest first, while fewer than `cap` are running. Serialized by Modal."""
    import time
    now = time.time() if now is None else now
    for key, entry in list(slots.items()):
        if now - entry.get("ts", 0) > ttl:
            release_slot(slots, key)
    live = store_size(slots)
    started = 0
    for job_id, _ts in sorted(pending.items(), key=lambda item: item[1]):
        if is_cancelled(job_id):  # cancelled while waiting: drop it, never spend a GPU on it
            release_slot(pending, job_id); release_slot(payloads, job_id)
            continue
        if live >= cap:
            break
        slots[job_id] = {"ts": now, "call_id": None}
        try:
            call_id = spawn(job_id, payloads[job_id])
        except Exception as exc:
            release_slot(slots, job_id)
            on_failed(job_id, exc)
        else:
            if job_id in slots:  # the worker may already have finished and released it
                slots[job_id] = {"ts": now, "call_id": call_id}
            on_started(job_id, call_id)
            live += 1
            started += 1
        release_slot(pending, job_id); release_slot(payloads, job_id)
    return started


def spawn_job(job_id, payload):
    """Gateway submit: queue the job; `dispatch` starts it when a GPU slot is free.

    Returns None because there is no FunctionCall yet; dispatch records `call:<job_id>` for cancel.
    """
    import time
    if store_size(pending) >= MAX_BACKLOG_JOBS:
        raise RuntimeError(f"Job backlog full ({MAX_BACKLOG_JOBS} jobs waiting)")
    payloads[job_id] = payload
    pending[job_id] = time.time()
    try:
        dispatch.spawn()
    except Exception:
        release_slot(pending, job_id); release_slot(payloads, job_id)
        raise
    return None


def cancel_call(call_id):
    modal.FunctionCall.from_id(call_id).cancel()
    release_slot_for_call(slots, call_id)
    try:
        dispatch.spawn()
    except Exception:
        pass


# Published Modal per-hour rates, used only for the UI's per-image estimate.
# Modal reports an A10G as "NVIDIA A10", hence the "A10" key.
GPU_RATES_USD_HOUR = {"L4": 0.80, "A10": 1.10}


def gpu_rate():
    """Rate of the GPU this container really got (L4, or A10G when L4 capacity was short)."""
    try:
        import torch
        name = torch.cuda.get_device_name(0)
    except Exception:
        return None, None
    for key, rate in GPU_RATES_USD_HOUR.items():
        if key in name:
            return key, rate
    return name, None


def generate_job(job_id: str, payload: dict):
    import time
    from app_runtime.core import generate
    from app_runtime.server import persist_generated_images, now_iso
    record = jobs[job_id]

    def put(value):
        # The user may have cancelled meanwhile; never overwrite that state with a progress tick.
        current = jobs.get(job_id)
        if current and current.get("status") == "cancelled":
            return
        jobs[job_id] = value
    started = time.monotonic()
    last_update = 0.0
    library_items = []
    first_image_seconds = None
    gpu_name, gpu_hourly = gpu_rate()

    def image_ready(image, meta):
        nonlocal record, first_image_seconds
        meta = {**meta, "source_name": meta.get("source_name") or payload.get("source_name", "Input image"), "source_url": meta.get("source_url") or payload.get("source_url")}
        # Real GPU time up to this saved image, so the library can show cost per file.
        meta = {**meta, "worker_seconds": round(time.monotonic() - started, 2), "gpu": gpu_name, "gpu_hourly_usd": gpu_hourly}
        items = persist_generated_images({"images": [image], "meta": dict(meta)})
        # Other containers must see the files before their URLs are published.
        outputs.commit()
        library_items.extend(items)
        if first_image_seconds is None:
            first_image_seconds = round(time.monotonic() - started, 2)
        record = {**record, "status": "running", "partial_images": list(library_items),
                  "first_image_seconds": first_image_seconds, "updated_at": now_iso()}
        put(record)

    def progress(value, message):
        nonlocal last_update, record
        now = time.monotonic()
        # Ten workers polling once per second each rewrote the whole job record.
        if now - last_update < 2 and value < 1:
            return
        last_update = now
        record = {**record, "status": "running", "progress": min(value, 0.98),
                  "message": message, "updated_at": now_iso()}
        record["logs"] = (record["logs"] + [{"timestamp": now_iso(), "progress": min(value, 0.98), "message": message}])[-12:]
        put(record)

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
        result["meta"].update(gpu=gpu_name, gpu_hourly_usd=gpu_hourly)
        result["meta"]["first_image_seconds"] = first_image_seconds
        put({**record, "status": "completed", "progress": 1,
             "message": "Completed", "updated_at": now_iso(), "result": result})
    except Exception as exc:
        try:
            outputs.commit()
        except Exception:
            pass
        put({**record, "status": "failed",
             "message": "Failed", "updated_at": now_iso(),
             "error": {"detail": str(exc)}})
        raise


@app.cls(
    image=gpu_image, gpu=["L4", "A10G"], cpu=2, memory=16384,
    volumes={"/models": models, "/outputs": outputs, "/archives": archives},
    # Per model pool (see MAX_GPU_JOBS above): one container per job, 10 per model.
    min_containers=0, max_containers=MAX_GPU_JOBS, scaledown_window=20,
    timeout=1200, retries=0,
    enable_memory_snapshot=SNAPSHOT,
    experimental_options={"enable_gpu_snapshot": True} if SNAPSHOT else {},
)
class ImageWorker:
    model_id: str = modal.parameter()

    @modal.enter()
    def preload(self):
        """Load this pool's checkpoint at container start so the first job does not pay for it."""
        try:
            models.reload()
            from app_runtime.core import ensure_pipeline, use_demo_mode
            if not use_demo_mode():
                ensure_pipeline(self.model_id)
        except Exception as exc:  # run() retries lazily and reports the real error on the job
            print(f"preload of {self.model_id} failed: {exc}")

    @modal.method()
    def run(self, job_id: str, payload: dict):
        try:
            return generate_job(job_id, payload)
        finally:
            release_slot(slots, job_id)
            try:
                dispatch.spawn()  # a slot is free: start the next waiting job
            except Exception as exc:
                print(f"dispatch wake-up failed (the periodic sweep will catch up): {exc}")


@app.function(
    image=base_image, max_containers=1, scaledown_window=20, cpu=0.25, memory=512, timeout=300,
    # Safety net if a wake-up is ever lost: the queue is also swept every two minutes.
    schedule=modal.Period(minutes=2),
)
def dispatch():
    from app_runtime.server import now_iso

    def spawn(job_id, payload):
        return ImageWorker(model_id=payload["model_id"]).run.spawn(job_id, payload).object_id

    def is_cancelled(job_id):
        record = jobs.get(job_id)
        return record is None or record.get("status") == "cancelled"

    def on_started(job_id, call_id):
        jobs[f"call:{job_id}"] = call_id
        if is_cancelled(job_id):  # cancelled in the instant between the check and the spawn
            try:
                cancel_call(call_id)
            except Exception:
                pass

    def on_failed(job_id, exc):
        record = jobs.get(job_id)
        if record and record.get("status") != "cancelled":
            jobs[job_id] = {**record, "status": "failed", "message": "Failed", "updated_at": now_iso(),
                            "error": {"detail": f"Could not start the cloud job: {exc}"}}

    drain_pending(pending, payloads, slots, spawn, is_cancelled, on_started, on_failed)


@app.function(
    image=base_image, volumes={"/outputs": outputs}, cpu=0.25, memory=512, timeout=600,
    schedule=modal.Cron("17 3 * * *"),
)
def purge_deleted_images():
    """Daily: really remove images deleted more than RETENTION_DAYS ago, so the Volume stops growing."""
    from app_runtime.server import purge_deleted
    outputs.reload()
    removed = purge_deleted(int(os.environ.get("DELETED_RETENTION_DAYS", "30")))
    if removed:
        outputs.commit()
    print(f"purged {removed} deleted images")


@app.function(
    image=base_image.add_local_dir("frontend/dist", "/app/frontend/dist"),
    volumes={"/outputs": outputs, "/state": state, "/archives": archives},
    min_containers=0, max_containers=1, scaledown_window=20,
    cpu=0.25, memory=512,
    # STUDIO_USERNAME / STUDIO_PASSWORD, optional MONTHLY_IMAGE_LIMIT and MAX_JOBS_PER_REQUEST.
    secrets=[modal.Secret.from_name("img2img-auth")],
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app(label="i")
def web():
    from app_runtime.cloud_server import (create_app, VolumeUsage, optional_int_env,
                                         DEFAULT_MAX_JOBS_PER_REQUEST)
    # Missing credentials make create_app refuse to start rather than serve an open GPU.
    return create_app(
        jobs=jobs, usage=VolumeUsage("/state/usage.json", state), submit=spawn_job,
        refresh=outputs.reload, commit=outputs.commit,
        cancel=cancel_call,
        username=os.environ.get("STUDIO_USERNAME"), password=os.environ.get("STUDIO_PASSWORD"),
        monthly_limit=optional_int_env("MONTHLY_IMAGE_LIMIT"),
        max_jobs_per_request=optional_int_env("MAX_JOBS_PER_REQUEST", DEFAULT_MAX_JOBS_PER_REQUEST),
        frontend_dir="/app/frontend/dist",
    )
