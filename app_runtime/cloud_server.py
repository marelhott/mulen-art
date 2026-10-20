"""CPU-only web gateway. Polling and gallery access never allocate a GPU."""
import base64
import binascii
from datetime import datetime, UTC
import hmac
import hashlib
import time
import io
import re
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from app_runtime.core import get_options, get_config_item, parse_input, decode_image
from app_runtime.server import OUTPUTS_DIR, api_library_save, load_deleted_ids, load_history_items, api_library_delete, api_library_order, load_library_items, now_iso


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


def create_app(*, jobs, usage, submit, refresh, commit, username, password,
               monthly_limit=None, frontend_dir=None, auth_enabled=True):
    if auth_enabled and (not username or not password):
        raise ValueError("Application credentials are required when authentication is enabled")
    app = FastAPI(title="SDXL Modal Studio", docs_url=None, redoc_url=None)
    lock = threading.Lock()

    def session_valid(token):
        try:
            timestamp, signature = token.split(".", 1)
            age = time.time() - int(timestamp)
            expected = hmac.new(password.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
            return 0 <= age < 30 * 86400 and hmac.compare_digest(signature, expected)
        except (ValueError, AttributeError):
            return False

    @app.get("/login", response_class=HTMLResponse)
    def login_page():
        return HTMLResponse(LOGIN_HTML, headers={"Cache-Control": "no-store"})

    @app.post("/login")
    async def login(request: Request):
        from urllib.parse import parse_qs
        raw = await request.body()
        if len(raw) > 4096:
            raise HTTPException(413, "Login request too large")
        fields = parse_qs(raw.decode(errors="replace"))
        user = fields.get("username", [""])[0]
        secret = fields.get("password", [""])[0]
        if not (hmac.compare_digest(user.encode(), username.encode()) and
                hmac.compare_digest(secret.encode(), password.encode())):
            return HTMLResponse(LOGIN_HTML.replace("Sign in to your studio", "Incorrect username or password"), status_code=401)
        timestamp = str(int(time.time()))
        signature = hmac.new(password.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
        response = RedirectResponse("/", status_code=303)
        response.set_cookie("studio_session", f"{timestamp}.{signature}", secure=True,
                            httponly=True, samesite="strict", max_age=30 * 86400)
        return response

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        if not auth_enabled or request.url.path == "/login":
            return await call_next(request)
        authorized = session_valid(request.cookies.get("studio_session", ""))
        try:
            scheme, value = request.headers.get("authorization", "").split(" ", 1)
            user, secret = base64.b64decode(value, validate=True).decode().split(":", 1)
            authorized = authorized or (scheme.lower() == "basic" and
                          hmac.compare_digest(user.encode(), username.encode()) and
                          hmac.compare_digest(secret.encode(), password.encode()))
        except (ValueError, UnicodeError, binascii.Error):
            pass
        if not authorized:
            if "text/html" in request.headers.get("accept", ""):
                return RedirectResponse("/login", status_code=303)
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Img2Img Studio", charset="UTF-8"'})
        response = await call_next(request)
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

    @app.get("/api/options")
    def options():
        from .archives import archive_options
        refresh()
        return {**get_options(), "archives": archive_options()}

    def validate_payload(payload):
        from dataclasses import asdict
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        parsed = parse_input(payload)
        if parsed.generation_type == "img2img":
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
        submitted, errors = [], []
        with lock:
            used = usage.get(month, 0)
            if monthly_limit is not None and used + requested > monthly_limit:
                raise HTTPException(429, f"Monthly safety limit reached ({monthly_limit} images).")
            # Zdroj uchováme pro porovnání i po obnovení stránky; žádná galerie složených vstupů.
            refresh()
            for payload in payloads:
                if payload["generation_type"] == "atelier":
                    payload["source_url"] = None
                    continue
                digest = hashlib.sha256(payload["image_base64"].encode()).hexdigest()
                filename = f"source_{digest}.png"
                path = OUTPUTS_DIR / filename
                if not path.exists():
                    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
                    decode_image(payload["image_base64"]).save(path, format="PNG")
                payload["source_url"] = f"/library/{filename}"
            commit()
            usage[month] = used + requested
            for index, payload in enumerate(payloads):
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
                    submit(job_id, payload)
                    submitted.append({"job_id": job_id, "source_name": payload["source_name"],
                                      "source_index": payload.get("source_index", index), "variant_index": payload.get("variant_index", 0),
                                      "expected_images": payload["num_images"]})
                    submitted[-1].update(generation_type=payload["generation_type"], model_id=payload["model_id"])
                except Exception:
                    requested -= payload["num_images"]
                    jobs.pop(job_id, None)
                    errors.append(f"Could not submit {payload['source_name']}")
            if errors:
                usage[month] = used + requested
        if not submitted:
            raise HTTPException(503, "Cloud GPU submission failed; please try again.")
        return {"jobs": submitted, "errors": errors}

    @app.post("/api/generate")
    async def generate(request: Request):
        payload = await read_payload(request, 24 * 1024 * 1024)
        try:
            payload = validate_payload(payload)
        except Exception as exc:
            raise HTTPException(422, f"Invalid generation input: {exc}") from exc
        result = enqueue([payload])
        return {"job_id": result["jobs"][0]["job_id"], "status": "queued"}

    @app.post("/api/atelier-batch")
    async def atelier_batch(request: Request):
        import secrets
        from .atelier import subject_for
        data = await read_payload(request, 64 * 1024)
        try:
            if not isinstance(data, dict) or not isinstance(data.get("settings", {}), dict):
                raise ValueError("Invalid atelier request")
            settings = data.get("settings", {})
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
                from .archives import reference_for
                reference_for(first.atelier_archive, 0)
            seed = secrets.randbits(32) if first.seed == -1 else first.seed
            payloads = []
            for index in range(count):
                variant_seed = (seed + index) % 2**32
                title = "Volná studie bez námětu" if first.atelier_mode == "noise" else subject_for(variant_seed, first.atelier_theme)[1]
                if first.atelier_mode == "archive":
                    archive, reference, _ = reference_for(first.atelier_archive, variant_seed)
                    title = archive["name"] + " · " + reference["filename"]
                for model_id in models:
                    payload = validate_payload({**settings, "generation_type": "atelier", "model_id": model_id,
                        "lora_id": "none", "num_images": 1, "seed": variant_seed, "source_name": title})
                    payload.update(source_index=index, variant_index=index)
                    payloads.append(payload)
        except Exception as exc:
            raise HTTPException(422, f"Invalid atelier request: {exc}") from exc
        return enqueue(payloads)

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
            payloads = [validate_payload({**settings, "image_base64": item["image_base64"],
                                         "source_name": item.get("name", f"Input {index + 1}")})
                        for index, item in enumerate(inputs)]
        except Exception as exc:
            raise HTTPException(422, f"Invalid batch input: {exc}") from exc
        # Každá varianta má vlastní úlohu, takže velká dávka nepřekročí čas jednoho GPU workeru.
        expanded = []
        for source_index, payload in enumerate(payloads):
            for variant_index in range(payload["num_images"]):
                expanded.append({**payload, "seed": -1 if payload["seed"] == -1 else (payload["seed"] + variant_index) % 2**32, "num_images": 1, "source_index": source_index, "variant_index": variant_index})
        return enqueue(expanded)

    @app.get("/api/jobs/{job_id}")
    def status(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found or expired.")
        if job["status"] == "running":
            age = (datetime.now(UTC) - datetime.fromisoformat(job["updated_at"])).total_seconds()
            if age > 1800:
                return {**job, "status": "failed", "error": {"detail": "Cloud job timed out. Try again."}}
        return job

    @app.get("/api/usage")
    def get_usage():
        month = datetime.now(UTC).strftime("%Y-%m")
        with lock:
            return {"month": month, "reserved_images": usage.get(month, 0), "limit": monthly_limit}

    @app.get("/api/history")
    def history():
        with lock:
            refresh()
            return {"items": load_history_items(), "deleted_ids": load_deleted_ids()}

    @app.post("/api/library/{item_id}")
    def save_to_library(item_id: str):
        with lock:
            refresh()
            result = api_library_save(item_id)
            commit()
            return result

    @app.get("/api/library")
    def library():
        with lock:
            refresh()
            return {"items": load_library_items()}

    @app.get("/library/{filename}")
    def asset(filename: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.(png|webp)", filename):
            raise HTTPException(404, "Image not found.")
        with lock:
            refresh()
            path = OUTPUTS_DIR / filename
            if not path.is_file():
                raise HTTPException(404, "Image not found.")
            # Read while holding the volume lock (FileResponse would read after releasing it).
            return Response(path.read_bytes(), media_type="image/png" if filename.endswith(".png") else "image/webp")

    @app.delete("/api/library/{item_id}")
    def delete(item_id: str):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", item_id):
            raise HTTPException(404, "Image not found.")
        with lock:
            refresh()
            result = api_library_delete(item_id)
            commit()
            return result

    @app.put("/api/library/order")
    def reorder_library(payload: dict):
        with lock:
            refresh()
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
