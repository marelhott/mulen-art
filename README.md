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

Use the HTTPS URL printed by Modal. The deployed studio is public and does not
require a username or password. Anyone with the URL can access gallery images
and submit image-generation jobs charged to this Modal workspace. No separate
frontend host or Vercel account is required.

## Architecture and cost control

- `modal_app.py`: deployable CPU web service and independent GPU function.
- The production web app is intentionally unauthenticated; protect the URL if you need to restrict access.
- Models live in `img2img-models` Volume (~26.69 GiB including SDXL Base).
- Gallery files/metadata live in `img2img-outputs` Volume.
- Jobs/progress live in a shared Modal Dict so CPU restarts do not lose them.
- Up to 10 independent L4 workers can process different input images concurrently,
  subject to the account GPU quota and available capacity. Each worker runs one
  input at a time; it scales to zero after a 20-second idle
  window. Browsing/polling never starts it. Starts and the idle window can be billed.
- Input count, variants per input and monthly output count have no application cap.
  Inputs remain independent; there are no composite inputs. The browser sends small
  transport batches, and each output has its own GPU job. The worker concurrency
  setting (10), account capacity, billing limits and per-request byte/time limits
  still apply; large batches queue instead of increasing one worker's duration.
- Monthly reservations remain as usage telemetry only. There is no production
  `MONTHLY_IMAGE_LIMIT`; `/api/usage` reports `limit: null`.
- Completed images appear while the rest of the batch runs. The gallery renders
  incrementally while scrolling, with automatic or manually adjusted thumbnail
  size, multi-selection, ZIP export and reuse of an output as an input.
- The Mulen Nano design uses the same local Hanken Grotesk / Instrument Serif
  fonts, moss colors, panel gradients, rounded cards, hover tools, dark/light
  switch, range controls and slim live progress bars. The viewer includes
  arrow navigation, Escape, zoom/pan and input/output comparison via slider.
  New jobs retain authenticated source images for comparison after reload;
  older outputs without retained sources cannot show comparison.
- The right progress bar uses real GPU steps, not a simulated countdown.
  Active and last submitted jobs resume after reload. The history has no 20-image cap.
- Quick preview uses 15 steps rather than the 25-step standard; fewer steps can
  change quality. It does not replace the checkpoint or LoRA.
- Failed submissions do not consume usage reservations. Accepted jobs continue
  if another submission fails; generation requests are never automatically retried.
- Model storage remains allocated when GPU is off. Current advertised storage
  price beyond the currently included 1 TiB is $0.09/GiB/month; this model
  inventory fits within that included storage. Consult https://modal.com/pricing
  for current credits and billing rules. Credits are not a guarantee of zero charges.
- The first real generation may download/cache SDXL tokenizer/config assets from
  Hugging Face. Cold starts and checkpoint switches are slower than warm requests.
- Job records expire according to Modal Dict retention; completed images persist
  separately in the output Volume until deleted.

## Canvas and saved library

Generated outputs automatically appear in both persistent canvas history and the library,
including outputs previously left unsaved. Trash is available on both surfaces and in bulk
selection. Deletion hides an image from both indexes with a durable metadata tombstone;
files remain recoverable through explicit API save. Polling cannot restore deleted cards.
Single click opens the viewer; clicking the enlarged image closes it.

## Adding work while generating

Generate becomes “Přidat do fronty” while jobs run. Inputs and settings remain editable;
every click captures its own batch and appends accepted jobs without replacing earlier
ones. Uploads may overlap, aggregate progress includes all accepted/pending submissions,
and accepted job IDs persist across reloads. There is no application-level queue count
cap; Modal GPU concurrency and account usage limits still apply.

## Input enlargement

`input_scale` (default 1, up to 4) performs one Lanczos resize before diffusion,
aligning dimensions to 8px and preserving the existing 1536px long-side ceiling.
This can change the model result and GPU time. The separate output `scale` resizes
the completed image after diffusion. Both values are captured per queued batch;
input scale is included in presets and output metadata. Default 1 preserves prior sizing.

## Studio output enlargement

The studio always uses the original single-pass schedule (`quick`), with original 1536px
input normalization and SDE as default sampler. Enlarging the completed output uses only
Lanczos interpolation. Old presets cannot re-enable full steps or a second diffusion pass.
Detail/full-step API modes below remain internal diagnostics, not studio controls.

## Generation controls

- Original (UI default, internal `quick`): SDE DPM++ 2M, Karras, original schedule-based step budget (e.g. 25 × 0.45 = 11 denoising steps).
  Blank negative prompts use the original SDXL zero conditioning. Enlarging uses Lanczos.
- Full steps (optional): preserves the requested number of actual denoising steps.
  The schedule length is ceil(steps / denoise); effective strength is recorded because
  discretization slightly changes it.
  This is a Diffusers implementation, not a claim of pixel-identical Forge sampling.
- Detail: full first pass, Lanczos enlargement, then another SDXL img2img pass with the
  same checkpoint/LoRA. Defaults: 15 detail steps at 0.25 denoise. This can change texture
  and composition, and consumes more GPU time. First-pass long side is capped at 1024,
  scale at 2×, so second-pass long side is at most 2048. VAE tiling reduces memory use;
  this is not tiled UNet diffusion. No refiner or third-party upscaler is substituted.
- DPM++ 2M uses dpmsolver++ order 2; DPM++ 2M SDE is a separate choice. Karras applies
  only to these two. Euler a and DDIM use their supported normal schedule.
- Single-pass resolution: selectable 1024/1536/2048 maximum long side; small sources are
  not enlarged before the first pass. Default output enlargement remains 2×.
- Seed −1 is random. A fixed unsigned 32-bit seed increments across variants; independent
  inputs intentionally reuse the same variant seeds for comparison. No guarantee of
  identical noise across Forge, different hardware or dependency versions.
- The studio generates without text prompts, including when restoring old presets.
  It uses the original zero negative conditioning for empty negative prompts, independently
  of render mode. Internal API conditioning comparison remains available for diagnostics.
- Each output retains its own seed, actual step counts, effective strengths and sizes in
  library JSON and embedded PNG metadata (`sdxl_studio` plus common `parameters` fields).
  Old saved presets restore quick/SDE behavior; new presets retain all engine controls.

Rollback before these changes: Git tag `studio-before-detail-engine-2026-10-19`.

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
production uses `app_runtime.cloud_server`; the Modal deployment explicitly disables app-level authentication.

## Návrat k předchozímu vzhledu

Původní nasazená verze je commit `d292249`, označený tagem
`studio-before-mulen-nano-2026-10-19`. Nová verze vzniká na větvi
`codex/mulen-nano-studio`. Pro samostatnou obnovu bez změny rozpracovaných souborů:

```sh
git worktree add ../img2img-original studio-before-mulen-nano-2026-10-19
```

V obnoveném checkoutu je nutné znovu připravit ignorované závislosti a přihlašovací
soubor a spustit `npm run modal:deploy`. Tag vrací také tehdejší limity; pokud je
nechceš obnovit, vrať pouze frontendové soubory z tagu.
