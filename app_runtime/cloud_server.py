"""CPU-only web gateway. Polling and gallery access never allocate a GPU."""
import base64
import binascii
from datetime import datetime, UTC
import hmac
import logging
import hashlib
import os
import time
import io
import re
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

from app_runtime.core import get_options, get_config_item, parse_input, decode_image, check_job_size
from app_runtime.server import (api_atelier_photo, api_atelier_photos, api_options, OUTPUTS_DIR, THUMBS_DIR, api_library_save, load_deleted_ids,
                                load_history_items, api_library_delete, api_library_order, load_library_items, now_iso,
                                ensure_thumbnail, is_safe_filename)

VOLUME_REFRESH_INTERVAL = float(os.getenv("VOLUME_REFRESH_SECONDS", "2.0"))


class VolumeUsage:
    """Monthly reservations must outlive Modal Dict's seven-day inactivity TTL."""
    def __init__(self, path, volume):
        self.path = Path(path)
        self.volume = volume

    def _read(self):
        import json
        self.volume.reload()
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def get(self, key, default=0):
        return self._read().get(key, default)

    def __setitem__(self, key, value):
        import json
        records = self._read()
        records[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(records))
        temporary.replace(self.path)
        self.volume.commit()


# Frontend transport chunks are at most 8 studies x 7 checkpoints (56 jobs).
DEFAULT_MAX_JOBS_PER_REQUEST = 64


MAX_EXPORT_PIXELS = 36_000_000
INTERACTIVE_REQUEST_JOBS = 4
RUNNING_JOB_TIMEOUT_SECONDS = 1800
QUEUED_JOB_TIMEOUT_SECONDS = 3 * 3600  # large batches legitimately queue for a long while; this only catches lost jobs
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 600
LOGIN_LOCKOUT_SECONDS = 300


def optional_float_env(name, default=None):
    """Positive number from the environment; unset or empty means `default`."""
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    number = float(value)
    if number <= 0:
        raise ValueError(f"{name} must be positive")
    return number


def optional_int_env(name, default=None):
    """Positive integer from the environment; unset or empty means `default`."""
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    number = int(value)
    if number < 1:
        raise ValueError(f"{name} must be a positive integer")
    return number


