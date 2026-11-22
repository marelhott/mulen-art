"""OpenRouter (/images) and Venice (Qwen edit, Lustify) over httpx; ported from Mulen Nano's lib/openrouter.cjs and lib/external-images.cjs.

Keys come from the environment only and are never logged or put into an error message.
"""
import base64
import os
import re
import time
from typing import Any, Callable

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/images"
VENICE_URL = "https://api.venice.ai/api/v1/image"
QWEN = {  # venice model -> (api id, max inputs, max prompt chars)
    "venice/qwen-edit-uncensored": ("qwen-edit-uncensored", 3, 1500),
    "venice/qwen-image-2-1-turbo-edit": ("qwen-image-2-1-turbo-edit", 6, 10000),
    "venice/qwen-image-2-1-pro-edit": ("qwen-image-2-1-pro-edit", 10, 10000),
}
VENICE_RATIOS = {"1:1", "3:2", "16:9", "21:9", "9:16", "2:3", "3:4", "4:3", "4:5"}


class ProviderError(RuntimeError):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class Cancelled(RuntimeError):
    pass


def clean_key(value: str | None) -> str:
    """A key pasted with quotes or a trailing \\n would be rejected as invalid."""
    key = str(value or "").strip()
    for _ in range(2):
        key = re.sub(r"\\n$", "", key).strip()
        if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
            key = key[1:-1].strip()
    return key


def new_client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(300.0, connect=20.0), headers={"User-Agent": "mulen-art-studio/1.0"}, follow_redirects=True)


def _scrub(text: str) -> str:
    return re.sub(r"data:[^\s\"']+", "[data]", str(text))[:600]


def _openrouter_error(response: httpx.Response) -> ProviderError:
    try:
        data = response.json()
    except ValueError:
        data = {}
    error = data.get("error") if isinstance(data, dict) and isinstance(data.get("error"), dict) else {}
    metadata = error.get("metadata") or {}
    raw = metadata.get("raw")
    upstream = ""
    if isinstance(raw, str):
        upstream = raw
    elif isinstance(raw, dict):
        upstream = (raw.get("error") or {}).get("message") or raw.get("message") or ""
    parts = [metadata.get("provider_name"), error.get("message") or (data.get("message") if isinstance(data, dict) else None) or f"OpenRouter HTTP {response.status_code}", upstream]
    return ProviderError(_scrub(" — ".join(str(part) for part in parts if part)), retryable=response.status_code in (408, 429) or response.status_code >= 500)


def _image_url_from(data: dict[str, Any]) -> str | None:
    message = ((data.get("choices") or [{}])[0] or {}).get("message") or {}
    content = message.get("content")
    candidates = [*(data.get("data") or []), *(message.get("images") or []), *(data.get("images") or []), *(content if isinstance(content, list) else [])]
    for item in candidates:
        if not isinstance(item, dict):
            continue
        url = (item.get("image_url") or {}).get("url") if isinstance(item.get("image_url"), dict) else None
        url = url or item.get("url") or item.get("data_url")
        if url:
            return str(url)
        if item.get("b64_json"):
            return f"data:{item.get('media_type') or item.get('mime_type') or 'image/png'};base64,{item['b64_json']}"
    return None


def data_url_bytes(url: str) -> bytes:
    return base64.b64decode(url.split(",", 1)[1])


def openrouter_image(client: httpx.Client, model: str, prompt: str, images: list[str], aspect_ratio: str | None, resolution: str | None) -> bytes:
    key = clean_key(os.environ.get("OPENROUTER_API_KEY"))
    if not key:
        raise ProviderError("OPENROUTER_API_KEY není nastavený na serveru.")
    body: dict[str, Any] = {"model": model, "prompt": prompt}
    if images:
        body["input_references"] = [{"type": "image_url", "image_url": {"url": url}} for url in images]
    if aspect_ratio and aspect_ratio != "Original":
        body["aspect_ratio"] = aspect_ratio
    if resolution:
        body["resolution"] = resolution
    headers = {"Authorization": f"Bearer {key}", "HTTP-Referer": os.environ.get("OPENROUTER_HTTP_REFERER") or "https://mulen-nano.vercel.app",
               "X-Title": os.environ.get("OPENROUTER_X_TITLE") or "Mulen Nano"}
    try:
        response = client.post(OPENROUTER_URL, json=body, headers=headers)
    except httpx.HTTPError as exc:
        raise ProviderError(f"OpenRouter: {type(exc).__name__}", retryable=True) from exc
    if response.status_code >= 400:
        raise _openrouter_error(response)
    url = _image_url_from(response.json())
    if not url:
        raise ProviderError("OpenRouter model nevrátil obrázek.", retryable=True)
    if url.startswith("data:"):
        return data_url_bytes(url)
    downloaded = client.get(url)
    if downloaded.status_code >= 400 or not downloaded.content:
        raise ProviderError("Výsledný obrázek se nepodařilo stáhnout.", retryable=True)
    return downloaded.content


