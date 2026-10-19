# SDXL Img2Img Studio — Modal

Private image-to-image app using your own SDXL checkpoints and LoRAs. React UI,
FastAPI CPU gateway, and an on-demand NVIDIA L4 worker. No RunPod or local GPU.

## Included models

Configured from `/Users/mulenmara/CODE_DISK/models`:

- `checkpoints/Tuymans_SDXL.safetensors`
- `checkpoints/tuy_small.safetensors`
- `checkpoints/hofmann_SDXL.safetensors`
- `lora/lora_tuymans_SDXL.safetensors`
- `lora/lora_hofmann_SDXL.safetensors`

The upload script maps local `lora/` to cloud `loras/`. It excludes `.bak` files.
Only SDXL-compatible weights are supported. Models are not retrained.
The UI has two separate modes: trained checkpoint without LoRA, or official
SDXL Base 1.0 with a trained LoRA. The API rejects mixed trained-checkpoint/LoRA
combinations and requires a LoRA when using the base. Old saved LoRA presets
are migrated to the base-model mode when applied.

Download the base directly on Modal (not onto the Mac):
`.venv/bin/modal run scripts/download_sdxl_base.py`.
The script pins Stability AI's official checkpoint revision and verifies SHA-256
before committing it. Source: https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0
An optional faster migration from the existing R2 copies is available with
`.venv/bin/modal run scripts/import_models.py`. It verifies the full SHA-256 of
every cloud file against the local source before committing it.

## Setup and deploy

Run from this repository (Python 3.11 recommended). Modal currently requires a
payment method on the account before GPU functions can be deployed:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
.venv/bin/python scripts/prepare_modal.py
.venv/bin/modal token new
.venv/bin/python scripts/upload_models.py --dry-run
.venv/bin/python scripts/upload_models.py
npm run modal:deploy
```

Use the HTTPS URL printed by Modal. Web username/password are in the private,
Git-ignored `.modal-app-credentials.json` file. Never put this file in Git.
Deployment injects these values through a Modal Secret; they are not bundled in
frontend assets. The app provides a sign-in form and a signed HttpOnly/Secure
session cookie (30 days). HTTP Basic authentication is also supported for tools.
No separate frontend host or Vercel account is required.

## Architecture and cost control

- `modal_app.py`: deployable CPU web service and independent GPU function.
- Web routes require authentication, including gallery images and generation.
- Models live in `img2img-models` Volume (~26.69 GiB including SDXL Base).
- Gallery files/metadata live in `img2img-outputs` Volume.
- Jobs/progress live in a shared Modal Dict so CPU restarts do not lose them.
- Up to 10 independent L4 workers can process different input images concurrently,
  subject to the account GPU quota and available capacity. Each worker runs one
  input at a time; it scales to zero after a 20-second idle
  window. Browsing/polling never starts it. Starts and the idle window can be billed.
- Select 1–10 separate PNG/JPEG/WebP inputs (45 MiB total in the browser).
  Each input produces 1–4 variants independently: 10 inputs × 2 variants = 20
  outputs. Images are never combined into a composite input. The CPU API validates
  the entire batch and reserves the total output quota before submitting any GPU.
  Failed submissions refund only their own reservations; accepted jobs continue.
- Completed images are published immediately while the rest of the batch runs.
  A responsive output grid supports up to 40 result tiles and shrinks previews as
  the count increases; full resolution stays available when opened/downloaded.
- The right-hand progress bar shows aggregate live progress across input jobs,
  using the actual img2img denoising step count. Active jobs resume after reload.
- Optional quick preview uses 15 steps instead of the unchanged 25-step standard.
  Fewer steps can change quality. It does not replace your checkpoint or LoRA.
- Default monthly safety limit: 200 submitted output images, UTC calendar month.
  This is an application usage limit, NOT a dollar budget or a platform billing cap.
  Reservations persist in the separate `img2img-state` Volume even after weeks
  without access. Failed GPU jobs still consume reservations; failed submissions
  roll them back.
  To change it, edit `MONTHLY_IMAGE_LIMIT` in the local credential file and redeploy.
- Model storage remains allocated when GPU is off. Current advertised storage
  price beyond the currently included 1 TiB is $0.09/GiB/month; this model
  inventory fits within that included storage. Consult https://modal.com/pricing
  for current credits and billing rules. Credits are not a guarantee of zero charges.
- The first real generation may download/cache SDXL tokenizer/config assets from
  Hugging Face. Cold starts and checkpoint switches are slower than warm requests.
- Job records expire according to Modal Dict retention; completed images persist
  separately in the output Volume until deleted.

The pipeline uses an empty text prompt, matching the original workflow. Denoise,
checkpoint and LoRA control the appearance. Output scaling uses Lanczos, not AI
super-resolution. Inputs are normalized to at most 1536 px on the long side.

## Verification

```sh
npm test
npm run build:frontend
```

Tests cover authorization, input rejection before GPU allocation, shared job
state, quota reservation/rollback, worker error reporting, and persistent gallery
save/download/delete. Local worker tests use demo filters, not a real GPU.
A successful build/test does not verify CUDA inference; do a real checkpoint and
LoRA generation on Modal after upload/deployment.

For a local UI preview without GPU inference:

```sh
npm run build:frontend
.venv/bin/python -m uvicorn app_runtime.server:app --port 8000
```

Set `IMG2IMG_DEMO_MODE=true` for demo filters. Local preview is for development;
production always uses `app_runtime.cloud_server` and its authentication.
