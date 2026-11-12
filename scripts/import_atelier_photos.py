#!/usr/bin/env python3
"""Export Photos folders MALBA and ARTISTS, make compact private copies, and upload to Modal.

Requires macOS Photos automation permission, Pillow is not required (uses sips), and a working
Modal CLI login. Only resized JPEGs (max side 1536) and 320px thumbnails are uploaded.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTIONS = (("malba", "MALBA", "Malba"), ("artists", "ARTISTS", "Artists"))
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".webp", ".bmp", ".gif", ".dng"}


def export_collection(collection_id, folder_name, destination):
    target = destination / collection_id
    target.mkdir(parents=True, exist_ok=True)
    command = ["uv", "run", "--python", "3.12", "--with", "osxphotos", "osxphotos", "export",
               "--folder", folder_name, "--directory", "{folder_album}", "--convert-to-jpeg",
               "--skip-live", "--skip-raw", "--preview-if-missing", str(target)]
    print(f"Exportuji všechna alba ve složce Photos {folder_name} (u fotek mimo Mac použiji náhled z Photos)…", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def convert(source, destination, thumb):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.jpg")
    subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "88", "-Z", "1536", str(source), "--out", str(temporary)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
    os.replace(temporary, destination)
    subprocess.run(["sips", "-Z", "320", str(destination), "--out", str(thumb)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return digest


def prepare(exported, stage):
    collections = []
    image_files = []
    for collection_id, folder_name, display_name in COLLECTIONS:
        items, known = [], set()
        folder = exported / collection_id
        if folder.exists():
            for source in sorted(path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES):
                image_files.append((collection_id, folder_name, display_name, source))
                known.add(str(source))
        collections.append({"id": collection_id, "name": display_name, "count": 0, "items": items})

    prepared = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {}
        for collection_id, folder_name, display_name, source in image_files:
            album = source.parent.name.replace("_", " ")
            token = hashlib.sha256(f"{collection_id}:{album}:{source.relative_to(exported).as_posix()}".encode()).hexdigest()
            relative = Path("user-photos") / collection_id / f"{token}.jpg"
            thumb_relative = Path("user-photos") / collection_id / f"{token}-thumb.jpg"
            futures[pool.submit(convert, source, stage / relative, stage / thumb_relative)] = (
                collection_id, album, source.name, token, relative.as_posix(), thumb_relative.as_posix())
        for future in as_completed(futures):
            collection_id, album, filename, token, relative, thumb_relative = futures[future]
            try:
                digest = future.result()
                prepared.append({"collection": collection_id, "album": album, "filename": filename,
                                 "id": token, "path": relative, "thumb_path": thumb_relative, "sha256": digest})
            except Exception as exc:
                print(f"Přeskočeno {filename}: {exc}", file=sys.stderr)
    by_id = {collection["id"]: collection for collection in collections}
    for item in prepared:
        by_id[item["collection"]]["items"].append({key: value for key, value in item.items() if key != "collection"})
    for collection in collections:
        collection["items"].sort(key=lambda item: (item["album"].casefold(), item["filename"].casefold()))
        collection["count"] = len(collection["items"])
    return {"version": 1, "collections": collections}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-upload", action="store_true", help="prepare and audit locally without uploading")
    args = parser.parse_args()
    if not shutil.which("sips") or not shutil.which("uv"):
        raise SystemExit("This importer needs macOS sips and uv (https://docs.astral.sh/uv/).")
    with tempfile.TemporaryDirectory(prefix="atelier-photos-") as temporary:
        work = Path(temporary)
        exported, stage = work / "export", work / "stage"
        exported.mkdir(); stage.mkdir()
        for collection_id, folder_name, _name in COLLECTIONS:
            export_collection(collection_id, folder_name, exported)
        manifest = prepare(exported, stage)
        (stage / "user-photos").mkdir(exist_ok=True)
        (stage / "user-photos" / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        counts = {collection["id"]: collection["count"] for collection in manifest["collections"]}
        print(f"Připraveno fotek: {counts}", flush=True)
        if args.no_upload:
            saved = ROOT / "outputs" / "atelier-photo-import" / "user-photos"
            if saved.exists():
                raise SystemExit(f"Lokální cíl už existuje, nic jsem nepřepsal: {saved}")
            shutil.copytree(stage / "user-photos", saved)
            print(f"Lokální kopie: {saved}")
            return
        command = ["uv", "run", "--python", "3.12", "--with", "modal", "modal", "volume", "put", "img2img-archives",
                   str(stage / "user-photos"), "atelier-archives/user-photos", "--force"]
        # Volume.put of this folder includes manifest.json and both photo collections.
        subprocess.run(command, cwd=ROOT, check=True)
        print("Soukromé fotky a náhledy byly nahrány do Modal volume img2img-archives.", flush=True)


if __name__ == "__main__":
    main()
