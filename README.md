# VisionLab AI

A local computer vision workstation for learning five AI-103 image-understanding capabilities. **Phase 2 (B2 + F2)** adds real image/video upload, persistent metadata, a shared media library, and interactive viewers. The five AI inference modules remain planned; this phase returns no generated predictions.

## Run locally

Prerequisites: Python 3.12, Node.js 20.19+ or 22.12+, npm, and FFprobe for video uploads. FFmpeg enables video poster thumbnails and is recommended. Use two PowerShell terminals.

**Backend — http://localhost:5200**

```powershell
cd backend
Copy-Item .env.example .env
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host localhost --port 5200
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

## Phase 2 features

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
  api/             system and media routes
  core/            settings, request logging, upload body limit
  repositories/    SQLite metadata access
  schemas/         typed API contracts
  services/        validation, thumbnails, video probing, storage
frontend/src/
  components/media/  uploader, library, image/video viewers, overlays, inspector
  lib/               API client and formatting helpers
  store/             shared active media and theme state
  types/             TypeScript API and future overlay contracts
```

The backend keeps media validation and storage out of route handlers. CPU development uses Pillow and external FFprobe/FFmpeg rather than loading AI frameworks. Media IDs, not disk paths, appear in browser URLs. The React viewer uses the real saved content endpoint; overlays have no detections until a provider is implemented.

## Verify

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .

cd ..\frontend
npm test
npm run lint
npm run build
```

To check manually, upload a JPEG (including a rotated phone photo) and an H.264 MP4, switch among the five modules, refresh, and select them again from Recent media. Seek the video and try image zoom/pan. See [backend/API.md](backend/API.md) for a byte-range request example. Browser playback depends on the uploaded codecs; the API reports `likely` or `uncertain`, not a guarantee.

## Current limits

Phase 2 does not perform AI inference, video analysis, tracking, webcam capture, segmentation or export. The recent-media endpoint returns up to 100 newest items and has no pagination yet. Video validation uses bounded metadata inspection and preview decode; it does not scan every frame for corruption. Cancelling a browser upload cannot undo a request the server has already fully received. This is a local development app without authentication or cloud storage.

Before integrating YOLO26 Nano in Phase 3, review [Ultralytics' YOLO26 licensing](https://docs.ultralytics.com/models/yolo26/): its code and models are offered under AGPL-3.0 and Enterprise licenses.
