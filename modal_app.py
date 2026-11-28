"""Deploy with: .venv/bin/modal deploy modal_app.py (after building frontend)."""
import logging
import os
import modal

APP_NAME = "img2img-studio"
log = logging.getLogger("mulen")
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
# One entry per finished job ("YYYY-MM:job_id" -> estimated GPU USD); written once per job, so
# concurrent workers never race, and summed per month for the optional dollar budget.
spend = modal.Dict.from_name("img2img-spend", create_if_missing=True)
payloads = modal.Dict.from_name("img2img-payloads", create_if_missing=True)
state = modal.Volume.from_name("img2img-state", create_if_missing=True)
base_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements("app_runtime/requirements-gateway.txt")
    .env({"MODEL_CONFIG_PATH": "/app/config/models.json", "OUTPUTS_DIR": "/outputs", "ARCHIVE_ROOT": "/archives/atelier-archives",
          # Fallback rate (Modal L4); per-image estimates use the GPU that actually ran the job.
          "GPU_HOURLY_USD": "0.80"})
    .add_local_python_source("app_runtime")
    .add_local_dir("config", "/app/config")
)
nano_secret = modal.Secret.from_name("nano-keys")  # OpenRouter and Venice keys; only the Vari/Koláž functions see it
# Own image (not base_image + pip_install): Modal wants build steps before add_local_*.
nano_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements("app_runtime/requirements-gateway.txt")
    .pip_install("httpx==0.28.1")
    .env({"MODEL_CONFIG_PATH": "/app/config/models.json", "OUTPUTS_DIR": "/outputs", "ARCHIVE_ROOT": "/archives/atelier-archives",
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
# next job whenever a slot frees (small requests first, then oldest first). MAX_BACKLOG_JOBS only guards against runaway submit loops.
MAX_GPU_JOBS = 10
MAX_BACKLOG_JOBS = int(os.environ.get("MAX_BACKLOG_JOBS", "1000"))
SLOT_TTL_SECONDS = 1200 + 300  # worker timeout + slack; reclaims slots leaked by a crashed worker
# A GPU container stays up this long after its job: the next batch (or a quick re-run) reuses the loaded checkpoint instead of
# paying the ~20 s cold start. Measured: a warm container starts a job in ~2 s, a cold one in 17-40 s (4 min right after a deploy).
WORKER_IDLE_SECONDS = 60
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
    if payload.get("generation_type") in {"vari", "collage"}:
        # Provider API calls need no GPU: straight to the CPU function, no slot, no queue.
        return nano_job.spawn(job_id, payload).object_id
    if store_size(pending) >= MAX_BACKLOG_JOBS:
        raise RuntimeError(f"Job backlog full ({MAX_BACKLOG_JOBS} jobs waiting)")
    payloads[job_id] = payload
    pending[job_id] = [payload.get("queue_priority", 1), time.time()]  # [priority, submit time]; lowest first
    try:
        dispatch.spawn()
    except Exception:
        release_slot(pending, job_id); release_slot(payloads, job_id)
        raise
    return None


_SPEND_CACHE = {}


def month_spend(month):
    """Estimated GPU dollars spent this month (worker time only; container boot is not counted).

    Summing walks every entry of a shared Dict over the network, so the result is kept for 30 s."""
    import time
    cached = _SPEND_CACHE.get(month)
    if cached and time.monotonic() - cached[0] < 30:
        return cached[1]
    prefix = f"{month}:"
    total = sum(value for key, value in spend.items() if key.startswith(prefix))
    _SPEND_CACHE[month] = (time.monotonic(), total)
    return total


def record_spend(job_id, seconds, hourly_usd):
    import time
    rate = hourly_usd if hourly_usd else float(os.environ.get("GPU_HOURLY_USD", "0.80"))
    month = time.strftime('%Y-%m', time.gmtime())
    spend[f"{month}:{job_id}"] = round(seconds / 3600 * rate, 5)
    _SPEND_CACHE.pop(month, None)


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


# The unCLIP presets of the frontend (reimagineTools.js) that Vari can run before its own model.
UNCLIP_PRESETS = {"free": {"denoise": 0.8, "noise_level": 0}, "loose": {"denoise": 0.65, "noise_level": 150}}


def unclip_stage(job_id, payload, preset, count, progress, cancelled):
    """Vari pre-stage: queue an unCLIP GPU job for the same source (through the normal queue and GPU cap), wait for it and
    return its images. A cancelled parent job cancels the child."""
    import time
    from dataclasses import asdict
    from PIL import Image
    from app_runtime.core import parse_input
    from app_runtime.server import OUTPUTS_DIR, now_iso
    settings = {"generation_type": "reimagine", "reimagine_mode": "unclip", "long_side": 1024, "steps": 35, "cfg": 5.0, "num_images": count,
                "seed": -1, "image_base64": "stored", **UNCLIP_PRESETS[preset],
                "glitch": payload.get("pre_unclip_glitch") or "", "glitch_until": payload.get("glitch_until")}
    pre = asdict(parse_input(settings))
    pre.update(image_base64="", source_file=payload["source_file"], source_name=payload.get("source_name", "Input image"),
               source_url=payload.get("source_url"), queue_priority=0)
    pre_id = f"{job_id}-unclip"
    jobs[pre_id] = {"id": pre_id, "status": "queued", "progress": 0, "message": "Waiting for cloud GPU", "source_name": pre["source_name"],
                    "source_url": pre["source_url"], "expected_images": count, "generation_type": "reimagine", "model_id": pre["model_id"],
                    "logs": [], "result": None, "error": None, "created_at": now_iso(), "updated_at": now_iso()}
    jobs[f"children:{job_id}"] = [pre_id]  # cancelling the parent in the gateway cancels these too
    call_id = spawn_job(pre_id, pre)
    if call_id:
        jobs[f"call:{pre_id}"] = call_id
    deadline = time.monotonic() + 1300
    while True:
        if cancelled():
            from app_runtime.cloud_server import cancel_children
            cancel_children(jobs, job_id, cancel_call)
            raise RuntimeError("Zrušeno.")
        record = jobs.get(pre_id) or {}
        status = record.get("status")
        progress(0.06 + 0.24 * float(record.get("progress") or 0), f"unCLIP: {record.get('message') or status or 'čeká'}")
        if status == "completed":
            break
        if status in ("failed", "cancelled"):
            raise RuntimeError("unCLIP selhal: " + str((record.get("error") or {}).get("detail", status)))
        if time.monotonic() > deadline:
            raise RuntimeError("unCLIP trvá příliš dlouho.")
        time.sleep(3)
    outputs.reload()
    images = []
    for item in (record.get("result") or {}).get("library_items") or record.get("partial_images") or []:
        with Image.open(OUTPUTS_DIR / item["filename"]) as image:
            images.append(image.convert("RGB"))
    return images


def generate_job(job_id: str, payload: dict):
    import time
    from app_runtime.core import generate
    from app_runtime.server import persist_generated_images, now_iso, materialize_source
    record = jobs[job_id]

    def cancelled():
        # The gateway sets a dedicated flag BEFORE it rewrites the job as cancelled, so a worker write can
        # never win the race between "check status" and "write status".
        if jobs.get(f"cancelled:{job_id}"):
            return True
        current = jobs.get(job_id)
        return bool(current and current.get("status") == "cancelled")

    if payload.get("generation_type") in {"vari", "collage"}:
        from app_runtime.nano.run import set_cancel_check, set_pre_stage
        set_cancel_check(cancelled)  # a cancelled job stops starting new provider calls
        set_pre_stage(lambda image, preset, count, report: unclip_stage(job_id, payload, preset, count, report, cancelled))

    def put(value):
        if cancelled():
            return
        jobs[job_id] = value
        if cancelled():  # cancelled between the check and the write: put the cancelled state back
            jobs[job_id] = {**value, "status": "cancelled", "message": "Cancelled"}
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
        if payload.get("batch_id"):
            meta = {**meta, "batch_id": payload["batch_id"], "job_id": job_id}
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
        payload = materialize_source(payload)  # slim payloads carry a stored-source name instead of base64
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
    finally:
        try:
            if payload.get("generation_type") not in {"vari", "collage"}:  # CPU function: no GPU cost to account
                record_spend(job_id, time.monotonic() - started, gpu_hourly)
        except Exception as exc:  # accounting must never fail a finished job
            log.warning(f"spend accounting failed: {exc}")


@app.cls(
    image=gpu_image, gpu=["L4", "A10G"], cpu=2, memory=24576,  # 24 GB: blending two checkpoints holds two SDXL copies on the CPU
    volumes={"/models": models, "/outputs": outputs, "/archives": archives},
    # Per model pool (see MAX_GPU_JOBS above): one container per job, 10 per model.
    min_containers=0, max_containers=MAX_GPU_JOBS, scaledown_window=WORKER_IDLE_SECONDS,
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
            log.warning(f"preload of {self.model_id} failed: {exc}")

    @modal.method()
    def warm(self):
        """No-op: starting the container is the whole point (the checkpoint loads in preload())."""
        return True

    @modal.method()
    def run(self, job_id: str, payload: dict):
        try:
            return generate_job(job_id, payload)
        finally:
            release_slot(slots, job_id)
            try:
                dispatch.spawn()  # a slot is free: start the next waiting job
            except Exception as exc:
                log.warning(f"dispatch wake-up failed (the periodic sweep will catch up): {exc}")


@app.cls(
    image=gpu_image, gpu=["L4", "A10G"], cpu=2, memory=24576,  # metamorph also loads SDXL Base from a single file
    volumes={"/models": models, "/outputs": outputs, "/archives": archives},
    min_containers=0, max_containers=MAX_GPU_JOBS, scaledown_window=20,
    timeout=1200, retries=0,
)
class UnclipWorker:
    """Reimagine (SD 2.1 unCLIP). Own pool: its pipeline is not an SDXL checkpoint, so ImageWorker cannot load it.
    Jobs still go through `dispatch`, so the global GPU cap, FIFO queue and spend accounting apply."""

    @modal.enter()
    def preload(self):
        try:
            models.reload()
            from app_runtime.unclip import ensure_unclip_pipeline
            ensure_unclip_pipeline()
        except Exception as exc:  # run() reports the real error on the job
            log.warning(f"preload of unCLIP failed: {exc}")

    @modal.method()
    def run(self, job_id: str, payload: dict):
        try:
            return generate_job(job_id, payload)
        finally:
            release_slot(slots, job_id)
            try:
                dispatch.spawn()
            except Exception as exc:
                log.warning(f"dispatch wake-up failed (the periodic sweep will catch up): {exc}")


@app.function(
    image=nano_image, secrets=[nano_secret], volumes={"/models": models, "/outputs": outputs},
    cpu=1, memory=1024, min_containers=0, max_containers=20, scaledown_window=30, timeout=1500, retries=0,
)
def nano_job(job_id: str, payload: dict):
    """One Vari or Koláž job (provider API calls, no GPU). Same job record as the GPU jobs, so polling, the library and
    cancel work unchanged."""
    return generate_job(job_id, payload)


@app.function(image=nano_image, secrets=[nano_secret], cpu=0.25, memory=256, timeout=30, scaledown_window=60)
def nano_status():
    """Which models have their provider key (names only; the keys never leave this function)."""
    from app_runtime.nano.models import availability
    return availability(os.environ)


@app.function(
    image=base_image, max_containers=1, scaledown_window=20, cpu=0.25, memory=512, timeout=300,
    # Safety net if a wake-up is ever lost: the queue is also swept every two minutes.
    schedule=modal.Period(minutes=2),
)
def dispatch():
    from app_runtime.server import now_iso

    def spawn(job_id, payload):
        if payload.get("generation_type") == "reimagine":
            return UnclipWorker().run.spawn(job_id, payload).object_id
        return ImageWorker(model_id=payload["model_id"]).run.spawn(job_id, payload).object_id

    def is_cancelled(job_id):
        from app_runtime.cloud_server import is_job_cancelled
        return is_job_cancelled(jobs, job_id)

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
    image=base_image, volumes={"/outputs": outputs}, cpu=1, memory=2048, timeout=1800,
    schedule=modal.Cron("47 3 * * *"),
)
def backfill_thumbnails():
    """Create gallery thumbnails missing on the Volume (older outputs), so the gateway never builds them on demand."""
    from app_runtime.server import OUTPUTS_DIR, ensure_thumbnail, thumb_path
    outputs.reload()
    created = 0
    for path in sorted(OUTPUTS_DIR.iterdir()):
        if path.suffix.lower() not in {".png", ".webp"} or path.name.startswith("source_"):
            continue
        if thumb_path(path.name).is_file():
            continue
        try:
            if ensure_thumbnail(path.name):
                created += 1
        except Exception as exc:
            log.warning(f"thumbnail failed for {path.name}: {exc}")
    if created:
        outputs.commit()
    print(f"created {created} thumbnails")


@app.function(
    image=base_image, volumes={"/outputs": outputs}, cpu=0.25, memory=512, timeout=600,
    schedule=modal.Cron("17 3 * * *"),
)
def purge_deleted_images():
    """Daily: really remove images deleted more than RETENTION_DAYS ago, so the Volume stops growing."""
    from app_runtime.server import purge_deleted, purge_orphan_sources
    outputs.reload()
    import time
    current = time.strftime("%Y-%m", time.gmtime())
    for key in [key for key in spend.keys() if not key.startswith(current)]:  # keep only this month's totals
        release_slot(spend, key)
    removed = purge_deleted(int(os.environ.get("DELETED_RETENTION_DAYS", "30")))
    orphans = purge_orphan_sources(int(os.environ.get("ORPHAN_SOURCE_DAYS", "14")))
    if removed or orphans:
        outputs.commit()
    print(f"purged {removed} deleted images and {orphans} unreferenced sources")


@app.function(
    image=base_image.add_local_dir("frontend/dist", "/app/frontend/dist"),
    volumes={"/outputs": outputs, "/state": state, "/archives": archives},
    # Stays warm for 15 minutes after the last request: a cold start (image, Volume, record scan) takes ~20 s.
    min_containers=0, max_containers=1, scaledown_window=900,
    cpu=2, memory=2048,  # thumbnails of 2048 px PNGs are decoded here; 0.25 CPU made them take 20+ s
    # STUDIO_USERNAME / STUDIO_PASSWORD, optional MONTHLY_IMAGE_LIMIT and MAX_JOBS_PER_REQUEST.
    secrets=[modal.Secret.from_name("img2img-auth")],
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app(label="i")
def web():
    from app_runtime.cloud_server import (create_app, VolumeUsage, optional_int_env, optional_float_env,
                                         DEFAULT_MAX_JOBS_PER_REQUEST)
    # Missing credentials make create_app refuse to start rather than serve an open GPU.
    return create_app(
        jobs=jobs, usage=VolumeUsage("/state/usage.json", state), submit=spawn_job,
        refresh=outputs.reload, commit=outputs.commit, background_commit=True,
        cancel=cancel_call,
        username=os.environ.get("STUDIO_USERNAME"), password=os.environ.get("STUDIO_PASSWORD"),
        monthly_limit=optional_int_env("MONTHLY_IMAGE_LIMIT"),
        spend=month_spend, monthly_budget_usd=optional_float_env("MONTHLY_BUDGET_USD"),
        max_jobs_per_request=optional_int_env("MAX_JOBS_PER_REQUEST", DEFAULT_MAX_JOBS_PER_REQUEST),
        frontend_dir="/app/frontend/dist",
        nano_models=lambda: nano_status.remote(),
        warm=lambda model_id: ImageWorker(model_id=model_id).warm.spawn(),
    )
