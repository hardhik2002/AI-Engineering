"""Explicitly install the single approved model into the local ignored model directory."""

import sys

from app.core.config import get_settings


def main() -> int:
    settings = get_settings()
    target = (settings.model_root / settings.detection_model).resolve()
    if target.is_file():
        print(f"Model already installed: {target}")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        from ultralytics import YOLO

        YOLO(str(target))
    except Exception as exc:
        print(f"Model installation failed: {exc}", file=sys.stderr)
        return 1
    if not target.is_file():
        print("Model installation did not create the expected weights file.", file=sys.stderr)
        return 1
    print(f"Installed {settings.detection_model}: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
