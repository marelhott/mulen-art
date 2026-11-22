"""Vari providers: fal (queue + storage), Replicate (predictions), OpenAI (vision + image edit), Gemini.

Port of Vari/lib/providers/*. Synchronous httpx; every function takes the client so tests can inject a mock transport.
An explicit User-Agent is always sent: Replicate answers 403 to the default Python one.
"""
import base64
import json
import os
import random
import re
import time
from typing import Any, Callable

import httpx

USER_AGENT = "mulen-vari/1.0"
FAL_QUEUE = "https://queue.fal.run"
FAL_STORAGE = "https://rest.alpha.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3"
REPLICATE_API = "https://api.replicate.com/v1/predictions"
OPENAI_API = "https://api.openai.com/v1"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_IMAGE_MODEL = "gemini-3-pro-image-preview"


class ProviderError(RuntimeError):
    """A provider refused or failed; the message is shown on the job."""


class Cancelled(ProviderError):
    pass


def new_client(timeout: float = 120.0) -> httpx.Client:
    return httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)


def _key(name: str, what: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ProviderError(f"Chybí {name} v prostředí. {what} bez něj nepoběží.")
    return value


def _error_text(response: httpx.Response, fallback: str) -> str:
    try:
        data = response.json()
    except Exception:
        return f"{fallback} (HTTP {response.status_code})"
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        for key in ("detail", "error", "message"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, list) and value:
                first = value[0]
                return str(first.get("msg") if isinstance(first, dict) and first.get("msg") else first)
    return f"{fallback} (HTTP {response.status_code})"


def data_uri(data: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


# ---------------------------------------------------------------------------------------------------------- fal

def fal_headers() -> dict[str, str]:
    return {"Authorization": f"Key {_key('FAL_KEY', 'Engine na fal')}", "Content-Type": "application/json"}


def fal_upload(client: httpx.Client, data: bytes, mime: str = "image/png") -> str:
    """Public URL of the source (fal storage), or a data URI when there is no key or the upload fails."""
    if not os.environ.get("FAL_KEY"):
        return data_uri(data, mime)
    try:
        response = client.post(FAL_STORAGE, json={"content_type": mime, "file_name": "source.png"}, headers=fal_headers())
        response.raise_for_status()
        info = response.json()
        put = client.put(info["upload_url"], content=data, headers={"Content-Type": mime})
        put.raise_for_status()
        return info["file_url"]
    except Exception:
        return data_uri(data, mime)


def _image_candidate(candidate: Any) -> dict[str, str] | None:
    if isinstance(candidate, str):
        return {"url": candidate}
    if isinstance(candidate, dict):
        if isinstance(candidate.get("url"), str):
            return {"url": candidate["url"]}
        if isinstance(candidate.get("image_url"), str):
            return {"url": candidate["image_url"]}
    return None


def extract_fal_images(result: dict[str, Any]) -> list[dict[str, str]]:
    def sub(name):
        value = result.get(name)
        return value if isinstance(value, dict) else {}

    data, output = sub("data"), sub("output")
    buckets = [result.get("images"), result.get("image"), result.get("image_url"), data.get("images"), data.get("image"),
               data.get("image_url"), output.get("images"), output.get("image"), output.get("image_url")]
    images = []
    for bucket in buckets:
        for candidate in (bucket if isinstance(bucket, list) else [bucket]):
            found = _image_candidate(candidate)
            if found:
                images.append(found)
    return images


def run_fal(client: httpx.Client, payload: dict[str, Any], timeout: float = 300.0, poll: float = 1.0,
            cancelled: Callable[[], bool] | None = None, sleep: Callable[[float], None] = time.sleep) -> list[dict[str, str]]:
    model_id = payload["_model_id"]
    body = {key: value for key, value in payload.items() if key not in ("_model_id", "_repeat")}
    response = client.post(f"{FAL_QUEUE}/{model_id}", json=body, headers=fal_headers())
    if response.status_code >= 400:
        raise ProviderError(_error_text(response, "fal odmítl požadavek"))
    job = response.json()
    status_url, result_url, cancel_url = job.get("status_url"), job.get("response_url"), job.get("cancel_url")
    deadline = time.monotonic() + timeout
    while True:
        if cancelled and cancelled():
            if cancel_url:
                client.put(cancel_url, headers=fal_headers())
            raise Cancelled("Zrušeno uživatelem.")
        status = client.get(status_url, headers=fal_headers())
        if status.status_code >= 400:
            raise ProviderError(_error_text(status, "fal nevrátil stav úlohy"))
        if status.json().get("status") == "COMPLETED":
            break
        if time.monotonic() > deadline:
            if cancel_url:
                client.put(cancel_url, headers=fal_headers())
            raise ProviderError("fal neodpověděl včas (limit 5 minut).")
        sleep(poll)
    result = client.get(result_url, headers=fal_headers())
    if result.status_code >= 400:
        raise ProviderError(_error_text(result, "fal vrátil chybu"))
    return extract_fal_images(result.json())


# ------------------------------------------------------------------------------------------------------ Replicate

def replicate_headers() -> dict[str, str]:
    return {"Authorization": f"Token {_key('REPLICATE_API_TOKEN', 'Engine na Replicate')}", "Content-Type": "application/json"}


def create_replicate_prediction(client: httpx.Client, payload: dict[str, Any], attempts: int = 8,
                                sleep: Callable[[float], None] = time.sleep) -> str:
    """Replicate throttles accounts with little credit (6 requests a minute, burst 1): a 429 carries `retry_after`,
    so wait that long (plus jitter, because parallel jobs collide) and try again."""
    body = {"model": payload["model"], "input": payload["input"]} if payload.get("model") else {"version": payload["version"], "input": payload["input"]}
    for attempt in range(attempts):
        response = client.post(REPLICATE_API, json=body, headers=replicate_headers())
        if response.status_code == 429 and attempt < attempts - 1:
            try:
                wait = float(response.json().get("retry_after") or 10)
            except Exception:
                wait = 10.0
            sleep(min(wait, 60.0) + random.uniform(0.5, 4.0) * (attempt + 1))
            continue
        if response.status_code >= 400:
            raise ProviderError(_error_text(response, "Replicate odmítl požadavek"))
        return response.json()["id"]
    raise ProviderError("Replicate odmítá požadavky (limit).")


def cancel_replicate_prediction(client: httpx.Client, prediction_id: str) -> None:
    try:
        client.post(f"{REPLICATE_API}/{prediction_id}/cancel", headers=replicate_headers())
    except Exception:
        pass


def run_replicate(client: httpx.Client, payload: dict[str, Any], timeout: float = 1200.0, poll: float = 2.0, start_timeout: float = 480.0,
                  cancelled: Callable[[], bool] | None = None, on_status: Callable[[str], None] | None = None,
                  sleep: Callable[[float], None] = time.sleep) -> list[dict[str, str]]:
    prediction_id = create_replicate_prediction(client, payload)
    began = time.monotonic()
    deadline = began + timeout
    while True:
        if cancelled and cancelled():
            cancel_replicate_prediction(client, prediction_id)
            raise Cancelled("Zrušeno uživatelem.")
        response = client.get(f"{REPLICATE_API}/{prediction_id}", headers=replicate_headers())
        if response.status_code >= 400:
            raise ProviderError(_error_text(response, "Replicate nevrátil stav úlohy"))
        data = response.json()
        if on_status:
            on_status(data.get("status", ""))
        if data.get("status") == "succeeded":
            output = data.get("output")
            urls = output if isinstance(output, list) else [output] if output else []
            return [{"url": url} for url in urls if isinstance(url, str)]
        if data.get("status") in ("failed", "canceled"):
            raise ProviderError(str(data.get("error") or "Replicate úloha selhala."))
        if data.get("status") == "starting" and time.monotonic() - began > start_timeout:
            # A cold public model can stay in "starting" for a very long time (SD Image Variation does): stop waiting.
            cancel_replicate_prediction(client, prediction_id)
            raise ProviderError(f"Replicate model se nespustil do {int(start_timeout // 60)} minut (studený start). Zkus jiný engine, nebo to zopakuj později.")
        if time.monotonic() > deadline:
            cancel_replicate_prediction(client, prediction_id)
            raise ProviderError("Replicate neodpověděl včas (limit 20 minut).")
        sleep(poll)


# -------------------------------------------------------------------------------------------------------- OpenAI

def _openai_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_key('OPENAI_API_KEY', 'Tento engine')}"}


def _response_text(data: dict[str, Any]) -> str:
    text = data.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    chunks = []
    for output in data.get("output") or []:
        if not isinstance(output, dict):
            continue
        for item in output.get("content") or []:
            if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip():
                chunks.append(item["text"].strip())
    return "\n".join(chunks).strip()


def _clean_string(value: Any, fallback: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _clean_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return items or fallback


def normalize_analysis(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "subject": _clean_string(data.get("subject"), "main subject and its defining forms"),
        "scene": _clean_string(data.get("scene"), "the depicted scene and environment"),
        "composition": _clean_string(data.get("composition"), "balanced but distinctive composition"),
        "framing": _clean_string(data.get("framing"), "medium framing"),
        "perspective": _clean_string(data.get("perspective"), "eye-level perspective"),
        "palette": _clean_string(data.get("palette"), "muted, coherent palette"),
        "light": _clean_string(data.get("light"), "soft directional light"),
        "medium": _clean_string(data.get("medium"), "image with tactile material character"),
        "texture": _clean_string(data.get("texture"), "visible surface texture and edge behavior"),
        "mood": _clean_string(data.get("mood"), "quiet but charged atmosphere"),
        "immutable_elements": _clean_list(data.get("immutable_elements"),
                                          ["the core subject identity", "the image's atmosphere", "the key material and spatial logic"]),
        "variable_elements": _clean_list(data.get("variable_elements"), ["crop", "camera angle", "secondary supporting details"]),
        "summary": _clean_string(data.get("summary"), "A faithful but newly generated variant of the source image."),
    }


def analyze_image_for_variant(client: httpx.Client, source_url: str) -> dict[str, Any]:
    body = {"model": "gpt-4.1-mini", "max_output_tokens": 900, "input": [{"role": "user", "content": [
        {"type": "input_text", "text": "Analyze this image for a variant-generation pipeline. Return JSON only, no markdown. "
         "Keys: subject, scene, composition, framing, perspective, palette, light, medium, texture, mood, immutable_elements, variable_elements, summary. "
         "immutable_elements and variable_elements must be arrays of short strings. Focus on what must stay recognizable across real variants, not on generic captioning."},
        {"type": "input_image", "image_url": source_url, "detail": "high"}]}]}
    response = client.post(f"{OPENAI_API}/responses", json=body, headers=_openai_headers())
    if response.status_code >= 400:
        raise ProviderError(_error_text(response, "OpenAI vision selhal"))
    match = re.search(r"\{[\s\S]*\}", _response_text(response.json()))
    if not match:
        raise ProviderError("Vision model nevrátil JSON analýzu.")
    return normalize_analysis(json.loads(match.group(0)))


def edit_with_gpt_image2(client: httpx.Client, image: bytes, prompt: str, count: int, size: str) -> list[bytes]:
    response = client.post(f"{OPENAI_API}/images/edits", headers=_openai_headers(), timeout=300.0,
                           data={"model": "gpt-image-2", "prompt": prompt, "n": str(count), "size": size, "quality": "high",
                                 "background": "auto", "output_format": "png"},
                           files={"image": ("source.png", image, "image/png")})
    if response.status_code >= 400:
        raise ProviderError(_error_text(response, "OpenAI GPT Image 2 selhal"))
    items = response.json().get("data") or []
    return [base64.b64decode(item["b64_json"]) for item in items if isinstance(item, dict) and item.get("b64_json")]


# -------------------------------------------------------------------------------------------------------- Gemini

def gemini_aspect_ratio(width: int, height: int) -> str:
    if width == height:
        return "1:1"
    if width > height:
        ratio = width / height
        return "21:9" if ratio >= 1.85 else "16:9" if ratio >= 1.55 else "4:3" if ratio >= 1.22 else "3:2"
    ratio = height / width
    return "9:16" if ratio >= 1.85 else "2:3" if ratio >= 1.45 else "3:4" if ratio >= 1.28 else "4:5"


def edit_with_gemini_3_pro(client: httpx.Client, image: bytes, prompt: str, count: int, width: int, height: int) -> list[bytes]:
    key = _key("GEMINI_API_KEY", "Gemini 3 Pro")
    aspect = gemini_aspect_ratio(width, height)
    outputs: list[bytes] = []
    for _ in range(max(1, count)):
        response = client.post(f"{GEMINI_API}/models/{GEMINI_IMAGE_MODEL}:generateContent", timeout=300.0,
                               headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                               json={"contents": [{"role": "user", "parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(image).decode()}}]}],
                                     "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "imageConfig": {"aspectRatio": aspect, "imageSize": "2K"}, "temperature": 0.35}})
        if response.status_code >= 400:
            raise ProviderError(_error_text(response, "Gemini 3 Pro selhal"))
        for candidate in response.json().get("candidates") or []:
            content = candidate.get("content") if isinstance(candidate, dict) else None
            for part in (content or {}).get("parts") or []:
                inline = part.get("inlineData") if isinstance(part, dict) else None
                if isinstance(inline, dict) and inline.get("data"):
                    outputs.append(base64.b64decode(inline["data"]))
    return outputs


def download(client: httpx.Client, url: str) -> bytes:
    if url.startswith("data:"):
        return base64.b64decode(url.split(",", 1)[1])
    response = client.get(url)
    if response.status_code >= 400:
        raise ProviderError(f"Výsledný obrázek se nepodařilo stáhnout (HTTP {response.status_code}).")
    return response.content
