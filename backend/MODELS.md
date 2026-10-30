# YOLO26 Nano setup

Phase 3 uses Ultralytics `yolo26n.pt` for image object detection. Installation is explicit, and the API never downloads weights during a request. The model file is stored at `backend/data/models/yolo26n.pt` by default; `backend/data/` is ignored by Git.

From `backend/` on Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[dev,vision]'
.\.venv\Scripts\python.exe -m app.scripts.install_model
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host localhost --port 5200
```

On CPU-only systems, use `VISIONLAB_DETECTION_DEVICE=cpu` or `auto` in `.env`. `auto` selects CUDA only when PyTorch reports that it is available. Explicit `cuda` with no supported GPU returns `device_unavailable`; it does not silently change device. The model is loaded lazily on the first analysis and cached for the process lifetime. Restarting the API reloads it from the local weight file. The first request can take several seconds on CPU. The model status API reports `not_installed`, `unavailable` (installed but not loaded, or unsupported device), `loading`, `ready`, or `error` and never reports `ready` before a successful load.

| Setting | Default | Meaning |
| --- | --- | --- |
| `VISIONLAB_MODEL_ROOT` | `data/models` | Ignored model cache |
| `VISIONLAB_DETECTION_MODEL` | `yolo26n.pt` | Only accepted model name in Phase 3 |
| `VISIONLAB_DETECTION_DEVICE` | `auto` | `auto`, `cpu`, or `cuda` |
| `VISIONLAB_DETECTION_CONFIDENCE` | `0.25` | Default inference score threshold |
| `VISIONLAB_DETECTION_IOU` | `0.45` | Default overlap suppression threshold |
| `VISIONLAB_DETECTION_IMAGE_SIZE` | `640` | Ultralytics inference image size |
| `VISIONLAB_DETECTION_MAX_DETECTIONS` | `100` | Maximum model detections per image |
| `VISIONLAB_DETECTION_CONCURRENCY` | `1` | Concurrent analysis capacity, 1–4 |
| `VISIONLAB_DETECTION_MAX_SOURCE_SIDE` | `2048` | Maximum decoded side before model input |

The server validates configuration ranges at startup. Client requests can override the four inference parameters, while display threshold, classes, and layer switches only filter stored results. CPU inference uses PyTorch, TorchVision, NumPy, Pillow, and Ultralytics. The Ultralytics package currently installs OpenCV as a dependency; VisionLab does not invoke OpenCV for this phase.

The pretrained model predicts COCO object categories. It cannot provide captions, OCR, relationships, activities, or all possible objects. A low score is not a calibrated probability. For reproducibility, saved results include the model name, YOLO26 version, Ultralytics package version, device, weight SHA-256 digest, parameters, and timing. Model weights downloaded today may differ from future releases; use the digest to identify the exact file.

Ultralytics describes [AGPL-3.0 and Enterprise licensing options](https://docs.ultralytics.com/help/quickstart/#ultralytics-license). Review the license and any obligations before using this code or the model in a distributed or hosted product. See the [YOLO26 model guide](https://docs.ultralytics.com/models/yolo26/) and [prediction arguments](https://docs.ultralytics.com/modes/predict/).
