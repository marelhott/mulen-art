"""Create local-only web credentials without printing the password.

The file is shaped for `modal secret create img2img-auth --from-json <file>`.
Older files using APP_USERNAME/APP_PASSWORD are migrated in place, keeping the password.
"""
import json
import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
path = root / ".modal-app-credentials.json"
if path.exists():
    current = json.loads(path.read_text())
    if "APP_PASSWORD" in current and "STUDIO_PASSWORD" not in current:
        # The old default monthly cap was never applied in production; leaving it out keeps "no limit".
        migrated = {"STUDIO_USERNAME": current.get("APP_USERNAME", "studio"),
                    "STUDIO_PASSWORD": current["APP_PASSWORD"]}
        path.write_text(json.dumps(migrated, indent=2))
        os.chmod(path, 0o600)
else:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"STUDIO_USERNAME": "studio", "STUDIO_PASSWORD": secrets.token_urlsafe(24)}, stream, indent=2)
print(f"Web credentials ready in {path.name} (private, ignored by Git).")
