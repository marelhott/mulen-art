"""Create local-only web credentials without printing the password."""
import json
import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
path = root / ".modal-app-credentials.json"
if not path.exists():
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"APP_USERNAME": "studio", "APP_PASSWORD": secrets.token_urlsafe(24),
                   "MONTHLY_IMAGE_LIMIT": "200"}, stream, indent=2)
print(f"Web credentials ready in {path.name} (private, ignored by Git).")
