"""Vari (image variations, Next.js) on Modal, next to the Mulen art studio.

Deploy (from the repo root): MODAL_PROFILE=img2img .venv/bin/python -m modal deploy Vari/modal_vari.py

Secrets (created by the owner, values never stored in the repo):
  vari-keys    FAL_KEY, REPLICATE_API_TOKEN, OPENAI_API_KEY, GEMINI_API_KEY,
               R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET  (+ optional R2_PUBLIC_URL)
  img2img-auth STUDIO_USERNAME, STUDIO_PASSWORD (already used by the studio; Vari reuses the sign-in)
"""
import os
import subprocess
from pathlib import Path

import modal

app = modal.App("vari")
HERE = Path(__file__).parent
PORT = 3000

image = (
    modal.Image.from_registry("node:22-slim", add_python="3.11")
    .add_local_dir(
        str(HERE), "/app", copy=True,
        ignore=["**/node_modules", "**/.next", "**/.next-build", "public/outputs", ".env", ".env.*", "modal_vari.py", "**/__pycache__"],
    )
    .workdir("/app")
    # devDependencies are needed for the build, so NODE_ENV is not set until `next start` sets it.
    .run_commands("npm ci", "npm run build")
)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("vari-keys"), modal.Secret.from_name("img2img-auth")],
    min_containers=0,
    max_containers=3,
    scaledown_window=300,
    # /api/generate is synchronous: fal waits up to 5 minutes per repeat.
    timeout=1800,
)
@modal.concurrent(max_inputs=20)
@modal.web_server(PORT, startup_timeout=90)
def web():
    # Bind explicitly: never rely on the default host of `next start`.
    subprocess.Popen(
        ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", str(PORT)],
        cwd="/app", env={**os.environ, "NEXT_DIST_DIR": ".next-build"},
    )
