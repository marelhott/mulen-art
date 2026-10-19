"""Real cloud inference verification (billable GPU time). Never runs a local model."""
import argparse
import base64
import json
from pathlib import Path
import time
import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--model", default="tuymans_sdxl")
    parser.add_argument("--lora", default="none")
    parser.add_argument("--steps", type=int, default=25)
    parser.add_argument("--num-images", type=int, default=1)
    parser.add_argument("--report-name")
    args = parser.parse_args()
    credentials = json.loads((ROOT / ".modal-app-credentials.json").read_text())
    started = time.monotonic()
    with httpx.Client(base_url=args.url.rstrip("/"), auth=(credentials["APP_USERNAME"], credentials["APP_PASSWORD"]), timeout=90) as client:
        response = client.post("/api/generate", json={
            "image_base64": base64.b64encode(args.image.read_bytes()).decode(),
            "model_id": args.model, "lora_id": args.lora, "lora_strength": 0.8,
            "denoise": 0.45, "cfg": 5, "steps": args.steps, "scale": 1,
            "num_images": args.num_images,
        })
        response.raise_for_status()
        job_id = response.json()["job_id"]
        previous = ""
        first_partial_wall_seconds = None
        while time.monotonic() - started < 1800:
            response = client.get(f"/api/jobs/{job_id}")
            response.raise_for_status()
            job = response.json()
            if job.get("partial_images") and first_partial_wall_seconds is None:
                partial = client.get(job["partial_images"][0]["url"])
                partial.raise_for_status()
                first_partial_wall_seconds = round(time.monotonic()-started, 2)
                print(f'First image downloadable after {first_partial_wall_seconds}s (job: {job["status"]})', flush=True)
            message = f'{job["status"]}: {job["message"]}'
            if message != previous:
                print(message, flush=True)
                previous = message
            if job["status"] == "failed":
                raise RuntimeError(job.get("error"))
            if job["status"] == "completed":
                result = job["result"]
                if result["meta"].get("demo_mode") is not False:
                    raise RuntimeError("Real inference check returned demo output")
                output_dir = ROOT / "outputs" / "verification"
                output_dir.mkdir(parents=True, exist_ok=True)
                image = result["images"][0]
                response = client.get(image["url"])
                response.raise_for_status()
                output_path = output_dir / f'{args.report_name or f"{args.model}_{args.lora}"}.png'
                output_path.write_bytes(response.content)
                report = {"job_id": job_id, "wall_seconds": round(time.monotonic()-started, 2),
                          "first_partial_wall_seconds": first_partial_wall_seconds,
                          "meta": result["meta"], "image": image}
                output_path.with_suffix(".json").write_text(json.dumps(report, indent=2))
                print(json.dumps(report, indent=2), flush=True)
                print(f"Saved {output_path}", flush=True)
                return
            time.sleep(3)
        raise TimeoutError("Cloud inference did not finish in 30 minutes")

if __name__ == "__main__":
    main()
