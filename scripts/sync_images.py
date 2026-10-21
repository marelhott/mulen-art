"""Mirror the generated images of the Modal outputs Volume into ~/Pictures/Mulen art.

  Plátno/   img2img results (canvas)
  Atelier/  Atelier studies

New images are downloaded within seconds; an image you delete in the app is moved to the Trash here too
(and comes back if you restore it in the app). Files you delete or move yourself are left alone.

  .venv/bin/python scripts/sync_images.py            one pass
  .venv/bin/python scripts/sync_images.py --watch    keep running (what the LaunchAgent does)
"""
import argparse, json, os, shutil, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

DEFAULT_DEST = Path.home() / "Pictures" / "Mulen art"
FOLDERS = {"canvas": "Plátno", "atelier": "Atelier"}
VOLUME = "img2img-outputs"


def classify(record):
    return "atelier" if (record.get("settings") or {}).get("generation_type") == "atelier" else "canvas"


def read_bytes(volume, path):
    return b"".join(volume.read_file(path))


def to_trash(path, trash=Path.home() / ".Trash"):
    """Move to the macOS Trash (recoverable); fall back to deleting only if the Trash is unavailable."""
    try:
        trash.mkdir(exist_ok=True)
        target = trash / path.name
        if target.exists():
            target = trash / f"{path.stem}-{int(time.time())}{path.suffix}"
        shutil.move(str(path), str(target))
    except OSError:
        path.unlink(missing_ok=True)


def migrate(state):
    """Older state files stored just the relative path per record."""
    return {name: (value if isinstance(value, dict) else {"status": "downloaded" if value.endswith((".png", ".webp")) else "skip", "path": value, "mtime": None})
            for name, value in state.items()}


def sync(dest, volume=None, trash=to_trash, now=None):
    if volume is None:
        import modal
        volume = modal.Volume.from_name(VOLUME)
    from modal.volume import FileEntryType
    entries = {entry.path.lstrip("/"): entry for entry in volume.listdir("/") if entry.type == FileEntryType.FILE}
    for folder in FOLDERS.values():
        (dest / folder).mkdir(parents=True, exist_ok=True)
    state_path = dest / ".sync-state.json"
    state = migrate(json.loads(state_path.read_text())) if state_path.exists() else {}
    # A record needs a look when it is new or was rewritten (saved, deleted, restored) since we last saw it.
    changed = [name for name, entry in entries.items() if name.endswith(".json") and (name not in state or state[name].get("mtime") != entry.mtime)]

    def load(name):
        try:
            record = json.loads(read_bytes(volume, name))
            return name, record if isinstance(record, dict) and record.get("filename") else None
        except Exception:
            return name, None

    with ThreadPoolExecutor(max_workers=16) as pool:
        loaded = list(pool.map(load, changed))
    downloads, report = [], {"downloaded": 0, "removed": 0, "checked": len(changed)}
    for name, record in loaded:
        mtime = entries[name].mtime
        previous = state.get(name, {})
        if record is None:
            state[name] = {"status": "skip", "path": None, "mtime": mtime}
        elif record.get("deleted"):
            local = previous.get("path") and dest / previous["path"]
            if previous.get("status") == "downloaded" and local and local.exists():
                trash(local)
                report["removed"] += 1
            state[name] = {"status": "deleted", "path": previous.get("path"), "mtime": mtime}
        elif record["filename"] in entries:  # the image can land a moment after its record
            downloads.append((name, record, mtime))

    def fetch(job):
        name, record, mtime = job
        target = dest / FOLDERS[classify(record)] / record["filename"]
        fresh = False
        if not target.exists() and state.get(name, {}).get("status") != "downloaded":
            data = read_bytes(volume, record["filename"])
            fd, temporary = tempfile.mkstemp(dir=target.parent, suffix=".part")
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(temporary, target)
            fresh = True
            try:
                stamp = datetime.fromisoformat(record["created_at"]).timestamp()
                os.utime(target, (stamp, stamp))  # Finder sorts by the time the image was made
            except (KeyError, ValueError):
                pass
        return name, {"status": "downloaded", "path": str(target.relative_to(dest)), "mtime": mtime}, fresh

    with ThreadPoolExecutor(max_workers=8) as pool:
        for name, entry, fresh in pool.map(fetch, downloads):
            state[name] = entry
            report["downloaded"] += int(fresh)
    state_path.write_text(json.dumps(state, ensure_ascii=False))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=15)
    args = parser.parse_args()
    while True:
        try:
            report = sync(args.dest)
            if report["downloaded"] or report["removed"] or not args.watch:
                print(datetime.now().isoformat(timespec="seconds"), json.dumps(report), flush=True)
        except Exception as exc:  # network hiccup: try again next round
            print(datetime.now().isoformat(timespec="seconds"), "sync failed:", exc, file=sys.stderr, flush=True)
            if not args.watch:
                raise
        if not args.watch:
            break
        time.sleep(args.interval)
