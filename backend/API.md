# VisionLab API (v1 routes, Phase 7)

Base URL: `http://localhost:5200`. See `/docs` for generated OpenAPI schemas. All media URLs use a server-generated UUID and never reveal local disk paths.

| Method | Route | Result |
| --- | --- | --- |
| `GET` | `/api/v1/health` | Service status and version |
| `GET` | `/api/v1/capabilities` | Module states; image detection modules become `available` after a model loads successfully |
| `GET` | `/api/v1/media/limits` | Effective size, duration and pixel limits |
| `POST` | `/api/v1/media/upload` | `multipart/form-data` with required `file`; returns 201 and a `MediaAsset` |
| `GET` | `/api/v1/media?limit=50` | Newest saved media, up to 100 |
| `GET` | `/api/v1/media/{media_id}` | One media asset |
| `GET`, `HEAD` | `/api/v1/media/{media_id}/content` | Original bytes, MIME and HTTP byte ranges |
| `GET` | `/api/v1/media/{media_id}/thumbnail` | JPEG thumbnail, when available |
| `DELETE` | `/api/v1/media/{media_id}` | Removes metadata and files; returns 204 |
| `GET` | `/api/v1/vision/models` | YOLO26 installation/load state; never triggers a download |
| `GET` | `/api/v1/vision/capabilities` | Fine-grained current/planned vision capabilities |
| `POST` | `/api/v1/media/{media_id}/analyze` | Run image object detection; returns 201 with a persisted analysis |
| `GET` | `/api/v1/media/{media_id}/analyses` | Up to 100 saved runs for a media item, newest first |
| `GET` | `/api/v1/media/{media_id}/analyses/{analysis_id}` | One saved analysis |

`MediaAsset` fields: `media_id`, `original_filename`, `media_type` (`image` or `video`), `detected_mime_type`, `width`, `height`, `file_size_bytes`, `duration_ms`, `frame_rate`, `video_codec`, `playback_compatibility`, `created_at`, `sha256`, `thumbnail_available`. Video-only values are `null` for images. `playback_compatibility` is `likely` for common H.264/AAC MP4 or VP8/VP9 WebM combinations and `uncertain` otherwise.

Upload example:

```powershell
curl.exe -F "file=@C:\path\to\photo.jpg;type=image/jpeg" http://localhost:5200/api/v1/media/upload
```

For a video range request, replace the UUID with an ID returned by the API:

```powershell
curl.exe -i -H "Range: bytes=0-1023" http://localhost:5200/api/v1/media/00000000-0000-4000-8000-000000000000/content
```

An existing item returns `206 Partial Content`, `Content-Range: bytes 0-1023/TOTAL`, `Accept-Ranges: bytes`, and the correct video MIME. An invalid or unsatisfiable single range returns `416` and `Content-Range: bytes */TOTAL`. Multi-range requests are not supported in Phase 2.

Errors use a consistent JSON shape for application validation and media lookup, such as:

```json
{"error":{"code":"invalid_media","message":"Image is malformed or truncated."}}
```

Every HTTP response has an `X-Request-ID` header. The server accepts a canonical UUIDv4 supplied in that header or generates a fresh UUIDv4 if it is absent or invalid. Include this ID when reporting an upload or analysis failure. It links the response to records in `data/logs/visionlab.jsonl`. The browser is allowed to read the header through CORS. Internal tracebacks stay out of API responses.

Common codes include `invalid_request` (422), `unsupported_format` (422), `invalid_mime_type` (422), `invalid_media` (422), `file_too_large`/`image_too_large`/`video_too_long` (413), `body_too_large` (413), `media_not_found` (404), `thumbnail_not_found` (404), `invalid_range` (416), and `media_dependency_unavailable` (503).

## Image detection contract

`POST /api/v1/media/{media_id}/analyze` accepts an optional JSON body. Omit it to use server defaults. To change inference parameters explicitly:

```json
{"tasks":["object_detection"],"parameters":{"confidence":0.25,"iou":0.45,"image_size":640,"max_detections":100}}
```

Confidence is greater than 0 and at most 1; IoU is 0 through 1; image size is 160–1280; maximum detections is 1–300. Invalid values return `422`. Omitted fields use configured server defaults; `GET /api/v1/vision/models` exposes those defaults. A new request always creates a new saved run. Display filters in React do not call this endpoint.

The response includes `analysis_id`, `media_id`, `status`, `task`, `created_at`, `completed_at`, `model`, `image`, `parameters`, `detections`, `summary`, and `timings_ms`. Each detection contains an ID, real class ID and label, confidence score, and `bounding_box` as normalized `{x,y,width,height}`. The origin is the top left of the EXIF-oriented image, with each coordinate in `[0,1]`. `image.width` and `image.height` are oriented original dimensions, even when preprocessing resized the detector input. Multiply normalized values by these dimensions to obtain pixel coordinates. Invalid or non-finite detector coordinates fail the analysis; out-of-image edges are clipped only when a positive area remains.

