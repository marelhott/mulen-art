"""Mirror the generated images of the Modal outputs Volume into ~/Pictures/Mulen art.

  Plátno/   img2img results (canvas)
  Atelier/  Atelier studies
  unCLIP/   unCLIP variants and metamorphoses
  Vari/     Vari siblings
  Koláž/    Koláž results

New images are downloaded within seconds; an image you delete in the app is moved to the Trash here too
(and comes back if you restore it in the app). Files you delete or move yourself are left alone.

  .venv/bin/python scripts/sync_images.py            one pass
  .venv/bin/python scripts/sync_images.py --watch    keep running (what the LaunchAgent does)
"""
import argparse, json, os, re, shutil, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime
from pathlib import Path

DEFAULT_DEST = Path.home() / "Pictures" / "Mulen art"
FOLDERS = {"canvas": "Plátno", "atelier": "Atelier", "unclip": "unCLIP", "vari": "Vari", "collage": "Koláž"}
KINDS = {"atelier": "atelier", "reimagine": "unclip", "vari": "vari", "collage": "collage"}
VOLUME = "img2img-outputs"
# The app lives in this Modal profile; the Mac's *active* profile is another workspace with its own, stale outputs Volume.
PROFILE = "img2img"
READ_TIMEOUT_SECONDS = 120
SAFE_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
_READER = ThreadPoolExecutor(max_workers=16, thread_name_prefix="volume-read")


class TransientError(Exception):
    """A network/Volume failure: nothing was learned about the record, so it must be looked at again."""


def classify(record):
    return KINDS.get((record.get("settings") or {}).get("generation_type"), "canvas")


def read_bytes(volume, path, timeout=READ_TIMEOUT_SECONDS):
    """Read a Volume file; the Modal call has no timeout of its own, so bound it here."""
    future = _READER.submit(lambda: b"".join(volume.read_file(path)))
    try:
        return future.result(timeout=timeout)
    except FutureTimeout as exc:
        raise TransientError(f"timed out reading {path}") from exc


def to_trash(path, trash=Path.home() / ".Trash"):
    """Move to the macOS Trash (recoverable). Never deletes for good: if the Trash is unavailable this raises
    and the file stays where it is (the next pass tries again)."""
    trash.mkdir(exist_ok=True)
    target = trash / path.name
    if target.exists():
        target = trash / f"{path.stem}-{int(time.time())}{path.suffix}"
    shutil.move(str(path), str(target))


def migrate(state):
    """Older state files stored just the relative path per record."""
    return {name: (value if isinstance(value, dict) else {"status": "downloaded" if value.endswith((".png", ".webp")) else "skip", "path": value, "mtime": None})
            for name, value in state.items()}


TRANSIENT = object()


def load_state(path):
    """A truncated or corrupt state file must not stop every later run: set it aside and start over
    (files already on disk are recognised, so nothing is downloaded twice)."""
    if not path.exists():
        return {}
    try:
        return migrate(json.loads(path.read_text()))
    except (ValueError, AttributeError):
        path.replace(path.with_suffix(".corrupt"))
        return {}


def save_state(path, state):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False))
    os.replace(temporary, path)  # atomic: a crash mid-write cannot leave half a JSON document


def sync(dest, volume=None, trash=to_trash, now=None):
    if volume is None:
        os.environ.setdefault("MODAL_PROFILE", PROFILE)  # must be set before modal reads its config
        import modal
        volume = modal.Volume.from_name(VOLUME)
    from modal.volume import FileEntryType
    entries = {entry.path.lstrip("/"): entry for entry in volume.listdir("/") if entry.type == FileEntryType.FILE}
    for folder in FOLDERS.values():
        (dest / folder).mkdir(parents=True, exist_ok=True)
    state_path = dest / ".sync-state.json"
    state = load_state(state_path)
    # A record needs a look when it is new or was rewritten (saved, deleted, restored) since we last saw it.
    # Downloads remembered without their kind predate the per-tab folders: look once more so the file moves where it belongs.
    changed = [name for name, entry in entries.items() if name.endswith(".json") and (name not in state or state[name].get("mtime") != entry.mtime
               or (state[name].get("status") == "downloaded" and "kind" not in state[name]))]

    def load(name):
        try:
            raw = read_bytes(volume, name)
        except Exception:
            return name, TRANSIENT  # network trouble says nothing about the record: look again next pass
        try:
            record = json.loads(raw)
        except ValueError:
            return name, None  # genuinely not a usable record
        valid = isinstance(record, dict) and isinstance(record.get("filename"), str) and SAFE_NAME.fullmatch(record["filename"]) and ".." not in record["filename"]
        return name, record if valid else None

    with ThreadPoolExecutor(max_workers=16) as pool:
        loaded = list(pool.map(load, changed))
    downloads, report = [], {"downloaded": 0, "removed": 0, "checked": len(changed)}
    for name, record in loaded:
        mtime = entries[name].mtime
        previous = state.get(name, {})
        if record is TRANSIENT:
            continue
        if record is None:
            state[name] = {"status": "skip", "path": None, "mtime": mtime}
        elif record.get("deleted"):
            local = previous.get("path") and dest / previous["path"]
            if previous.get("status") == "downloaded" and local and local.exists():
                try:
                    trash(local)
                except OSError as exc:  # keep the file and the old state: retried on the next pass
                    print("could not move to the Trash:", local, exc, file=sys.stderr, flush=True)
                    continue
                report["removed"] += 1
            state[name] = {"status": "deleted", "path": previous.get("path"), "mtime": mtime}
        elif record["filename"] in entries:  # the image can land a moment after its record
            downloads.append((name, record, mtime))

    def fetch(job):
        name, record, mtime = job
        kind = classify(record)
        target = dest / FOLDERS[kind] / record["filename"]
        fresh = False
        previous = state.get(name, {})
        old = previous.get("path") and dest / previous["path"]
        if previous.get("status") == "downloaded" and old and old != target and old.is_file() and not target.exists():
            os.replace(old, target)  # filed under another folder by an earlier version
        if not target.exists() and state.get(name, {}).get("status") != "downloaded":
            try:
                data = read_bytes(volume, record["filename"])
            except Exception:
                return name, None, False  # try again next pass
            fd, temporary = tempfile.mkstemp(dir=target.parent, suffix=".part")
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                os.replace(temporary, target)
            finally:
                Path(temporary).unlink(missing_ok=True)  # no stray .part files after a failed write
            fresh = True
            try:
                stamp = datetime.fromisoformat(record["created_at"]).timestamp()
                os.utime(target, (stamp, stamp))  # Finder sorts by the time the image was made
            except (KeyError, ValueError):
                pass
        return name, {"status": "downloaded", "path": str(target.relative_to(dest)), "kind": kind, "mtime": mtime}, fresh

    with ThreadPoolExecutor(max_workers=8) as pool:
        for name, entry, fresh in pool.map(fetch, downloads):
            if entry is None:
                continue
            state[name] = entry
            report["downloaded"] += int(fresh)
    save_state(state_path, state)
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
