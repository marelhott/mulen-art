"""Copy the three approved training checkpoints into the private application volume."""
import json
from pathlib import Path
import modal

app = modal.App("img2img-promote-tuymans")
source = modal.Volume.from_name("mulen-training-results")
target = modal.Volume.from_name("img2img-models")

@app.function(image=modal.Image.debian_slim(python_version="3.11"), volumes={"/results": source, "/models": target}, cpu=2, memory=512, timeout=1800)
def promote():
    import hashlib
    import os
    import struct
    folder = Path("/results/full-unet-approved-20261019T203404Z")
    report = []
    for step in (800, 1600, 2400):
        src = folder / f"mvhpaint_full_unet-step{step:08d}.safetensors"
        dst = Path(f"/models/checkpoints/tuymans_modal_{step}.safetensors")
        with src.open("rb") as f:
            header_len = struct.unpack("<Q", f.read(8))[0]
            header = json.loads(f.read(header_len))
        end = max(v["data_offsets"][1] for k,v in header.items() if k != "__metadata__")
        if 8 + header_len + end != src.stat().st_size:
            raise ValueError(f"Incomplete checkpoint: {src.name}")
        with src.open("rb") as f:
            expected = hashlib.file_digest(f, "sha256").hexdigest()
        if step == 2400 and expected != "bfbf513f8a70e5aea50f6e23ae41ae88aa2685c3d511aefad91d70a817cb81a8":
            raise ValueError("Candidate hash changed")
        valid = False
        if dst.exists() and dst.stat().st_size == src.stat().st_size:
            with dst.open("rb") as f:
                valid = hashlib.file_digest(f, "sha256").hexdigest() == expected
        if not valid:
            tmp = dst.with_suffix(".part")
            dst.parent.mkdir(parents=True, exist_ok=True)
            with src.open("rb") as inp, tmp.open("wb") as out:
                while chunk := inp.read(8 * 1024 * 1024):
                    out.write(chunk)
            with tmp.open("rb") as f:
                actual = hashlib.file_digest(f, "sha256").hexdigest()
            if actual != expected:
                raise ValueError(f"Copy hash mismatch: {dst.name}")
            os.replace(tmp, dst)
        report.append({"step": step, "path": str(dst), "sha256": expected, "size": dst.stat().st_size})
        target.commit()
        print(f"Verified {dst.name}", flush=True)
    return report

@app.local_entrypoint()
def main():
    report = promote.remote()
    path = Path("outputs/verification/tuymans-promoted.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