`summary.total_objects` and `summary.class_counts` are derived from the returned detections. Zero detections is a successful result with an empty list and zero counts. `model` includes Ultralytics package version, YOLO26 version, execution device, and the installed weight file's SHA-256 digest. Timings are measured in milliseconds; `model_initialization` is separate from `inference`. The `analysis.completed` log duration includes persistence, while the response's `timings_ms.total` is measured when the result is constructed, before the database write. Failed runs are retained with `status=failed` and `error_code`; internal tracebacks are never sent to the browser.

Additional errors: `unsupported_media_task` (422 for video), `model_not_installed` (503), `device_unavailable` (503), `model_initialization_failed` (503), `model_busy` (429 with `Retry-After`), `inference_failed` (500), `media_changed` (409), and `analysis_not_found` (404). The status and capability endpoints are lightweight and do not load model weights.

## Florence-2 image captioning (Phase 4)

`POST /api/v1/media/{media_id}/caption` accepts `{"mode":"short"}`, `detailed`, or `extended` and returns `201`. `POST /api/v1/media/{media_id}/dense-regions` accepts no body. `POST /api/v1/media/{media_id}/regions/describe` accepts `{"detection_analysis_id":"UUID","detection_id":"UUID"}`; both IDs must refer to a completed YOLO run and one of its saved detections for the same media. `GET /api/v1/media/{media_id}/captions` returns up to 100 newest saved Florence runs. `GET /api/v1/vision/caption-model` reports local installation and load state without loading or downloading the checkpoint.

Each successful result includes `analysis_id`, `media_id`, `task`, `status`, timestamps, `model` (provider, checkpoint, pinned revision, device, Transformers version), `duration_ms`, `model_load_ms`, `inference_ms`, and either real `text` or `regions`. Dense regions include an ID, generated description, provenance, and normalized `{x,y,width,height}` box in the EXIF-oriented image coordinate space. No Florence confidence score is invented. An empty dense list is valid. Runs persist in the existing `analyses` table and are deleted with their media. Capability keys for individual caption tasks become `available` only after a successful real run in the current API process.

Errors retain the standard `error` shape and `X-Request-ID`. Relevant codes include `caption_model_not_installed` (503), `caption_model_load_failed` (503), `caption_device_unavailable` (503), `caption_busy` (429), `caption_inference_failed` (500), `malformed_caption` (500), `invalid_region` (500), `invalid_detection` (404/422), `unsupported_media_task` (422), and `media_changed` (409). `422` also covers an invalid mode. Caption generation may take seconds on CPU; client calls have no fixed timeout.

## OpenAI image Q&A and accessible descriptions (Phase 5)

`GET /api/v1/vision/providers` returns provider name, configured model, and state (`unconfigured`, `configured`, `available`, `unavailable`, or `error`). `configured` means only that a backend key exists; `available` requires a successful response in the current process. No credentials are returned.

`POST /api/v1/media/{media_id}/vqa` takes `{"question":"What is visible?","conversation_id":null,"consent_external_transfer":true}`. `conversation_id` can be omitted to start a conversation. The response contains conversation and message IDs, roles, text, timestamps, provider/model, measured duration, actual token usage when supplied, and model-assessed `grounding_status` plus `uncertainty_note`. Prior messages are bounded to the last eight in each request; each conversation is capped at 50 questions. `GET /api/v1/media/{media_id}/vqa/conversations` lists up to 50 conversations; `GET` or `DELETE /api/v1/media/{media_id}/vqa/conversations/{conversation_id}` opens or clears one. Conversations cannot cross media IDs.

`POST /api/v1/media/{media_id}/accessibility` takes `purpose` (`informative`, `decorative`, `functional`, `complex`), optional `context`, `audience`, and `function`, and `consent_external_transfer:true` for a cloud generation. Decorative always returns local `alt_text:""` without cloud transfer. To save an existing Florence caption as an editable local suggestion, pass its `source_caption_analysis_id`; that ID must belong to this media. `GET /api/v1/media/{media_id}/accessibility` returns up to 50 saved records. `PATCH /api/v1/media/{media_id}/accessibility/{result_id}` takes `alt_text`, optional `detailed_description` and `extended_description`, and `expected_version` to prevent overwriting concurrent edits. Each record retains `generated` and `edited` separately with source, version, timestamps, model, latency, and actual usage when available.

