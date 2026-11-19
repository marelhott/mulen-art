"""Private user-photo catalog stored beside Atelier's Modal reference archives."""
import hashlib
import json
import random
from functools import lru_cache
import os
import re
from pathlib import Path


COLLECTIONS = {"malba", "artists"}
ID_RE = re.compile(r"^[0-9a-f]{64}$")


def photos_root():
    from .archives import archive_root
    return archive_root() / "user-photos"


def load_manifest():
    path = photos_root() / "manifest.json"
    try:
        stat = path.stat()
        return _load_manifest(stat.st_mtime_ns, stat.st_size)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"version": 1, "collections": []}


@lru_cache(maxsize=4)
def _load_manifest(_mtime_ns, _size):
    path = photos_root() / "manifest.json"
    data = json.loads(path.read_text())
    return data if isinstance(data.get("collections"), list) else {"version": 1, "collections": []}


def collection_options():
    return [{key: collection[key] for key in ("id", "name", "count")}
            for collection in load_manifest()["collections"] if collection.get("id") in COLLECTIONS]


def list_photos(collection_id, offset=0, limit=48):
    if collection_id not in COLLECTIONS:
        raise ValueError("Unknown photo collection")
    offset = max(0, int(offset))
    limit = min(72, max(1, int(limit)))
    collection = next((row for row in load_manifest()["collections"] if row.get("id") == collection_id), None)
    items = collection.get("items", []) if collection else []
    return {"collection": collection_id, "name": collection.get("name", collection_id.title()) if collection else collection_id.title(),
            "count": len(items), "offset": offset, "items": [public_item(item) for item in items[offset:offset + limit]],
            "has_more": offset + limit < len(items)}


def public_item(item):
    return {key: item[key] for key in ("id", "filename", "album", "width", "height", "thumb") if key in item} | {
        "thumbnail_url": f"/atelier-photo/{item['id']}?thumb=true", "image_url": f"/atelier-photo/{item['id']}"}


_index_state = (None, {})  # (manifest object the index was built from, id -> (collection, item)); replaced atomically


def _item_for_id(photo_id):
    """O(1) lookup instead of scanning every photo of every collection per request."""
    global _index_state
    manifest = load_manifest()
    built_from, index = _index_state
    if built_from is not manifest:  # load_manifest() returns the same object until the file changes
        index = {}
        for collection in manifest["collections"]:
            for item in collection.get("items", []):
                index.setdefault(item.get("id"), (collection, item))
        _index_state = (manifest, index)
    return index.get(photo_id, (None, None))


def pick_photo(collection_id, seed, photo_id=""):
    """Choose the photo from the manifest alone (no file access) - enough to title a study."""
    if collection_id not in COLLECTIONS:
        raise ValueError("Unknown photo collection")
    collection = next((row for row in load_manifest()["collections"] if row.get("id") == collection_id), None)
    items = collection.get("items", []) if collection else []
    if photo_id:
        item = next((row for row in items if row.get("id") == photo_id), None)
    elif items:
        # Each study's unique seed makes an independent, repeatable draw from the full collection.
        item = items[random.Random(f"atelier-photo:{collection_id}:{int(seed)}").randrange(len(items))]
    else:
        item = None
    if not item:
        raise ValueError(f"No photos are available in {collection_id}; import the Photos albums first")
    return collection, item


def photo_for(collection_id, seed, photo_id=""):
    collection, item = pick_photo(collection_id, seed, photo_id)
    root = photos_root().resolve()
    source = (root.parent / item["path"]).resolve()
    thumb = (root.parent / item["thumb_path"]).resolve()
    if not source.is_relative_to(root.parent) or not source.is_file():
        raise ValueError("Selected Atelier photo is unavailable")
    if hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
        raise ValueError("Selected Atelier photo failed its integrity check")
    return collection, item, source, thumb


def photo_path(photo_id, thumbnail=False):
    if not isinstance(photo_id, str) or not ID_RE.fullmatch(photo_id):
        raise ValueError("Invalid Atelier photo id")
    _collection, item = _item_for_id(photo_id)
    if item:
        root = photos_root().parent.resolve()
        relative = item.get("thumb_path") if thumbnail else item.get("path")
        path = (root / relative).resolve()
        if path.is_relative_to(root) and path.is_file():
            return path
    raise FileNotFoundError("Atelier photo not found")
