# Vari

Image variations (Next.js 15). Part of the Mulen art repo; the studio has a **VARI** tab that opens it.

## Hosting: Modal (replaces Railway)

Vari runs as its own Modal app (`vari`, file `modal_vari.py`) next to the studio (`img2img-studio`).

```sh
# once: secret with the provider keys (values are yours; the repo never contains them)
.venv/bin/python -m modal secret create vari-keys \
  FAL_KEY=... REPLICATE_API_TOKEN=... OPENAI_API_KEY=... GEMINI_API_KEY=... \
  R2_ACCOUNT_ID=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... R2_BUCKET=... [R2_PUBLIC_URL=...]

# deploy Vari, then redeploy the studio so its VARI tab knows the address
MODAL_PROFILE=img2img .venv/bin/python -m modal deploy Vari/modal_vari.py
VARI_URL=https://<workspace>--vari-web.us-east.modal.run MODAL_PROFILE=img2img npm run modal:deploy
```

- **Sign-in:** every request needs HTTP Basic auth with the studio credentials (Modal secret `img2img-auth`:
  `STUDIO_USERNAME` / `STUDIO_PASSWORD`). Without them Vari answers 503. `next dev` skips the check.
- **Storage:** in production images always go to R2 (`NODE_ENV=production`), so the R2 variables are required.
- **Long requests:** `/api/generate` is synchronous. Modal cuts web requests at 150 s but answers with a 303
  redirect that browsers follow (about 50 minutes in total), so same-origin fetches keep working.
- `STABILITY_API_KEY` from the old `.env.example` is not used by the code. `GEMINI_API_KEY` and `OPENAI_API_KEY` are.
- The old Railway setup (`DEPLOY.md`) is kept for reference only.

---

# Variants

Web app for generating sibling image variants from one source image.

The goal is not a filter, restoration, or photorealistic cleanup. The app is built for generating "another shot from the same series":

- same atmosphere
- related palette
- related composition family
- preserved ambiguity and defects
- but still a different image

## What The App Does

The UI lets you:

- upload one source image
- choose one main engine for direct generation
- choose a "distance from original" mode
- choose the number of variants
- run one engine or run multiple engines at once with `generovat všechno`
- open a separate `batch` page for long-running multi-input generation
- review generated outputs in the main grid
- open results larger, download them, and browse them later in the gallery

## Core Principle

This project is tuned for artistic source images where the input may already contain:

- blur
- painterly defects
- unresolved anatomy
- ambiguous forms
- damaged texture
- non-literal shapes

The prompts and negative prompts are intentionally biased against:

- photorealistic cleanup
- face restoration
- beauty retouch
- literal humanoid reconstruction
- "fixing" the image into realism

## Engines

The app currently supports seven generation engines:

### 1. `comfy-unclip`

This is a ComfyUI workflow executed on Replicate.

What it uses:

- SD 1.5 checkpoint
- IPAdapter
- positive/negative prompt control
- exposed UI controls for:
  - `noise augmentation`
  - `strength`

Why it exists:

- fastest engine in the stack
- good for "same world / same series" sibling variants
- useful when speed matters more than strict fidelity

Important detail:

- IPAdapter CLIP vision tends to crop non-square images badly
- the app now preprocesses the source into a square reference without hard center-cropping, to preserve more of the original composition
- comfy internal generation resolution is pushed higher than before to recover more detail

### 2. `sd-variation`

Replicate model:

- `lambdal/stable-diffusion-image-variation`

Why it matters:

- typically preserves image detail better than comfy or unCLIP
- often gives the strongest "same image family, but not identical" result

Known behavior:

- slower than comfy
- earlier it could fail on RGBA PNG inputs; the app now normalizes inputs to RGB PNG before sending them

### 3. `unclip`

Replicate model:

- `cjwbw/stable-diffusion-2-1-unclip`

Why it exists:

- looser semantic variation
- can produce interesting alternate interpretations while still staying anchored to the input

Important limitation:

- this model does not expose a direct output resolution parameter in the current integration
- the app gives it full normalized input resolution and increased inference steps, but its detail ceiling is still more model-limited than `sd-variation`

### 4. `qwen`

fal.ai model:

- `fal-ai/qwen-image-2/edit`

Why it exists:

- stronger fal-based alternative now that BRIA was removed from the app
- useful when you want a more assertive reinterpretation path than the Replicate variation models

### 5. `stable`

fal.ai model:

- `fal-ai/stable-diffusion-v3-medium/image-to-image`

Why it exists:

- additional image-to-image path with different texture/detail behavior

### 6. `ip-adapter-sdxl`

Replicate model:

- `chigozienri/ip_adapter-sdxl`

Why it exists:

- this is the first added SDXL-class image-first adapter path in the app
- unlike normal img2img, it can run with an empty prompt and use the source image as the primary conditioning signal
- it is the closest currently working public provider path to the "reimagine what you see" behavior that the project is chasing

Important detail:

- the prompt is intentionally left blank in this integration
- the only exposed variation comes from the source image plus engine-specific scale and step settings
- `scale` is mapped from the distance preset: higher scale stays closer, lower scale allows more re-composition

### 7. `sdxl-artistic`

fal.ai model:

- `fal-ai/fast-sdxl/image-to-image`

Why it exists:

- experimental comparison engine against `sd-variation`
- tuned intentionally away from default photorealistic SDXL behavior
- kept as a side option, not the primary recommendation

Important tuning:

- lower CFG than a standard SDXL photo workflow
- no prompt expansion
- hard negative prompt against realistic people, anatomy repair, and portrait cleanup
- preserve-aspect-ratio enabled

## Investigated But Not Active

