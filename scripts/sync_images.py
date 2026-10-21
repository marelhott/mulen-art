"""Download every generated image from the Modal outputs Volume into ~/Pictures/Mulen art.

  Plátno/   img2img results (canvas)
  Atelier/  Atelier studies (noise, subject, photo, archive)

Runs on the Mac (manually or from the LaunchAgent in scripts/install_sync_agent.sh) and is safe to repeat:
a record is processed once (.sync-state.json), existing files are never overwritten, and images you deleted in
the app are skipped. Nothing is ever deleted locally. Usage: .venv/bin/python scripts/sync_images.py [--dest DIR]
"""
import argparse, json, os, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import modal

DEFAULT_DEST = Path.home() / "Pictures" / "Mulen art"
FOLDERS = {"canvas": "Plátno", "atelier": "Atelier"}
VOLUME = "img2img-outputs"


def read_bytes(volume, path):
    return b"".join(volume.read_file(path))


def classify(record):
    return "atelier" if (record.get("settings") or {}).get("generation_type") == "atelier" else "canvas"


def sync(dest, dry_run=False):
    volume = modal.Volume.from_name(VOLUME)
    entries = {entry.path.lstrip("/"): entry for entry in volume.listdir("/") if entry.type == modal.volume.FileEntryType.FILE}
    for folder in FOLDERS.values():
        (dest / folder).mkdir(parents=True, exist_ok=True)
    state_path = dest / ".sync-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    todo = [name for name in entries if name.endswith(".json") and name not in state]

    def load(name):
        try:
            record = json.loads(read_bytes(volume, name))
            return name, record if isinstance(record, dict) and record.get("filename") else None
        except Exception:
            return name, None

    with ThreadPoolExecutor(max_workers=16) as pool:
        loaded = list(pool.map(load, todo))
    jobs, skipped = [], 0
    for name, record in loaded:
        if record is None:
            state[name] = "not-a-record"
        elif record.get("deleted"):
            state[name] = "deleted"
            skipped += 1
        elif record["filename"] in entries:  # the image may land a moment after its record
            jobs.append((name, record))

    def fetch(job):
        name, record = job
        target = dest / FOLDERS[classify(record)] / record["filename"]
        if not target.exists():
            data = read_bytes(volume, record["filename"])
            fd, temporary = tempfile.mkstemp(dir=target.parent, suffix=".part")
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(temporary, target)
            try:
                stamp = datetime.fromisoformat(record["created_at"]).timestamp()
                os.utime(target, (stamp, stamp))  # Finder sorts by the time it was generated
            except (KeyError, ValueError):
                pass
        return name, str(target.relative_to(dest))

    downloaded = 0
    if not dry_run:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for name, relative in pool.map(fetch, jobs):
                state[name] = relative
                downloaded += 1
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=0))
    return {"new_records": len(todo), "downloaded": downloaded, "skipped_deleted": skipped,
            "waiting_for_image": len(todo) - len(jobs) - skipped - sum(1 for _, r in loaded if r is None), "dry_run": dry_run}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = sync(args.dest, args.dry_run)
    print(datetime.now().isoformat(timespec="seconds"), json.dumps(result, ensure_ascii=False))