def _venice_post(client: httpx.Client, path: str, payload: dict[str, Any]) -> httpx.Response:
    key = clean_key(os.environ.get("VENICE_API_KEY"))
    if not key:
        raise ProviderError("Chybí VENICE_API_KEY na serveru.")
    try:
        response = client.post(f"{VENICE_URL}/{path}", json=payload, headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError as exc:
        raise ProviderError(f"Venice: {type(exc).__name__}", retryable=True) from exc
    if response.status_code >= 400:
        hints = {401: "Neplatný API klíč.", 402: "Nedostatek kreditu.", 429: "Překročen limit požadavků."}
        detail = ""
        try:
            parsed = response.json()
            error = parsed.get("error")
            detail = _scrub((error.get("message") if isinstance(error, dict) else error) or parsed.get("message") or "")[:200]
        except ValueError:
            pass
        raise ProviderError(f"Venice HTTP {response.status_code}. {hints.get(response.status_code, 'Požadavek poskytovatel odmítl.')}" + (f" ({detail})" if detail else ""),
                            retryable=response.status_code in (408, 429) or response.status_code >= 500)
    return response


def _dimensions(aspect_ratio: str | None, width: int, height: int) -> dict[str, int]:
    ratio = width / height if height else 1.0
    match = re.fullmatch(r"(\d+):(\d+)", aspect_ratio or "")
    if match:
        ratio = int(match[1]) / int(match[2])
    ratio = min(4.0, max(0.25, ratio))
    return {"width": round((1024 if ratio >= 1 else 1024 * ratio) / 8) * 8, "height": round((1024 if ratio <= 1 else 1024 / ratio) / 8) * 8}


def venice_image(client: httpx.Client, model: str, prompt: str, images: list[str], aspect_ratio: str | None, resolution: str | None,
                 size: tuple[int, int] = (1024, 1024)) -> bytes:
    qwen = QWEN.get(model)
    if qwen:
        api_id, max_inputs, prompt_max = qwen
        if not images:
            raise ProviderError("Qwen Edit vyžaduje alespoň jeden vstupní obrázek.")
        if len(images) > max_inputs:
            raise ProviderError(f"Tento Qwen podporuje nejvýše {max_inputs} vstupních obrázků.")
        if len(prompt) > prompt_max:
            raise ProviderError(f"Prompt pro tento Qwen smí mít nejvýše {prompt_max} znaků.")
        multi = len(images) > 1
        payload: dict[str, Any] = {"modelId": api_id, "images": images, "prompt": prompt} if multi else {"model": api_id, "image": images[0], "prompt": prompt}
        payload.update(safe_mode=False, output_format="png")
        if aspect_ratio and aspect_ratio != "Original":
            if aspect_ratio not in VENICE_RATIOS:
                raise ProviderError("Tento poměr stran Qwen nepodporuje.")
            payload["aspect_ratio"] = aspect_ratio
        if api_id != "qwen-edit-uncensored" and resolution:
            payload["resolution"] = resolution
        response = _venice_post(client, "multi-edit" if multi else "edit", payload)
        if response.headers.get("content-type", "").split(";")[0] not in ("image/png", "image/jpeg", "image/webp") or not response.content:
            raise ProviderError("Venice nevrátil obrázek.", retryable=True)
        return response.content
    if model == "venice/lustify-v8":
        if images:
            raise ProviderError("Lustify v8 podporuje pouze generování z textu.")
        if len(prompt) > 1500:
            raise ProviderError("Prompt Lustify smí mít nejvýše 1500 znaků.")
        data = _venice_post(client, "generate", {"model": "lustify-v8", "prompt": prompt, **_dimensions(aspect_ratio, *size), "format": "png", "return_binary": False, "safe_mode": False}).json()
        image = (data.get("images") or [None])[0]
        if not isinstance(image, str) or not image:
            raise ProviderError("Lustify nevrátil obrázek.", retryable=True)
        return data_url_bytes(image) if image.startswith("data:") else base64.b64decode(image)
    raise ProviderError("Nepodporovaný externí model.")


def generate_image(client: httpx.Client, model: str, prompt: str, images: list[str], aspect_ratio: str | None, resolution: str | None,
                   cancelled: Callable[[], bool] | None = None, attempts: int = 3, size: tuple[int, int] = (1024, 1024),
                   sleep: Callable[[float], None] = time.sleep) -> bytes:
    """One image; transient failures (network, 429, 5xx, an empty answer) are retried with a growing pause."""
    call = venice_image if model.startswith("venice/") else openrouter_image
    for attempt in range(1, attempts + 1):
        if cancelled and cancelled():
            raise Cancelled("Zrušeno.")
        try:
            if call is venice_image:
                return venice_image(client, model, prompt, images, aspect_ratio, resolution, size)
            return openrouter_image(client, model, prompt, images, aspect_ratio, resolution)
        except ProviderError as exc:
            if not exc.retryable or attempt == attempts:
                raise
            sleep(2.0 * attempt)
    raise ProviderError("Generování selhalo.")
