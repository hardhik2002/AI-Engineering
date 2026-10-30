# VisionLab AI

A local computer vision workstation for learning five AI-103 image-understanding capabilities. **Phase 5 (B5 + F5)** adds optional OpenAI image Q&A and accessible descriptions, while local YOLO and Florence inference remain available. Video inference remains planned.

## Run locally

Prerequisites: Python 3.12, Node.js 20.19+ or 22.12+, npm, and FFprobe for video uploads. FFmpeg enables video poster thumbnails and is recommended. Use two PowerShell terminals.

**Backend — http://localhost:5200**

```powershell
cd backend
Copy-Item .env.example .env
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev,vision,caption,openai]'
.\.venv\Scripts\python.exe -m app.scripts.install_model
.\.venv\Scripts\python.exe -m app.scripts.install_florence
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --no-access-log --host localhost --port 5200
```

If `py -3.12` is unavailable, run `py -0p` and select an installed Python 3.12 runtime. On this workstation, `py -V:Astral/CPython3.12.15 -m venv .venv` works. With uv installed, `uv venv --python 3.12 --seed .venv` also creates a pip-ready environment. On macOS/Linux, use `python3.12 -m venv .venv` and `.venv/bin/python`.

**Frontend — http://localhost:5180**

```powershell
cd frontend
Copy-Item .env.example .env
npm ci
npm run dev
```

