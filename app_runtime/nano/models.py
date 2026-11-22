"""The image models of Mulen Nano (constants/imageModels.ts). One catalogue for the picker, the planner and input checks."""
from typing import Any

# max_inputs None = unlimited; resolution None = the provider is not sent one (FLUX 3 on OpenRouter only supports seed).
MODELS: list[dict[str, Any]] = [
    {"id": "nano-pro", "title": "Nano Pro", "model": "google/gemini-3-pro-image", "min_inputs": 0, "max_inputs": 14, "resolution": "1K"},
    {"id": "gemini", "title": "Nano Banana 2.1", "model": "google/gemini-nano-banana-2.1", "min_inputs": 0, "max_inputs": 14, "resolution": "1K"},
    {"id": "gpt", "title": "GPT Image 2.5", "model": "openai/gpt-image-2.5-sunburst", "min_inputs": 0, "max_inputs": 16, "resolution": None},
    {"id": "flux", "title": "FLUX 3", "model": "black-forest-labs/flux-3-image", "min_inputs": 0, "max_inputs": 10, "resolution": "1K"},
    {"id": "seedream", "title": "Seedream 5 Pro", "model": "bytedance-seed/seedream-5-0-pro", "min_inputs": 0, "max_inputs": 14, "resolution": "1K"},
    {"id": "muse", "title": "Muse", "model": "meta/muse-image", "min_inputs": 0, "max_inputs": None, "resolution": None},
    {"id": "grok", "title": "Grok Image 2", "model": "x-ai/grok-imagine-image-2.0", "min_inputs": 0, "max_inputs": 3, "resolution": "1K"},
    {"id": "mai", "title": "MAI Image 2.6", "model": "microsoft/mai-image-2.6", "min_inputs": 0, "max_inputs": 5, "resolution": None},
    {"id": "recraft", "title": "Recraft 4.1 Pro", "model": "recraft/recraft-v4.1-pro", "min_inputs": 0, "max_inputs": 1, "resolution": None},
    {"id": "qwen-uncensored", "title": "Qwen Uncensored", "model": "venice/qwen-edit-uncensored", "min_inputs": 1, "max_inputs": 3, "resolution": None},
    {"id": "qwen-turbo", "title": "Qwen Turbo", "model": "venice/qwen-image-2-1-turbo-edit", "min_inputs": 1, "max_inputs": 6, "resolution": "1K"},
    {"id": "qwen-pro", "title": "Qwen Pro", "model": "venice/qwen-image-2-1-pro-edit", "min_inputs": 1, "max_inputs": 10, "resolution": "1K"},
    {"id": "lustify", "title": "Lustify v8", "model": "venice/lustify-v8", "min_inputs": 0, "max_inputs": 0, "resolution": None},
]
BY_ID = {item["id"]: item for item in MODELS}
MAX_PER_MODEL = 5
MAX_SOURCES = 10


def provider_of(model: dict[str, Any]) -> str:
    return "venice" if model["model"].startswith("venice/") else "openrouter"


def key_name(model: dict[str, Any]) -> str:
    return "VENICE_API_KEY" if provider_of(model) == "venice" else "OPENROUTER_API_KEY"


def input_error(model: dict[str, Any], count: int) -> str | None:
    """The same checks as imageModelInputError in Mulen Nano."""
    title = model["title"]
    if count < model["min_inputs"]:
        return f"{title} vyžaduje vstupní obrázek."
    if model["max_inputs"] == 0 and count > 0:
        return f"{title} podporuje pouze generování z textu, ne úpravy fotografií."
    if model["max_inputs"] is not None and count > model["max_inputs"]:
        return f"{title} přijímá nejvýše {model['max_inputs']} vstupních obrázků."
    return None


def availability(env) -> list[dict[str, Any]]:
    """The models with whether their provider key is set (names only; a key value is never returned)."""
    result = []
    for item in MODELS:
        name = key_name(item)
        has_key = bool(str(env.get(name, "")).strip())
        result.append({"id": item["id"], "title": item["title"], "model": item["model"], "provider": provider_of(item),
                       "min_inputs": item["min_inputs"], "max_inputs": item["max_inputs"],
                       "available": has_key, "missing": None if has_key else name})
    return result