All Phase 5 routes require a valid uploaded image ID. Video returns `unsupported_media_task` (422). Cloud requests without consent return `external_consent_required` (403); without a key return `openai_not_configured` (503). Other explicit errors include `vision_busy` (429), `conversation_busy`/`version_conflict` (409), provider timeout/unavailability (503/504), and missing saved IDs (404). OpenAI content and the key are absent from structured logs. The frontend displays the response `X-Request-ID` for failures.

## Uploaded video analysis (Phase 6)

`POST /api/v1/media/{media_id}/video/analyze` returns `202` with a persisted job. Optional JSON fields are `detection_fps` (0.25–8), `caption_interval_seconds` (1–120), `generate_captions`, `track_objects`, and the existing `detection` parameter object. The worker has one active and one queued slot; further starts return `video_queue_full` (429). `GET /api/v1/media/{media_id}/video/analyses` lists 50 saved runs. `GET /api/v1/video/analyses/{analysis_id}` returns one analysis.

`GET /api/v1/video/jobs/{job_id}` returns status (`queued`, `running`, `completed`, `failed`, `cancel_requested`, `cancelled`, `interrupted`), stage, counts, timestamp, elapsed milliseconds, error code, and revision. `POST /api/v1/video/jobs/{job_id}/cancel` requests cancellation. `GET /api/v1/video/jobs/{job_id}/events` emits SSE `job` events with revision IDs; send `Last-Event-ID` to reconnect. Polling the job endpoint is also supported. A restarted server marks nonterminal jobs `interrupted` and preserves partial results.

`GET /api/v1/video/analyses/{analysis_id}/frames?start_ms=0&end_ms=10000&limit=100` returns up to 100 timestamped frame records, including original PTS/time base, source display dimensions, actual YOLO scores and normalized boxes, optional ByteTrack IDs, model metadata, and inference duration. `GET .../timeline` returns compact sampled-frame markers. `GET .../tracks` and `GET .../captions` support the same time filters and limits (max 100). Tracks are sampled associations. `POST /api/v1/media/{media_id}/video/analyses/{analysis_id}/captions` with `{"timestamp_ms":1234}` queues an on-demand Florence frame caption job. `PATCH /api/v1/video/analyses/{analysis_id}/captions/{caption_id}` with `{"edited_text":"...","expected_version":1}` saves a separate human edit.

`POST /api/v1/media/{media_id}/video/vqa` takes `question`, `start_ms`, `end_ms`, optional `conversation_id`, and `consent_external_transfer:true`. It returns the saved conversation and `examined_timestamps_ms`; each answer also retains its frame references. The same conversation list/get/delete routes as image VQA apply. `POST /api/v1/media/{media_id}/video/analyses/{analysis_id}/refine` takes `timestamp_ms`, optional `context`, and consent to save an OpenAI description for one actual frame. Both cloud routes require explicit consent and a configured backend key. Local detection and captioning remain usable without OpenAI. No response claims continuous observation between sampled frames.

## Live camera WebSocket (Phase 7)

`WS /ws/v1/live` uses protocol version `1`. A browser connection needs an exact `Origin` from `VISIONLAB_CORS_ORIGINS` whose host is `localhost` or `127.0.0.1`; unsupported origins close with code `1008` before acceptance. Capacity overflow closes with `1013`. On acceptance the server sends `session.started` with a UUID `session_id`, `protocol_version`, active session count, and frame limits including `max_in_flight_frames:1`. No media is stored by this endpoint.

The client sends one **binary** `frame.submitted` message at a time: ASCII `VL1` (3 bytes), a big-endian unsigned 32-bit JSON-header length (4 bytes), UTF-8 JSON header (at most 1024 bytes), then JPEG bytes. Header fields are `type`, `session_id`, UUID `frame_id`, browser `performance.now()` `captured_at_ms`, `source_width`, `source_height`, and `encoded_format:"jpeg"`. The encoded image must match declared dimensions and stay within `VISIONLAB_LIVE_MAX_FRAME_BYTES`; dimensions cannot exceed the configured maximum. The backend also enforces `VISIONLAB_LIVE_TARGET_FPS` and closes oversized messages with `1009`. Recommended Uvicorn settings are `--ws-max-size 1050000 --ws-max-queue 2`.

Responses are JSON `frame.result` (session/frame IDs, echoed browser capture timestamp, source dimensions, real normalized `{x,y,width,height}` detections, model metadata, actual `inference_ms`, `processing_ms`, server `result_at`, outcome), `frame.skipped` (frame ID and reason such as `rate_limited` or `model_busy`), and `session.error` (safe code/message). The client sends JSON `{"type":"session.stop"}` to end a session; the server replies `session.stopped`. Idle sessions end after 30 seconds by default. Browser round-trip latency must be computed with the echoed browser monotonic clock; server wall-clock timestamps are for provenance, not RTT calculation. The frontend sends no OpenAI request from this socket.
