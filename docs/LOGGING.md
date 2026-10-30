# VisionLab backend logging

Phase 3.5 keeps the existing Python `logging` architecture and adds two outputs. The default console is readable in PowerShell:

```text
18:35:41.210 | INFO     | ANALYSIS   | req=b72d1234 | COMPLETE Image analysis finished | media_id=... analysis_id=... duration_ms=...
```

The file `backend/data/logs/visionlab.jsonl` contains one independently parseable JSON object per line. The file always uses JSONL even when the console is set to `pretty`. Each record has `timestamp`, `level`, `component`, `event`, `message`, and `request_id`; applicable records add IDs, model/device, real counts, error codes, and measured durations. `START`, `COMPLETE`, `SKIPPED`, `WARNING`, and `FAILED` prefixes make terminal status clear. The application suppresses successful health polling at INFO by default. Uvicorn server startup and error messages remain enabled, while its duplicate access lines are disabled.

## Configuration

Put these values in `backend/.env` with the `VISIONLAB_` prefix. Example: `VISIONLAB_LOG_LEVEL=DEBUG`.

| Variable after prefix | Default | Effect |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `LOG_CONSOLE_ENABLED` | `true` | Emit terminal events |
| `LOG_FILE_ENABLED` | `true` | Emit rotating JSONL |
| `LOG_FORMAT` | `pretty` | `pretty` or `json` for console; file remains JSONL |
| `LOG_DIRECTORY` | `data/logs` | File directory relative to `backend/` by default |
| `LOG_FILE_MAX_MB` | `10` | Maximum size of one file, 1–100 MiB |
| `LOG_FILE_BACKUP_COUNT` | `5` | Number of rotated backups, 1–20 |
| `LOG_REQUEST_ID_ENABLED` | `true` | Include request IDs in application logs; response IDs are always generated |
| `LOG_SLOW_REQUEST_MS` | `1000` | Emit `request.slow` only when exceeded |
| `LOG_HEALTH_REQUESTS` | `false` | Show successful health polls at INFO |
| `LOG_INFERENCE_DETAILS` | `true` | At DEBUG, log at most 20 validated detections per run |
| `LOG_COLORS` | `auto` | `auto`, `always`, or `never` for console; no color library required |

The directory is created at startup. Files rotate as `visionlab.jsonl`, `visionlab.jsonl.1`, through `.5`. Existing logs are appended, not overwritten. This uses Python's `RotatingFileHandler`, which is intended for the initial **single API worker**. Multiple independent worker processes writing the same file require a process-safe collector or distinct per-worker files. The ignored log directory is local development data. On shutdown the standard Python logging lifecycle flushes and closes handlers; VisionLab emits `server.stopped`.

## Follow a request

Copy the `X-Request-ID` from an API response or the reference ID shown in the frontend error. The server accepts an incoming canonical UUIDv4, otherwise generates one. The ID is stored on request state and propagated with a context variable into the thread used for upload and inference. It is reset after the request, so concurrent requests keep separate IDs. The JSONL file retains the full UUID; the console shows the first eight characters.

From the project root in PowerShell:

```powershell
Get-Content backend\data\logs\visionlab.jsonl -Tail 30
$requestId = 'paste-full-uuid-here'
Get-Content backend\data\logs\visionlab.jsonl | ConvertFrom-Json |
  Where-Object request_id -EQ $requestId |
  Select-Object timestamp,level,component,event,message,duration_ms,error_code
```

For an analysis ID from a saved result:

```powershell
$analysisId = 'paste-analysis-uuid-here'
Get-Content backend\data\logs\visionlab.jsonl | ConvertFrom-Json |
  Where-Object analysis_id -EQ $analysisId |
  Select-Object timestamp,event,model,device,run_kind,detection_count,duration_ms
```

To find upload validation or inference failures:

```powershell
Get-Content backend\data\logs\visionlab.jsonl | ConvertFrom-Json |
  Where-Object { $_.event -in 'upload.failed','model.load_failed','model.inference_failed','analysis.failed','request.failed' } |
  Select-Object timestamp,request_id,event,error_code,message
```

The upload path records `upload.started`, one `upload.streaming` summary, validation, metadata, thumbnail creation when one exists, persistence, and completion. Rejected uploads record the established error code and cleanup when temporary files were removed. The analysis path records media lookup, decoding, EXIF orientation only if an actual transform was applied, preprocessing, model load or cache reuse, inference, validated boxes, summary, persistence, and final completion. Empty detections are successful and log `detection_count=0`.

## Understand durations

All durations use a monotonic timer and are in milliseconds. `model.load_completed.duration_ms` measures only cold initialization. `model.cache_hit` means an already loaded model was reused. `analysis.completed.model_load_ms` distinguishes cold and warm runs; `inference_ms` measures prediction after loading. `decode_ms`, `preprocessing_ms`, `postprocessing_ms`, and `persistence_ms` describe their own phases. `analysis.completed.duration_ms` includes the full analysis and save. `request.completed.duration_ms` includes HTTP handling around it. A slow operation emits `request.slow` only after the configured threshold. A first model load may be slow for an expected reason; inspect `run_kind=cold` before treating it as a fault.

## Privacy and sharing

VisionLab logs media and analysis UUIDs, MIME type, byte count, dimensions, model metadata, scores at DEBUG, and error codes. It does not log raw media, original filenames, cookies, headers, credentials, SQL text, or full persisted results. Structured fields with secret or filename keys are redacted, and development traceback entries retain only module basenames, line numbers, and function names. Unexpected exception messages are not logged. Review even sanitized logs before sharing, since media IDs and class labels may still be sensitive to your use case.

To share a narrow diagnostic excerpt, export only relevant fields for one request:

```powershell
$requestId = 'paste-full-uuid-here'
Get-Content backend\data\logs\visionlab.jsonl | ConvertFrom-Json |
  Where-Object request_id -EQ $requestId |
  Select-Object timestamp,level,component,event,message,error_code,duration_ms |
  ConvertTo-Json -Depth 4 |
  Set-Content visionlab-diagnostic.json
```

Inspect `visionlab-diagnostic.json` before sending it to another person. Rotate or delete local log copies according to your data retention needs.
