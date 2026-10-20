"""Upload only configured checkpoint/LoRA files; .bak files are never uploaded."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def inventory(source):
    config = json.loads((ROOT / "config/models.json").read_text())
    result = []
    for section in ("models", "loras"):
        for item in config[section]:
            if item.get("kind") == "base" or item.get("origin") == "modal-training":
                continue  # Downloaded directly on Modal by download_sdxl_base.py.
            if not item.get("path"):
                continue
            folder = "checkpoints" if section == "models" else "lora"
            local = source / folder / Path(item["path"]).name
            if not local.is_file():
                raise FileNotFoundError(local)
            result.append((local, item["path"].removeprefix("/models")))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("/Users/mulenmara/CODE_DISK/models"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    files = inventory(args.source)
    for local, remote in files:
        print(f"{local.name}: {local.stat().st_size / 1024**3:.2f} GiB -> {remote}")
    print(f"Total: {sum(p.stat().st_size for p, _ in files) / 1024**3:.2f} GiB")
    if args.dry_run:
        return
    import modal
    volume = modal.Volume.from_name("img2img-models", create_if_missing=True)
    # One upload transaction; CLI/SDK handles multipart transfers for large files.
    with volume.batch_upload(force=True) as batch:
        for local, remote in files:
            batch.put_file(local, remote)
    print("Upload complete.")


if __name__ == "__main__":
    main()