def create_app(*, jobs, usage, submit, refresh, commit, username, password,
               monthly_limit=None, max_jobs_per_request=DEFAULT_MAX_JOBS_PER_REQUEST, cancel=None,
               frontend_dir=None, auth_enabled=True, spend=None, monthly_budget_usd=None):
    if auth_enabled and (not username or not password):
        raise ValueError("Application credentials are required when authentication is enabled")
    app = FastAPI(title="SDXL Modal Studio", docs_url=None, redoc_url=None)
    lock = threading.Lock()
    thumbnail_lock = threading.Lock()
    status_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="job-status")
    reload_lock = threading.Lock()  # one Volume reload at a time; asset reads never wait on `lock`
    refresh_state = {"at": 0.0}

    def refresh_cached(*, force=False):
        """Volume reload is a network call; collapse bursts of polling into one."""
        now = time.monotonic()
        if not force and now - refresh_state["at"] < VOLUME_REFRESH_INTERVAL:
            return
        with reload_lock:
            # Re-check: a burst of requests all passed the cheap check above while one of them reloaded.
            if not force and time.monotonic() - refresh_state["at"] < VOLUME_REFRESH_INTERVAL:
                return
            try:
                refresh()
            except RuntimeError as exc:
                # Modal refuses a reload while another request still holds a file open; the next call retries.
                if "open files" not in str(exc):
                    raise
                return
            refresh_state["at"] = time.monotonic()

    def wait_for_file(find):
        """A fresh worker output can take a moment to become visible here: reload and retry briefly."""
        found = find()
        for _ in range(3):
            if found is not None:
                break
            refresh_cached(force=True)
            found = find()
            if found is None:
                time.sleep(0.4)
        return found

    # Dedicated, domain-separated signing key: the login password itself never signs anything.
    session_key = hmac.new((password or "").encode(), b"mulen-art/session/v1", hashlib.sha256).digest()

    def sign_session(timestamp):
        # The username is part of the signed message, so a cookie is bound to the account it was issued for.
        return hmac.new(session_key, f"{username}\n{timestamp}".encode(), hashlib.sha256).hexdigest()

    def session_valid(token):
        try:
            timestamp, signature = token.split(".", 1)
            age = time.time() - int(timestamp)
            return 0 <= age < 30 * 86400 and hmac.compare_digest(signature, sign_session(timestamp))
        except (ValueError, AttributeError):
            return False

    # Best-effort brute-force guard (the gateway is a single container, so memory is enough).
    failures = {}
    failures_lock = threading.Lock()

    def client_ip(request):
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        return forwarded or (request.client.host if request.client else "unknown")

    def lockout_remaining(ip):
        with failures_lock:
            entry = failures.get(ip)
            return max(0, int(entry["blocked_until"] - time.monotonic())) if entry else 0

    def record_failure(ip):
        now = time.monotonic()
        with failures_lock:
            if len(failures) > 2000:  # bound memory under a scan
                for key in [k for k, v in failures.items() if now - v["since"] > LOGIN_WINDOW_SECONDS and v["blocked_until"] < now]:
                    del failures[key]
            entry = failures.get(ip)
            if not entry or now - entry["since"] > LOGIN_WINDOW_SECONDS:
                entry = failures[ip] = {"count": 0, "since": now, "blocked_until": 0.0}
            entry["count"] += 1
            if entry["count"] >= LOGIN_MAX_FAILURES:
                entry["blocked_until"] = now + LOGIN_LOCKOUT_SECONDS
                entry["count"] = 0
                entry["since"] = now

    def record_success(ip):
        with failures_lock:
            failures.pop(ip, None)

    def locked_out_response(remaining):
        return Response("Too many failed sign-in attempts. Try again later.", status_code=429,
                        headers={"Retry-After": str(remaining), "Cache-Control": "no-store"})

    @app.get("/login", response_class=HTMLResponse)
    def login_page():
        return HTMLResponse(LOGIN_HTML, headers={"Cache-Control": "no-store"})

    @app.post("/login")
    async def login(request: Request):
        from urllib.parse import parse_qs
        raw = await request.body()
        if len(raw) > 4096:
            raise HTTPException(413, "Login request too large")
        ip = client_ip(request)
        remaining = lockout_remaining(ip)
        if remaining:
            return locked_out_response(remaining)
        fields = parse_qs(raw.decode(errors="replace"))
        user = fields.get("username", [""])[0]
        secret = fields.get("password", [""])[0]
        if not (hmac.compare_digest(user.encode(), username.encode()) and
                hmac.compare_digest(secret.encode(), password.encode())):
            record_failure(ip)
            return HTMLResponse(LOGIN_HTML.replace("Sign in to your studio", "Incorrect username or password"), status_code=401)
        record_success(ip)
        timestamp = str(int(time.time()))
        response = RedirectResponse("/", status_code=303)
        response.set_cookie("studio_session", f"{timestamp}.{sign_session(timestamp)}", secure=True,
                            httponly=True, samesite="strict", max_age=30 * 86400)
        return response

    @app.post("/logout")
    def logout():
        """End the session and tell the browser to drop everything cached for this origin."""
        response = Response(status_code=204, headers={"Cache-Control": "no-store"})
        response.delete_cookie("studio_session", secure=True, httponly=True, samesite="strict")
        # "storage" covers IndexedDB and Cache Storage (the gallery snapshot and the media service worker).
        response.headers["Clear-Site-Data"] = '"cache", "storage"'
        return response

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        if not auth_enabled or request.url.path in {"/login", "/logout", "/health"}:
            return await call_next(request)
        ip = client_ip(request)
        remaining = lockout_remaining(ip)
        if remaining:
            return locked_out_response(remaining)
        authorized = session_valid(request.cookies.get("studio_session", ""))
        presented_basic = False
        try:
            scheme, value = request.headers.get("authorization", "").split(" ", 1)
            user, secret = base64.b64decode(value, validate=True).decode().split(":", 1)
            presented_basic = scheme.lower() == "basic"
            authorized = authorized or (presented_basic and
                          hmac.compare_digest(user.encode(), username.encode()) and
                          hmac.compare_digest(secret.encode(), password.encode()))
        except (ValueError, UnicodeError, binascii.Error):
            pass
        if not authorized and presented_basic:
            record_failure(ip)  # only wrong credentials count, not a browser that has none yet
        if not authorized:
            if "text/html" in request.headers.get("accept", ""):
                return RedirectResponse("/login", status_code=303)
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Img2Img Studio", charset="UTF-8"'})
        response = await call_next(request)
        # Immutable image/thumbnail responses keep their own long-lived caching.
        if "cache-control" not in {key.lower() for key in response.headers}:
            response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/health")
    def health():
        return {"ok": True, "provider": "modal", "demo_mode": False}

    @app.middleware("http")
    async def fresh_frontend_entry(request: Request, call_next):
        entry = request.url.path in {"/", "/index.html"}
        if entry:
            # StaticFiles ETags depend on size/mtime. Image builds can preserve those
            # across changed, equal-length asset names and incorrectly answer 304.
            request.scope["headers"] = [(key, value) for key, value in request.scope["headers"]
                                        if key.lower() not in {b"if-none-match", b"if-modified-since"}]
        response = await call_next(request)
        if entry or request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if entry:
            for header in ("etag", "last-modified"):
                if header in response.headers:
                    del response.headers[header]
        return response

    # The read-only catalogue endpoints are identical to the local server's: one implementation, registered here.
    app.get("/api/options")(api_options)
    app.get("/api/atelier/photos")(api_atelier_photos)
    app.get("/atelier-photo/{photo_id}")(api_atelier_photo)

    def validate_payload(payload, verify_image=True):
        from dataclasses import asdict
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        parsed = parse_input(payload)
        if parsed.generation_type == "img2img" and verify_image:
            image_data = base64.b64decode(parsed.image_base64.split(",")[-1], validate=True)
            with Image.open(io.BytesIO(image_data)) as image:
                image.verify()
        result = asdict(parsed)
        result["source_name"] = str(payload.get("source_name", "Input image"))[:120]
        return result

    async def read_payload(request, maximum):
        if not request.headers.get("content-type", "").startswith("application/json"):
            raise HTTPException(415, "Expected application/json")
        raw = await request.body()
        if len(raw) > maximum:
            raise HTTPException(413, "Input images are too large for one batch.")
        import json
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise HTTPException(422, "Invalid JSON") from exc

    def enqueue(payloads):
        month = datetime.now(UTC).strftime("%Y-%m")
        requested = sum(payload["num_images"] for payload in payloads)
        if max_jobs_per_request is not None and len(payloads) > max_jobs_per_request:
            raise HTTPException(413, f"Too many jobs in one request ({len(payloads)} > {max_jobs_per_request}); send smaller batches.")
        submitted, errors = [], []
        # The lock covers only the usage ledger. Writing sources, committing the Volume and the (up to hundreds
        # of) spawn calls used to run under it and stalled every other write request.
        with lock:
            used = usage.get(month, 0)
            if monthly_limit is not None and used + requested > monthly_limit:
                raise HTTPException(429, f"Monthly safety limit reached ({monthly_limit} images).")
            if monthly_budget_usd is not None and spend is not None and spend(month) >= monthly_budget_usd:
                raise HTTPException(429, f"Monthly GPU budget reached (${monthly_budget_usd:.2f}).")
            usage[month] = used + requested

        def refund(images):
            if images > 0:
                with lock:
                    usage[month] = max(0, usage.get(month, 0) - images)

        try:
            # Zdroj uchováme pro porovnání i po obnovení stránky; žádná galerie složených vstupů.
            refresh_cached()
            has_sources = False
            for payload in payloads:
                if payload["generation_type"] == "atelier":
                    payload["source_url"] = None
                    continue
                has_sources = True
                filename = payload.get("source_file")
                if not filename:
                    digest = hashlib.sha256(payload["image_base64"].encode()).hexdigest()
                    filename = payload["source_file"] = f"source_{digest}.png"
                path = OUTPUTS_DIR / filename
                if not path.exists():
                    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
                    decode_image(payload["image_base64"]).save(path, format="PNG")
                payload["source_url"] = f"/library/{filename}"
                payload["image_base64"] = ""  # the worker loads the stored file by name (smaller spawn arguments)
            # Also confirm reused files: a previous failed commit may have left
            # a source present locally without making it durable.
            if has_sources:
                commit()
        except BaseException:
            refund(requested)  # nothing was submitted: give the reservation back
            raise
        # Small, interactive requests start before the tail of a large batch waiting in the queue.
        priority = 0 if len(payloads) <= INTERACTIVE_REQUEST_JOBS else 1
        failed_images = 0
        for index, payload in enumerate(payloads):
            payload["queue_priority"] = priority
            job_id = uuid.uuid4().hex
            jobs[job_id] = {
                "id": job_id, "status": "queued", "progress": 0,
                "message": "Waiting for cloud GPU (first start can take longer)",
                "source_name": payload["source_name"], "source_url": payload["source_url"], "expected_images": payload["num_images"],
                "generation_type": payload["generation_type"], "model_id": payload["model_id"],
                "logs": [], "result": None, "error": None,
                "created_at": now_iso(), "updated_at": now_iso(),
            }
            try:
                call_id = submit(job_id, payload)
                if call_id:
                    jobs[f"call:{job_id}"] = call_id
                submitted.append({"job_id": job_id, "source_name": payload["source_name"],
                                  "source_index": payload.get("source_index", index), "variant_index": payload.get("variant_index", 0),
                                  "expected_images": payload["num_images"]})
                submitted[-1].update(generation_type=payload["generation_type"], model_id=payload["model_id"])
            except Exception:
                logging.getLogger("studio").exception("Could not submit job %s", job_id)
                failed_images += payload["num_images"]
                jobs.pop(job_id, None)
                errors.append(f"Could not submit {payload['source_name']}")
        refund(failed_images)
        if not submitted:
            raise HTTPException(503, "Cloud GPU submission failed; please try again.")
        return {"jobs": submitted, "errors": errors}

    @app.post("/api/generate")
    async def generate(request: Request):
        payload = await read_payload(request, 24 * 1024 * 1024)
        try:
            payload = await run_in_threadpool(validate_payload, payload)  # decodes and verifies the image
            check_job_size(payload["num_images"])
        except Exception as exc:
            raise HTTPException(422, f"Invalid generation input: {exc}") from exc
        result = await run_in_threadpool(enqueue, [payload])
        return {"job_id": result["jobs"][0]["job_id"], "status": "queued"}

    def plan_atelier(data):
        """Validate an Atelier request and plan its studies. Runs in a worker thread: it touches manifests and files."""
        import secrets
        from .atelier import subject_for
        if not isinstance(data, dict) or not isinstance(data.get("settings", {}), dict):
            raise ValueError("Invalid atelier request")
        settings = data.get("settings", {})
        ratio_mode = settings.get("atelier_ratio", "fixed")
        if ratio_mode not in {"fixed", "random"}:
            raise ValueError("Unknown aspect ratio mode")
        models = data.get("model_ids")
        if not isinstance(models, list) or not models or any(not isinstance(item, str) for item in models):
            raise ValueError("Select artist checkpoints")
        models = list(dict.fromkeys(models))
        count = data.get("count", 1)
        # Transport chunks only; the frontend can enqueue an unlimited number of chunks.
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 8:
            raise ValueError("At most eight studies per transport request")
        # Validate the seed before resolving its random sentinel.
        first = parse_input({**settings, "generation_type": "atelier", "model_id": models[0], "lora_id": "none", "num_images": 1})
        if first.atelier_mode == "archive":
            from .archives import pick_reference, reference_for
            reference_for(first.atelier_archive, 0)  # full integrity check once per request
        if first.atelier_mode == "photo" and first.atelier_photo_source == "library":
            from .user_photos import photo_for
            photo_for(first.atelier_photo_collection, 0, first.atelier_photo_id)
        seed = secrets.randbits(32) if first.seed == -1 else first.seed
        payloads = []
        for index in range(count):
            for model_id in models:
                # Stable per-model streams survive transport chunking and model reordering.
                model_offset = int.from_bytes(hashlib.sha256(model_id.encode()).digest()[:4], "big")
                variant_seed = (seed + index + model_offset) % 2**32
                title = "Volná studie bez námětu" if first.atelier_mode == "noise" else subject_for(variant_seed, first.atelier_theme)[1]
                if first.atelier_mode == "archive":
                    archive, reference = pick_reference(first.atelier_archive, variant_seed)
                    title = archive["name"] + " · " + reference["filename"]
                if first.atelier_mode == "photo" and first.atelier_photo_source == "library":
                    from .user_photos import pick_photo
                    collection, photo_item = pick_photo(first.atelier_photo_collection, variant_seed, first.atelier_photo_id)
                    title = photo_item["filename"]
                dimensions = {}
                if ratio_mode == "random":
                    import random
                    width, height = random.Random(f"atelier-ratio:{variant_seed}").choice([(1024,1024), (832,1216), (1216,832), (896,1152), (1152,896)])
                    dimensions = {"width": width, "height": height}
                payload = validate_payload({**settings, **dimensions, "generation_type": "atelier", "model_id": model_id,
                    "lora_id": "none", "num_images": 1, "seed": variant_seed, "source_name": title})
                if first.atelier_mode == "photo" and first.atelier_photo_source == "library":
                    payload.update(atelier_photo_collection=first.atelier_photo_collection,
                                   atelier_photo_id=first.atelier_photo_id)
                payload.update(source_index=index, variant_index=index)
                payloads.append(payload)
        return payloads

    @app.post("/api/atelier-batch")
    async def atelier_batch(request: Request):
        data = await read_payload(request, 64 * 1024)
        try:
            payloads = await run_in_threadpool(plan_atelier, data)
        except Exception as exc:
            raise HTTPException(422, f"Invalid atelier request: {exc}") from exc
        return await run_in_threadpool(enqueue, payloads)

    def store_source(image_base64):
        digest = hashlib.sha256(image_base64.encode()).hexdigest()
        filename = f"source_{digest}.png"
        path = OUTPUTS_DIR / filename
        if not path.exists():
            OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
            decode_image(image_base64).save(path, format="PNG")
        return digest, filename

    @app.post("/api/sources")
    async def upload_source(request: Request):
        """Upload an input once; later batches reference it by id instead of resending the bytes."""
        data = await read_payload(request, 24 * 1024 * 1024)
        try:
            if not isinstance(data, dict) or not isinstance(data.get("image_base64"), str):
                raise ValueError("image_base64 is required")
            digest, _ = await run_in_threadpool(store_source, data["image_base64"])
            await run_in_threadpool(commit)
        except Exception as exc:
            raise HTTPException(422, f"Invalid source image: {exc}") from exc
        return {"source_id": digest}

    def find_source(source_id):
        if not isinstance(source_id, str) or not re.fullmatch(r"[0-9a-f]{64}", source_id):
            raise ValueError("Invalid source id")
        filename = f"source_{source_id}.png"
        path = OUTPUTS_DIR / filename
        if not path.is_file():
            refresh_cached(force=True)
        if not path.is_file():
            raise ValueError("Uploaded source not found; upload it again")
        return filename

    @app.post("/api/generate-batch")
    async def generate_batch(request: Request):
        data = await read_payload(request, 64 * 1024 * 1024)
        try:
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            inputs, settings = data.get("inputs"), data.get("settings", {})
            if not isinstance(inputs, list) or not inputs:
                raise ValueError("Select at least one separate input image")
            if not isinstance(settings, dict):
                raise ValueError("Invalid settings")
        except Exception as exc:
            raise HTTPException(422, f"Invalid batch input: {exc}") from exc
        # Reject oversized batches before decoding every image.
        if max_jobs_per_request is not None and len(inputs) > max_jobs_per_request:
            raise HTTPException(413, f"Too many inputs in one request ({len(inputs)} > {max_jobs_per_request}); send smaller batches.")
        def build_payloads():
            built = []
            for index, item in enumerate(inputs):
                image_base64, source_file = item.get("image_base64"), None
                if image_base64 is None:
                    # Our own stored PNG: it was decoded and verified when it was uploaded, and the worker reads
                    # it from the Volume by name, so it is not re-encoded to base64 and re-decoded here.
                    source_file = find_source(item.get("source_id"))
                payload = validate_payload({**settings, "image_base64": image_base64 or "stored",
                                           "source_name": item.get("name", f"Input {index + 1}")},
                                           verify_image=source_file is None)
                if source_file:
                    payload["source_file"] = source_file
                    payload["image_base64"] = ""
                built.append(payload)
            return built
        try:
            # Volume reads, base64 and PIL verification must not run on the event loop.
            payloads = await run_in_threadpool(build_payloads)
        except Exception as exc:
            raise HTTPException(422, f"Invalid batch input: {exc}") from exc
        # Refuse an absurd count before it is expanded into a list of jobs (the cap in enqueue comes too late).
        if max_jobs_per_request is not None and sum(item["num_images"] for item in payloads) > max_jobs_per_request:
            raise HTTPException(413, f"Too many images in one request ({sum(item['num_images'] for item in payloads)} > {max_jobs_per_request}); send smaller batches.")
        # Každá varianta má vlastní úlohu, takže velká dávka nepřekročí čas jednoho GPU workeru.
        expanded = []
        for source_index, payload in enumerate(payloads):
            for variant_index in range(payload["num_images"]):
                expanded.append({**payload, "seed": -1 if payload["seed"] == -1 else (payload["seed"] + variant_index) % 2**32, "num_images": 1, "source_index": source_index, "variant_index": variant_index})
        return await run_in_threadpool(enqueue, expanded)

    def with_timeout(job_id, job):
        """Report a job that stopped making progress as failed - and store that, so it stays failed."""
        limit = {"running": RUNNING_JOB_TIMEOUT_SECONDS, "queued": QUEUED_JOB_TIMEOUT_SECONDS}.get(job["status"])
        if limit is None:
            return job
        if not job.get("updated_at"):
            return job
        age = (datetime.now(UTC) - datetime.fromisoformat(job["updated_at"])).total_seconds()
        if age <= limit:
            return job
        detail = "Cloud job timed out. Try again." if job["status"] == "running" else "The job never started. Try again."
        expired = {**job, "status": "failed", "message": "Failed", "error": {"detail": detail}}
        try:
            jobs[job_id] = expired
        except Exception:
            logging.getLogger("studio").warning("Could not store the timeout of job %s", job_id, exc_info=True)
        return expired

    @app.get("/api/jobs")
    def bulk_status(ids: str = ""):
        """One request instead of one poll per job; unknown or expired ids map to null."""
        wanted = [item for item in dict.fromkeys(ids.split(",")) if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", item)]
        if not wanted or len(wanted) > 200:
            raise HTTPException(422, "Pass between 1 and 200 job ids.")
        # Each lookup is a network round trip to the shared Dict: do them concurrently, not 200 in a row.
        records = list(status_pool.map(jobs.get, wanted))
        return {"jobs": {job_id: None if job is None else with_timeout(job_id, job) for job_id, job in zip(wanted, records)}}

    @app.get("/api/jobs/{job_id}")
    def status(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found or expired.")
        return with_timeout(job_id, job)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        if cancel is None:
            raise HTTPException(501, "Cancellation is not available.")
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found or expired.")
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        call_id = jobs.get(f"call:{job_id}")
        if call_id:
            try:
                cancel(call_id)
            except Exception as exc:
                raise HTTPException(502, "Could not cancel the cloud job.") from exc
        # Flag first, record second: a worker that re-checks the flag after each write restores this state.
        jobs[f"cancelled:{job_id}"] = True
        # Images already saved by the worker stay in the library.
        job = {**job, "status": "cancelled", "message": "Cancelled", "updated_at": now_iso()}
        jobs[job_id] = job
        return job

    @app.get("/api/usage")
    def get_usage():
        month = datetime.now(UTC).strftime("%Y-%m")
        with lock:
            reserved = usage.get(month, 0)
        # The spend sum walks a shared Dict over the network; it must not wait behind (or hold) the write lock.
        return {"month": month, "reserved_images": reserved, "limit": monthly_limit,
                "spent_usd": round(spend(month), 2) if spend is not None else None,
                "budget_usd": monthly_budget_usd}

    @app.get("/api/history")
    def history():
        # Read-only: records are replaced atomically, so listing needs no write lock. Holding it here made
        # /api/usage and every other request wait behind a slow cold listing (50 s on a cold container).
        refresh_cached()
        return {"items": load_history_items(), "deleted_ids": load_deleted_ids()}

    @app.post("/api/library/{item_id}")
    def save_to_library(item_id: str):
        with lock:
            refresh_cached(force=True)
            result = api_library_save(item_id)
            commit()
            return result

    @app.get("/api/library")
    def library():
        refresh_cached()
        return {"items": load_library_items()}

    def asset_response(path, media_type, request: Request):
        stat = path.stat()
        etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        headers = {"Cache-Control": "private, max-age=31536000, immutable", "ETag": etag}
        # Browsers revalidate on reload; a 304 saves re-sending megabytes through the gateway.
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        if request.method == "HEAD":
            return Response(status_code=200, media_type=media_type, headers={**headers, "Content-Length": str(stat.st_size)})
        return FileResponse(path, media_type=media_type, headers=headers)

    @app.get("/library/{filename}")
    @app.head("/library/{filename}")
    def asset(filename: str, request: Request):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.(png|webp)", filename):
            raise HTTPException(404, "Image not found.")
        path = OUTPUTS_DIR / filename
        if not wait_for_file(lambda: path if path.is_file() else None):
            raise HTTPException(404, "Image not found.")
        return asset_response(path, "image/png" if filename.endswith(".png") else "image/webp", request)

    @app.get("/thumb/{filename}")
    @app.head("/thumb/{filename}")
    def thumbnail(filename: str, request: Request):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.(webp|png|jpg|jpeg)", filename):
            raise HTTPException(404, "Thumbnail not found.")
        target = THUMBS_DIR / filename
        if target.is_file():
            return asset_response(target, "image/webp", request)
        stem = Path(filename).stem
        source = wait_for_file(lambda: next(
            (p for p in OUTPUTS_DIR.glob(f"{stem}.*") if p.suffix.lower() in {".png", ".webp"}), None))
        if source is None:
            raise HTTPException(404, "Thumbnail not found.")
        with thumbnail_lock:  # concurrent requests for the same image decode it only once
            target = ensure_thumbnail(source.name)
        if target is None:
            raise HTTPException(404, "Thumbnail not found.")
        try:
            commit()  # without this the thumbnail vanished with the container and was rebuilt on every cold start
        except Exception:
            logging.getLogger("studio").warning("Could not persist thumbnail %s", target.name, exc_info=True)
        return asset_response(target, "image/webp", request)

    @app.get("/api/library/{item_id}/export")
    def export_print(item_id: str, scale: int = 2):
        """Print-ready PNG: a separate Lanczos upscale of a finished output, tagged 300 dpi."""
        import json
        if not re.fullmatch(r"[A-Za-z0-9_-]+", item_id) or scale not in (2, 3, 4):
            raise HTTPException(404, "Image not found.")
        record_path = OUTPUTS_DIR / f"{item_id}.json"
        # A freshly generated image may exist only in another container's view of the Volume until we reload.
        wait_for_file(lambda: record_path if record_path.is_file() else None)
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if not is_safe_filename(record.get("filename")):
                raise ValueError("unsafe filename")
            path = OUTPUTS_DIR / record["filename"]
            wait_for_file(lambda: path if path.is_file() else None)
            source = Image.open(path)
        except (OSError, ValueError, KeyError):
            raise HTTPException(404, "Image not found.")
        with source:
            width, height = source.width * scale, source.height * scale
            if width * height > MAX_EXPORT_PIXELS:  # the gateway has 512 MB of RAM
                raise HTTPException(413, "Export would be too large; try a smaller scale.")
            upscaled = source.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        upscaled.save(buffer, format="PNG", dpi=(300, 300))
        return Response(buffer.getvalue(), media_type="image/png",
                        headers={"Content-Disposition": f'attachment; filename="{item_id}_print_{scale}x.png"'})

    @app.delete("/api/library/{item_id}")
    def delete(item_id: str):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", item_id):
            raise HTTPException(404, "Image not found.")
        with lock:
            refresh_cached()
            result = api_library_delete(item_id)
            commit()
            return result

    @app.put("/api/library/order")
    def reorder_library(payload: dict):
        with lock:
            refresh_cached()
            result = api_library_order(payload.get("ids", []))
            commit()
            return result

    if frontend_dir and Path(frontend_dir).is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    return app


LOGIN_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>IMG2IMG · Sign in</title>
<style>body{margin:0;background:#111214;color:#eee;font:15px system-ui;display:grid;place-items:center;min-height:100vh}
form{width:min(320px,80vw);padding:40px;background:#1b1c1f;border:1px solid #333;border-radius:12px}
h1{letter-spacing:.15em;font-size:26px}p{color:#aaa;margin-bottom:28px}label{display:block;margin-top:18px}
input,button{box-sizing:border-box;width:100%;padding:12px;border-radius:6px;border:1px solid #444;background:#111;color:#eee;margin-top:8px;font:inherit}
button{margin-top:28px;background:#d8eb9d;color:#161b0c;border:0;cursor:pointer;font-weight:600}</style></head>
<body><form method="post" action="/login"><h1>IMG2IMG</h1><p>Sign in to your studio</p>
<label>Username<input name="username" autocomplete="username" required></label>
<label>Password<input name="password" type="password" autocomplete="current-password" required></label>
<button type="submit">Sign in</button></form></body></html>"""
