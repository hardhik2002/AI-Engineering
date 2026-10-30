# VisionLab media API (v1 routes, Phase 2)

Base URL: `http://localhost:5200`. See `/docs` for generated OpenAPI schemas. All media URLs use a server-generated UUID and never reveal local disk paths.

| Method | Route | Result |
| --- | --- | --- |
| `GET` | `/api/v1/health` | Service status and version |
| `GET` | `/api/v1/capabilities` | Five AI modules `planned`; upload and previews `available` |
| `GET` | `/api/v1/media/limits` | Effective size, duration and pixel limits |
| `POST` | `/api/v1/media/upload` | `multipart/form-data` with required `file`; returns 201 and a `MediaAsset` |
| `GET` | `/api/v1/media?limit=50` | Newest saved media, up to 100 |
| `GET` | `/api/v1/media/{media_id}` | One media asset |
| `GET`, `HEAD` | `/api/v1/media/{media_id}/content` | Original bytes, MIME and HTTP byte ranges |
| `GET` | `/api/v1/media/{media_id}/thumbnail` | JPEG thumbnail, when available |
| `DELETE` | `/api/v1/media/{media_id}` | Removes metadata and files; returns 204 |

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

Common codes include `invalid_request` (422), `unsupported_format` (422), `invalid_mime_type` (422), `invalid_media` (422), `file_too_large`/`image_too_large`/`video_too_long` (413), `body_too_large` (413), `media_not_found` (404), `thumbnail_not_found` (404), `invalid_range` (416), and `media_dependency_unavailable` (503).
