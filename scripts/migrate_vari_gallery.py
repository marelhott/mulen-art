"""One-time copy of the old Vari gallery (R2 bucket `variants`) into the studio library on Modal.

Reads R2 only (the bucket is never changed or deleted). Adds each image to the outputs Volume with a library record
(generation_type "vari"), so it shows in the Vari tab and in Knihovna. Safe to repeat: already copied keys are skipped
(manifest `.vari-migrated.json` on the Volume).

  Dry run (default):  MODAL_PROFILE=img2img .venv/bin/python -m modal run scripts/migrate_vari_gallery.py
  Copy:               MODAL_PROFILE=img2img .venv/bin/python -m modal run scripts/migrate_vari_gallery.py --apply

Needs the Modal secret `vari-keys` with R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY (R2_BUCKET defaults to `variants`).
"""
import modal

app = modal.App("vari-gallery-migration")
outputs = modal.Volume.from_name("img2img-outputs")
image = modal.Image.debian_slim(python_version="3.11").pip_install("boto3==1.35.99", "pillow==11.1.0")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MANIFEST = ".vari-migrated.json"


@app.function(image=image, secrets=[modal.Secret.from_name("vari-keys")], volumes={"/outputs": outputs}, timeout=3600, cpu=2, memory=2048)
def migrate(apply: bool = False):
    import io
    import json
    import os
    import re
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    import boto3
    from PIL import Image

    bucket = os.environ.get("R2_BUCKET") or "variants"
    client = boto3.client("s3", region_name="auto", endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                          aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])
    objects = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for item in page.get("Contents", []):
            if Path(item["Key"]).suffix.lower() in IMAGE_EXTENSIONS:
                objects.append(item)
    objects.sort(key=lambda item: (item["LastModified"], item["Key"]))
    total_bytes = sum(item["Size"] for item in objects)
    outputs.reload()
    root = Path("/outputs")
    manifest_path = root / MANIFEST
    done = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    todo = [item for item in objects if item["Key"] not in done]
    summary = {"bucket": bucket, "images_in_bucket": len(objects), "bytes": total_bytes, "already_copied": len(objects) - len(todo), "to_copy": len(todo)}
    if not apply:
        return {**summary, "mode": "dry-run (nothing written)"}

    def stem_for(item, index):
        folder = item["Key"].split("/")[0]
        match = re.match(r"^\d{10,}-(.+)$", folder)
        engine = match.group(1) if match else "replicate"
        engine_part = re.sub(r"[^A-Za-z0-9_-]+", "_", engine)[:60]
        stamp = item["LastModified"].strftime("%Y%m%dT%H%M%S") + f"{index:06d}"
        return f"{stamp}_01_vari_{engine_part}", engine

    def copy(pair):
        index, item = pair
        stem, engine = stem_for(item, index)
        body = client.get_object(Bucket=bucket, Key=item["Key"])["Body"].read()
        picture = Image.open(io.BytesIO(body))
        extension = (picture.format or "PNG").lower().replace("jpeg", "jpg")
        name = f"{stem}.{extension}"
        (root / name).write_bytes(body)
        created = item["LastModified"].isoformat()
        record = {"id": stem, "filename": name, "url": f"/library/{name}", "thumb_url": f"/thumb/{stem}.webp", "width": picture.width, "height": picture.height,
                  "format": extension, "created_at": created, "model_id": f"vari_{engine}", "lora_id": "none",
                  "settings": {"generation_type": "vari", "vari_engine": engine, "model_id": f"vari_{engine}", "model_name": f"Vari · {engine}",
                               "lora_id": "none", "migrated_from": f"r2/{bucket}/{item['Key']}", "output_width": picture.width, "output_height": picture.height},
                  "saved_to_library": True}
        (root / f"{stem}.json").write_text(json.dumps(record, ensure_ascii=True, indent=2), encoding="utf-8")
        return item["Key"], stem

    copied = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for key, stem in pool.map(copy, list(enumerate(todo))):
            done[key] = stem
            copied += 1
    manifest_path.write_text(json.dumps(done))
    outputs.commit()
    return {**summary, "mode": "copied", "copied_now": copied}


@app.local_entrypoint()
def main(apply: bool = False):
    print(migrate.remote(apply))
