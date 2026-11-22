#!/Users/mulenmara/.local/share/fal-cli/bin/python3.14

import json
import sys

import fal.apps


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        model_id = payload.pop("_model_id", "fal-ai/qwen-image-2/edit")
        repeat = int(payload.pop("_repeat", 1))
        images = []
        last_result = {}

        for _ in range(max(1, repeat)):
            handle = fal.apps.submit(model_id, payload)
            result = handle.get()
            last_result = result

            if isinstance(result, dict) and isinstance(result.get("images"), list):
                images.extend(result["images"])
            elif isinstance(result, dict) and isinstance(result.get("image"), dict):
                images.append(result["image"])

        if images:
            last_result["images"] = images

        json.dump(last_result, sys.stdout)
        return 0
    except Exception as exc:  # noqa: BLE001
        json.dump({"error": str(exc)}, sys.stdout)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