Open [http://localhost:5180](http://localhost:5180). Interactive API documentation is at [http://localhost:5200/docs](http://localhost:5200/docs), with the media contract in [backend/API.md](backend/API.md). The frontend reads `VITE_API_BASE_URL`, defaulting to `http://localhost:5200`.

### FFmpeg and FFprobe

Install a current build from the [official FFmpeg download page](https://ffmpeg.org/download.html). On Windows, follow its Windows EXE build link, extract the archive, and add its `bin` directory to `PATH`. On macOS, `brew install ffmpeg` is a common option. On Debian/Ubuntu, `sudo apt install ffmpeg` installs both commands. Restart the terminal and verify:

```powershell
ffprobe -version
ffmpeg -version
```

The binaries can also be set explicitly with `VISIONLAB_FFPROBE_BINARY` and `VISIONLAB_FFMPEG_BINARY` in `backend/.env`. Missing FFprobe gives a clear `503` error for video upload. Without FFmpeg, video metadata can still be stored but no poster thumbnail is generated.

## Phase 5 image Q&A and accessibility

The OpenAI SDK is optional. To enable cloud vision, add `OPENAI_API_KEY` to **backend/.env** and restart FastAPI. The default model is `gpt-5.4-mini`; set `OPENAI_VISION_MODEL` to another vision-capable Responses model if needed. Never put the key in `frontend/.env` or a `VITE_` variable. Without a key, image upload, YOLO detection, Florence captions, decorative `alt=""`, and saved Florence caption suggestions still work.

In **Visual Q&A**, select an uploaded image, tick the image-specific consent box, and ask a question. Follow-ups reuse up to eight previous messages and the same validated image. Conversations persist in SQLite, can be reopened or cleared, and display model-assessed grounding, uncertainty, latency, and token usage when returned. The provider reports `configured` until a real successful response; `available` never means that a test mock or mere key presence proved cloud access. Answers are model assessments and should be reviewed against the displayed image.

In **Accessibility**, choose informative, functional, complex, or decorative purpose and supply usage context. Decorative creates empty alt text locally without an API call. Other purposes can use OpenAI after consent, or start from a previously saved Florence caption as an explicitly labeled suggestion. Generated text and user edits are saved separately; choose a saved result to edit, copy alt text, or preview its screen-reader wording. Descriptions do not invent object coordinates. Uploaded video remains viewable, while Q&A and descriptions require an image in this phase.

Cloud requests send a resized, EXIF-oriented JPEG with metadata removed, not the original file. A bounded semaphore limits concurrent calls; there is no automatic cloud call on upload or navigation. OpenAI request storage is disabled with `store=False`. Review the [API contract](backend/API.md) and [model notes](backend/MODELS.md).

Automated tests mock the provider and make no paid request. The single live smoke test runs only when both `RUN_LIVE_OPENAI_TESTS=1` and a valid `OPENAI_API_KEY` are present in the shell environment.

## Phase 4 Florence-2 captions and regions

In **Image Captioning**, select an uploaded image, choose Short, Detailed, or Extended, then generate a caption. Generate Dense Regions to draw the model's boxes over the same image. Select a region in the image or inspector to read its full description; the region overlay can be hidden independently. Saved caption runs reopen after refresh. In **Objects & regions**, run YOLO detection, select a box, and choose **Describe Selected Object** to caption its validated crop. Florence text is separate from YOLO's confidence score. Empty dense-region output is a valid model result.

The model installs explicitly and runs locally on CPU by default. The first request loads its roughly 463 MB checkpoint; subsequent requests reuse it. See [Florence setup](backend/MODELS.md), [API contract](backend/API.md), and [architecture](docs/ARCHITECTURE.md). Florence generation can take several seconds on this CPU. No model is downloaded during an API request.

## Phase 3 image detection

- In **Image Analysis** or **Objects & regions**, select an uploaded JPEG, PNG, or WebP and choose **Analyze Image**. YOLO26 Nano returns real class labels, scores, and boxes. Results are saved in SQLite and reopen after refresh.
- The inspector shows object counts, class distribution, timing, model metadata, saved runs, and normalized and pixel coordinates. Select an object from its box or list and use Previous/Next for navigation.
- Display confidence and class filters, box/label/score switches, and reset controls change only the view. Inference confidence and IoU are separate; **Re-run Analysis** creates a new saved run.
- The backend and browser use EXIF-oriented dimensions. The same image layer transforms the source, canvas, and selectable boxes while fitting, resizing, zooming, panning, and entering fullscreen.
- Video analysis explicitly reports that it is planned for Phase 6. A valid empty result means the model found no supported objects above the chosen threshold.

The detector uses pretrained COCO categories. Detection scores are model confidence scores, not calibrated probabilities. It does not infer activities, relationships, text, attributes, captions, or a scene narrative. The Ultralytics package and model have [AGPL-3.0 and Enterprise licensing options](https://docs.ultralytics.com/help/quickstart/#ultralytics-license); review the license before distributing a modified or hosted product. See [model setup](backend/MODELS.md), [API contract](backend/API.md), and [architecture](docs/ARCHITECTURE.md).

## Phase 2 media features

- JPEG, PNG, WebP, MP4 and WebM upload with client progress, cancellation, retry and backend validation.
- SQLite metadata and UUID-named files in `backend/data/media/`; thumbnails in `backend/data/thumbnails/`. These paths and the database are ignored by Git.
- EXIF-aware image dimensions and thumbnails. The original uploaded bytes remain intact.
- Video metadata and a poster thumbnail when FFmpeg can decode it. Browser playback uses a byte-range content endpoint.
- One active media selection shared by all five module routes, a recent-media library loaded after refresh, and verified metadata in the inspector.
- Image fit, zoom, pan and reset; video seek, play/pause, volume, speed and fullscreen. Empty overlay canvases are aligned to image pixels and the visible video area for later phases.
- Light/dark and responsive layouts, keyboard controls, loading/error/disconnected states. No simulated AI output.

### Default validation limits

| Limit | Default environment setting |
| --- | --- |
| Image file | 20 MiB (`VISIONLAB_MAX_IMAGE_BYTES`) |
| Video file | 250 MiB (`VISIONLAB_MAX_VIDEO_BYTES`) |
| Video duration | 10 minutes (`VISIONLAB_MAX_VIDEO_DURATION_MS`) |
| Image pixels | 40 million (`VISIONLAB_MAX_IMAGE_PIXELS`) |

The frontend reads effective limits from `GET /api/v1/media/limits`. The backend is authoritative. Uploads stream through a bounded request body and file copy; the server checks MIME, extension, signature, decoded image or probed video metadata. Rejected files are removed from local storage.

## Architecture

```text
backend/app/
  api/             system, media and vision routes
  core/            settings, request logging, upload body limit
  providers/       lazy YOLO26 detector
  repositories/    SQLite media and analysis persistence
  schemas/         typed API contracts
  services/        media storage and bounded image analysis
frontend/src/
  components/media/  uploader, library, image/video viewers, overlays, inspector
  lib/               API client and formatting helpers
  store/             shared active media and theme state
  types/             TypeScript API and future overlay contracts
```

The backend keeps media validation and inference out of route handlers. Image inference runs in the FastAPI thread pool with a bounded semaphore; excess concurrent requests receive `429`. Model weights load lazily and remain cached. An additive SQLite migration preserves existing media records, and deleting media cascades to its analyses. Media IDs, not disk paths, appear in browser URLs.

## Phase 3.5 diagnostics

The backend writes readable PowerShell console events and rotating JSONL records at `backend/data/logs/visionlab.jsonl`. Each request has an `X-Request-ID` response header that also appears on its upload, inference, database, and HTTP events. Successful health polling is quiet at INFO. Set `VISIONLAB_LOG_LEVEL=DEBUG` for up to 20 validated per-object entries per analysis. The [logging guide](docs/LOGGING.md) covers configuration, timing interpretation, PowerShell commands, privacy, and log sharing. Frontend API errors display a reference ID when the backend provides one.

## Verify

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
$env:VISIONLAB_RUN_REAL_MODEL='1'; .\.venv\Scripts\python.exe -m pytest -q -s tests/test_real_model.py
$env:VISIONLAB_RUN_REAL_FLORENCE='1'; .\.venv\Scripts\python.exe -m pytest -q -s tests/test_real_florence.py

cd ..\frontend
npm test
npm run lint
npm run build
```

The optional real-model test needs a local JPEG: set `VISIONLAB_SMOKE_IMAGE` to its path, or place the [Ultralytics sample photo](https://ultralytics.com/images/bus.jpg) at `backend/data/smoke/bus.jpg`. It skips during ordinary `pytest` runs.

To check manually, upload a photo containing people or vehicles, run Image Analysis, select a box, and confirm the matching list item and coordinates. Change display filters without new inference. Zoom, pan, resize, enter fullscreen, refresh, and reopen the saved run. Try an EXIF-rotated photo and an image with no expected COCO objects. Select a video and confirm analysis remains unavailable while playback works. Browser playback depends on the uploaded codecs; the API reports `likely` or `uncertain`, not a guarantee.

## Current limits

Phase 4 performs image object detection and local Florence-2 captioning. Video AI analysis, tracking, webcam capture, segmentation, VQA, accessible descriptions, and exports remain planned. Media and analysis lists each return at most 100 newest items with no pagination. This local app has no authentication; a production multi-user deployment needs authentication and authorization. Video validation uses bounded metadata inspection and preview decode; it does not scan every frame for corruption. Cancelling a browser upload cannot undo a request the server has already fully received.

Review [Ultralytics' YOLO26 licensing](https://docs.ultralytics.com/models/yolo26/) before distributing or hosting this project.
