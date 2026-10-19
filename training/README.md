# Private SDXL training on Modal

This training workflow is independent of the deployed img2img app. It never changes the active model or overwrites the existing Dreamlook checkpoints.

- `prepare_dataset.py` uses the reviewed local manifest in `outputs/research/tuymans/review-candidates.json`; it produces dataset-v2, paired content captions, a held-out split, and an exclusion manifest. Embedded color profiles are converted to sRGB. No AI upscaling, sharpening, color augmentation, or aspect-ratio stretching is used. Originals are not modified.
- `../training_modal.py` pins kohya sd-scripts commit `04ca541746b7667b27eab230db067579f682895e`. A bounded LoRA or full UNet run saves configurations, environment, checkpoints, resumable state and timing on private Modal volumes. Full training requires 12 generic base-SDXL regularization paintings. These are ordinary replay samples at approximately 3% frequency, not an asserted per-image loss weighting. The pinned `sdxl_train.py` does not apply the dataset's `loss_weights` in its loss calculation, so `is_reg` / `prior_loss_weight` is deliberately not used for this full-training configuration.
- `evaluate_modal.py` evaluates empty-prompt img2img at the app's scheduler, conditioning and defaults, with fixed sources and seed. Full checkpoints also receive six content-only text tests with the style trigger. These text tests are supplemental; promptless img2img is the primary target.
- `evaluate_modal.py --watch-run RUN_ID` coordinates checkpoint evaluations entirely on Modal, independently of the Mac. `finish_run.py RUN_ID` waits for that cloud pipeline, downloads samples and the latest candidate, and verifies the downloaded safetensors header and SHA256. It does not select the best artistic result automatically. The Mac performs file I/O and coordination only, not training or inference.

## Completed pilot

`lora64-pilot-20261019T163003Z`: 300 optimizer steps, effective batch 4, rank 64 / alpha 32, LR 5e-5, BF16, 15% caption dropout, 95 training images. Finished in 1312.11 seconds. Estimated compute at the checked base GPU/CPU/RAM rates: USD 1.1658; not an invoice. The pilot used dataset-v1, before correcting embedded wide-color profiles on two source images.

Reference comparison: six private app inputs, seeds 231019, 28 scheduler steps, DPM++ 2M Karras, CFG 1.8, empty positive prompt and `negative_prompt=None`, strengths .52 and .70. No super-resolution or detail-enhancement second pass. There are 14 actual denoising steps at .52 and 19 at .70, matching the app's quick schedule semantics.

## Commands

From the repository root:

```sh
.venv/bin/python training/prepare_dataset.py
.venv/bin/modal run --detach training/evaluate_modal.py --regularization
.venv/bin/modal run --detach training_modal.py --kind full --steps 1200 --learning-rate 0.000004
.venv/bin/modal run --detach training/evaluate_modal.py --watch-run full-unet-YYYYMMDDTHHMMSSZ
.venv/bin/python training/finish_run.py full-unet-YYYYMMDDTHHMMSSZ
```

Run the cloud coordinator only once per training run to avoid duplicate paid evaluations. It has no automatic paid-job retry. Before a new training experiment, choose a bounded configuration based on visual results rather than assuming that more steps, lower loss, more detail, or higher resolution improves the style.