Some candidate engines were researched and deliberately not wired into the live app yet:

- `Stable Cascade` on currently reachable fal.ai and Replicate endpoints appears to be publicly exposed as text-to-image rather than image-first variation in the forms we checked
- `Stability Reimagine` was tested against the expected API path with a valid `STABILITY_API_KEY` and still returned `404`, so it was not added as a fake/broken option in the UI

The app only exposes engines that have a concrete provider path behind them.

## Environment

Current provider secrets used by the app may include:

- `REPLICATE_API_TOKEN`
- `FAL_KEY`
- `STABILITY_API_KEY` for future Stability experiments
- `R2_*` variables for shared output storage

## Distance Modes

The app exposes four distance presets:

- `locked`
- `sibling`
- `looser`
- `new-frame`

These do not simply change one denoise-like knob. Internally they affect engine-specific prompt and sampling behavior.

Examples:

- comfy changes `noise`, `strength`, `cfg`, and step count
- fal-backed engines change prompt framing, guidance, and strength
- replicate engines change inference steps and guidance where available

## How Generation Works

### Single-engine generation

`generovat`

- runs the selected main engine only
- returns the requested number of images

### Multi-engine generation

`generovat všechno`

- runs all enabled engines from the model list
- each enabled engine generates two outputs
- results are shown with per-tile method/settings labels
- failures are isolated per engine so one broken or slow engine does not block the whole batch

This matters because different providers have very different latency and failure modes.

### Long Batch Page

`/batch`

- accepts up to 20 source images in one run
- uses one selected engine and one selected distance preset across the whole batch
- generates 2 to 4 outputs per input image, so 20 inputs can become 40 to 80 outputs
- renders results in a large scrollable gallery of small aspect-ratio-preserving thumbnails
- opens the full image on click

## Why Some Engines Look Softer Than Others

That is mostly real, not imagined.

Current observed pattern:

- `sd-variation` usually keeps the best detail
- `comfy-unclip` is faster, but historically looked softer because of lower internal resolution and reference cropping
- `unclip` is semantically interesting but has a lower detail ceiling than `sd-variation`

Recent improvements already added:

- RGB normalization for provider compatibility
- better comfy reference preprocessing for non-square sources
- higher comfy internal resolution
- more comfy sampling steps
- higher unCLIP inference steps
- parallelized batch generation with engine-level failure isolation
- strict output aspect-ratio enforcement based on the input image

## Aspect Ratio Handling

All engines are now forced to respect the source image aspect ratio at the app level.

This is important because providers do not all expose the same size controls, and some of them drift away from the input ratio.

Current approach:

- the source image dimensions are measured on upload
- providers generate as usual
- before the generated image is stored, the app re-normalizes the output to the input aspect ratio
- this happens uniformly for both direct generation and async Replicate jobs

The adjustment is designed to preserve the generated image rather than hard-crop it:

- blurred background fill
- contained foreground image
- same final ratio as the source

So the app keeps composition continuity without introducing abrupt center crops

## Reliability And Batch Behavior

The app is built to survive mixed provider behavior.

Current behavior:

- `generovat` runs one selected engine
- `generovat všechno` runs enabled engines in parallel
- each engine fills its own two output slots
- one engine failure no longer blocks the rest of the batch
- long-running requests are guarded by client-side timeout handling

This matters because:

- Replicate models usually return quickly with async job ids
- fal.ai models can still be slower or inconsistent in response shape than the Replicate-backed engines
- some engines may fail on certain source image conditions

The UI now keeps per-tile status more truthfully:

- pending
- generated
- failed

## Storage

The app is designed for cloud use across devices.

### Production storage

Cloudflare R2

- generated images are uploaded to R2
- gallery reads from R2
- delete removes the object from R2

### Development fallback

If R2 is not enabled locally, the app can fall back to:

- `public/outputs`

## Gallery

The gallery is a separate page that:

- lists all generated images
- opens images larger
- allows download
- allows delete

## UI Notes

The app includes:

- dark and light theme toggle
- main generation grid
- gallery page
- per-tile method/settings labels
- favicon and project icon wiring

## Stack

- Next.js App Router
- TypeScript
- Tailwind CSS
- Railway for hosting
- Cloudflare R2 for storage
- Replicate for Comfy/IPAdapter and variation models
- fal.ai for qwen/stable image-to-image models
- `sharp` for image preprocessing and normalization

## Deployment

The project is currently set up for Railway.

Important files:

- `railway.json`
- `.railwayignore`
- `.env.example`
- `DEPLOY.md`

## Required Environment Variables

```bash
REPLICATE_API_TOKEN=
FAL_KEY=

STORAGE_DRIVER=r2
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=variants
R2_PUBLIC_URL=
```

## Project Structure

```text
app/
  api/
    gallery/
    generate/
  gallery/
  layout.tsx
  page.tsx
lib/
  storage.ts
public/
  favicon.svg
  outputs/
README.md
DEPLOY.md
railway.json
```

## Current Practical Notes

- `sd-variation` is still the best detail-preserving engine in the current mix
- `comfy-unclip` is the fastest engine and now tuned to preserve more composition/detail than before
- `unclip` is useful, but should be treated more as a semantic variation engine than as the detail champion
- `qwen` and `stable` depend on fal.ai responses and may vary more in speed and reliability than the Replicate-backed engines

## Suggested Direction For Future Improvement

If the project keeps evolving, the next meaningful upgrades would be:

- replace the current comfy SD1.5 path with a stronger detail-preserving workflow
- add a dedicated high-detail "quality mode"
- store per-image provider metadata more structurally
- add favorites / tagging in the gallery
- add engine benchmarking in the UI
