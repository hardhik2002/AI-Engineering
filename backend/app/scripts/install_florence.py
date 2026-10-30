"""Download one pinned Florence checkpoint into ignored local model storage."""

import json
import sys

from app.core.config import get_settings


def main() -> int:
    settings = get_settings()
    target = (settings.model_root / "florence2").resolve()
    manifest = target / "visionlab-model.json"
    expected = {"checkpoint": settings.florence_checkpoint, "revision": settings.florence_revision}
    if (target / "model.safetensors").is_file() and manifest.is_file():
        if json.loads(manifest.read_text(encoding="utf-8")) == expected:
            print("Pinned Florence-2 checkpoint is already installed.")
            return 0
    target.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=settings.florence_checkpoint,
            revision=settings.florence_revision,
            local_dir=target,
            allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model"],
            ignore_patterns=["*.bin"],
        )
        if not (target / "model.safetensors").is_file():
            raise RuntimeError("Checkpoint weights were not downloaded")
        manifest.write_text(json.dumps(expected), encoding="utf-8")
    except Exception as exc:
        print(f"Florence-2 installation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Installed {settings.florence_checkpoint} at revision {settings.florence_revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
