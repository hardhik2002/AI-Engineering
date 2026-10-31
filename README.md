# VisionLab AI

A local computer vision workstation for learning five AI-103 image-understanding capabilities. **Phase 7 (B7 + F7)** adds user-initiated live webcam detection with the local YOLO26 model and an explicit snapshot path into the existing five modules. Uploaded image and video features remain available.

## Run locally

Prerequisites: Python 3.12, Node.js 20.19+ or 22.12+, npm, and FFprobe for video uploads. FFmpeg enables video poster thumbnails and is recommended. Use two PowerShell terminals.

**Backend — http://localhost:5200**

```powershell
cd backend
Copy-Item .env.example .env
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev,vision,caption,openai,video]'
.\.venv\Scripts\python.exe -m app.scripts.install_model
.\.venv\Scripts\python.exe -m app.scripts.install_florence
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --no-access-log --host localhost --port 5200 --ws-max-size 1050000 --ws-max-queue 2
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

## Phase 7 live camera

Open **Live Camera** and choose **Start Camera** to request browser permission. The page requests video only, never microphone access. Choose a device or front/back facing mode, resolution (320 × 240 or 640 × 480), analysis rate (0.5–2 FPS), and optional mirror. The preview remains native video while bounded JPEG frames go to the local WebSocket. The browser sends at most one frame until its result or skip arrives and checks WebSocket buffering. The server allows one local session by default and shares the image detector's semaphore, so overload returns an explicit skip. Neither camera frames nor predictions are saved automatically.

Boxes use validated normalized YOLO coordinates over the same fitted and mirrored video area. They identify the latest analyzed frame and clear after five seconds. Display confidence, classes, box/label/score switches, and object selection only change the view. **Capture Snapshot** uploads the current frame through the existing validated media API, selects it, and opens Image Analysis; the saved image can then be used in all five existing modules. Florence and OpenAI are never called by continuous live inference. Existing OpenAI consent still applies to snapshots.

Defaults in `backend/.env.example` are 640 × 480 maximum encoded dimensions, 2 FPS server limit, 1 MiB JPEG limit, one active session, and a 30-second idle timeout. The WebSocket checks an explicit localhost origin allowlist; keep the API bound to localhost. Browser camera access requires a secure context: localhost works for development, while a non-local deployment needs HTTPS and a matching secure WebSocket. Chrome, Edge, Firefox, and Safari versions with `getUserMedia` can use the fallback scheduler; `requestVideoFrameCallback` is used when present. Device availability and permission behavior vary by browser and hardware.

A real local YOLO service smoke run on a 360 × 480 JPEG of the bus photograph found six objects. Cold processing took 13.2 seconds; the next warm inference took 41.5 ms (43.4 ms wall time). This is a single-image detector baseline, **not measured webcam throughput**. Live tracking is unavailable because the existing ByteTrack state is separate from the cached image detector. Sparse sampling and delayed inference can make live boxes lag the preview. No physical webcam was available for automated validation; manually verify on your own camera.

Manual check: start both servers, open `http://localhost:5180/workspace/live_camera`, select **Start Camera**, grant permission, place a recognizable object in view, and compare its box and label with the inspector. Resize and mirror the preview, select an object, change display filters, switch cameras if available, then stop and confirm the browser camera indicator turns off. Restart, capture a snapshot, and verify it opens as saved media in Image Analysis and remains selectable in Captioning, Q&A, Objects & regions, and Accessibility. Navigate away while streaming and confirm the indicator turns off. Deny permission once to check the error message. Local live inference makes no OpenAI request.

Troubleshooting: if permission is denied, enable camera access for localhost in browser settings; if busy, close other camera apps. If no boxes appear, check the local YOLO weights, backend logs, and whether the display confidence filter hides the detections. If the socket closes, confirm both servers use localhost and `VISIONLAB_CORS_ORIGINS` contains the exact frontend origin. Run `python -m pytest -q -s tests/test_real_live.py` from `backend/` for the optional local-model frame smoke test; it is not a physical camera test.

### FFmpeg and FFprobe

Install a current build from the [official FFmpeg download page](https://ffmpeg.org/download.html). On Windows, follow its Windows EXE build link, extract the archive, and add its `bin` directory to `PATH`. On macOS, `brew install ffmpeg` is a common option. On Debian/Ubuntu, `sudo apt install ffmpeg` installs both commands. Restart the terminal and verify:

```powershell
ffprobe -version
ffmpeg -version
```

The binaries can also be set explicitly with `VISIONLAB_FFPROBE_BINARY` and `VISIONLAB_FFMPEG_BINARY` in `backend/.env`. Missing FFprobe gives a clear `503` error for video upload. Without FFmpeg, video metadata can still be stored but no poster thumbnail is generated.

## Phase 6 uploaded video understanding

Upload an MP4 or WebM with the existing uploader, select it in any module, choose detection FPS and caption interval, then **Analyze Video**. A single bounded in-process worker decodes timestamped frames with PyAV, runs real YOLO26 + ByteTrack sequentially, and samples Florence captions at the selected interval. The page polls persisted job progress and supports cancellation; one job runs and one may queue by default. Cancellation is checked between steps, so a current model call may finish first. After a restart, queued or active jobs become `interrupted`; saved frames remain available and **Analyze Video** starts a new run.

The native video viewer keeps boxes and captions aligned to its displayed video area. It uses frame presentation timestamps, `requestVideoFrameCallback` when available, and a time-update fallback. Boxes appear only near an analyzed frame; gaps show no boxes. Click timeline markers, tracks, or captions to seek. Display confidence, class filters, box/label/score switches, and the caption layer change only the view. A track ID is an estimated association across sampled frames, not a guaranteed distinct physical object. Sparse sampling can weaken ID stability. Partial coverage at a frame limit is shown explicitly.

In **Visual Q&A**, select a frame or time range and consent to send *this video's* sampled frames to OpenAI. The backend sends at most `VISIONLAB_VIDEO_MAX_VQA_FRAMES` resized frames (default 6), labels each with its actual timestamp, and saves the examined frame references with each answer. No video frame is sent to OpenAI on upload or during local analysis. User-initiated OpenAI calls may incur charges on your API account. In **Accessibility**, edit, copy, or export the local timestamped Florence description timeline; optional selected-frame OpenAI refinement also requires consent. These cues are not a complete accessible video solution.

Defaults are 2 detection FPS, a 10-second caption interval, 1,800 processed frames, 60 caption frames, one worker, and a 100,000 decoded-frame safety limit. These are CPU-safe initial bounds, not real-time targets. A local i5-1350P smoke run sampled four frames from a four-second encoded clip that loops a real bus photograph, saved 20 YOLO detections and one Florence caption, and took 72.1 seconds including model initialization (about 0.055 sampled frames per second end to end). This verifies real decoding and inference, but not tracking under scene motion or general throughput. The 10-minute upload limit still applies. See [API](backend/API.md), [model notes](backend/MODELS.md), and [architecture](docs/ARCHITECTURE.md).

For a manual check: upload a short H.264 MP4, select **Image Analysis**, analyze at 1–2 FPS, wait for completion, play and seek across sampled and unsampled times, then inspect tracks and captions. Refresh and reopen the saved run. Cancel a second run to check its terminal state. If OpenAI is configured, explicitly consent and ask about a selected time range; verify that the shown timestamps match the examined frames. No paid call is needed for local analysis. The local-model smoke test is `python -m pytest -q -s tests/test_real_video.py` from `backend/`; it uses installed weights and `data/smoke/bus-4s.mp4` when present.

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
- A valid empty result means the model found no supported objects above the chosen threshold.

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
