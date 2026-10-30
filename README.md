# VisionLab AI

A local computer vision workstation for learning five AI-103 image-understanding capabilities. This repository currently implements **Phase 1 only**: a working FastAPI service and a responsive React workstation shell connected to real health and capability endpoints.

## Run locally

Prerequisites: Python 3.12, Node.js 20.19+ or 22.12+, and npm. Use two terminals.

**Backend (http://localhost:5200)**

```powershell
cd backend
Copy-Item .env.example .env
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host localhost --port 5200
```

If `py -3.12` is unavailable, use `uv venv --python 3.12 .venv` (when uv is installed) or another installed Python 3.12 executable. On macOS/Linux, use `python3.12 -m venv .venv` and `.venv/bin/python`.

**Frontend (http://localhost:5180)**

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Open [http://localhost:5180](http://localhost:5180). API documentation is at [http://localhost:5200/docs](http://localhost:5200/docs). The frontend uses `VITE_API_BASE_URL` and defaults to `http://localhost:5200`.

## What Phase 1 includes

- Five module routes, responsive media viewer shell, AI inspector, light/dark themes, keyboard focus and skip navigation.
- Health and capability APIs. Every inference capability is explicitly marked `planned`; no dummy captions, detections or answers are returned.
- Pydantic and matching TypeScript contracts for media dimensions, normalized boxes, detections, model provenance and API status.
- Environment-based settings, local CORS configuration, JSON request logging and request IDs.
- Basic backend and frontend tests. The frontend shows checking and disconnected states when the API is unavailable.

### API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/health` | Service status, version and environment |
| `GET /api/v1/capabilities` | Availability and planned phase for all five modules |

## Structure

```text
backend/
  app/api/          HTTP routes
  app/core/         settings and structured logging
  app/schemas/      versioned response and future inference contracts
  tests/            API and contract tests
frontend/
  src/components/   shared UI components
  src/lib/          API client and utilities
  src/store/        local theme state
  src/types/        TypeScript API contracts
  src/App.tsx       module routes and workstation shell
```

The modular monolith keeps HTTP contracts separate from future media, provider and inference services. FastAPI is suitable for typed local APIs; React provides the interactive viewer and inspector. Phase 1 installs only dependencies used by this phase. PyTorch, Transformers, Ultralytics, OpenCV, PyAV, Supervision, OpenAI, video workers and other planned integrations will be added in their respective phases, so CPU development starts quickly. SQLite is configured for future metadata persistence but is not initialized or used in Phase 1. No Docker, cloud account or authentication is needed.

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

Phase 1 tests cover the API contract, honest capability state, local CORS, normalized coordinate validation, JSON logging, frontend API status, navigation and theme. In later phases, model quality needs a labeled image set, detection precision/recall and caption/VQA grounding checks. Record model provenance and inference latency with every real result before benchmarking providers.

## Upcoming phases and limits

Media upload and viewing begin in Phase 2; object detection and overlays in Phase 3. The upload button is intentionally disabled in Phase 1. There is no inference, video processing, webcam, export or provider switching endpoint yet. Secrets remain server-side: `.env` is ignored by Git, and OpenAI credentials will never use a `VITE_` variable.

Before integrating YOLO26 Nano in Phase 3, review [Ultralytics' YOLO26 licensing](https://docs.ultralytics.com/models/yolo26/): its code and models are offered under AGPL-3.0 and Enterprise licenses. Choose a license appropriate to the intended use.
