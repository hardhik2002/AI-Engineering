# Local model setup

## Optional OpenAI vision (Phase 5)

Install the `openai` extra with `python -m pip install -e '.[openai]'`, set `OPENAI_API_KEY` only in `backend/.env`, and restart. The default `OPENAI_VISION_MODEL=gpt-5.4-mini` uses the [Responses API](https://developers.openai.com/api/docs/guides/images-vision) with [Pydantic structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs). This model supports image input and structured outputs according to its [official model page](https://developers.openai.com/api/docs/models/gpt-5.4-mini). No key is required for local models or decorative alt text.

`OPENAI_VISION_DETAIL` is `auto`, `low`, or `high`; `OPENAI_TIMEOUT_SECONDS` defaults to 90; `OPENAI_MAX_OUTPUT_TOKENS` to 600; `OPENAI_MAX_CONCURRENCY` to 2; and `VISIONLAB_OPENAI_MAX_IMAGE_SIDE` to 1600. A request resizes the validated image, strips metadata, and sends a JPEG data URL. Responses use `store=False`, retry transient failures at most twice, and record only actual usage returned by the API. Model output may be wrong; grounding status is the model's assessment, not independent visual verification. Live verification requires an explicitly configured key and opt-in.

## Florence-2 (Phase 4)

Install with `python -m pip install -e '.[dev,vision,caption]'`, then run `python -m app.scripts.install_florence` from `backend/`. The installer downloads [florence-community/Florence-2-base-ft](https://huggingface.co/florence-community/Florence-2-base-ft) at pinned revision `0b03b6f15a4a211370fb204aee4e7dd48887ea37` into ignored `data/models/florence2/` and writes a revision manifest. Runtime loading uses native `Florence2ForConditionalGeneration` and `AutoProcessor` with `trust_remote_code=False` and local files only. Verified here with PyTorch `2.15.0+cpu`, Transformers `4.57.6`, Ultralytics `8.4.193`, and safetensors `0.8.0`. The weight file is about 463 MB. CPU uses float32; CUDA, when configured and available, uses float16.

The model loads lazily once per API process and runs behind a one-request semaphore. `VISIONLAB_FLORENCE_DEVICE` is `cpu` by default (`auto` or `cuda` are optional). `VISIONLAB_FLORENCE_MAX_NEW_TOKENS=512`, `VISIONLAB_FLORENCE_NUM_BEAMS=1`, `VISIONLAB_FLORENCE_MAX_REGIONS=30`, and `VISIONLAB_FLORENCE_MAX_SOURCE_SIDE=2048` bound generation and output. Model status distinguishes not installed, installed but unloaded, loading, ready, and error. API requests never download weights. On this Windows CPU, the first model load and each generation take seconds; timings vary by input and task. Dense regions may legitimately be empty. Transformers `4.57.6` expects adjacent `<loc_...>` tokens while this checkpoint generates whitespace between them; VisionLab removes only that separator whitespace before calling `post_process_generation()`.

## YOLO26 Nano (Phase 3)

Phase 3 uses Ultralytics `yolo26n.pt` for image object detection. Installation is explicit, and the API never downloads weights during a request. The model file is stored at `backend/data/models/yolo26n.pt` by default; `backend/data/` is ignored by Git.

From `backend/` on Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[dev,vision]'
.\.venv\Scripts\python.exe -m app.scripts.install_model
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --no-access-log --host localhost --port 5200
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
