# CLIPFORGE AI — Architecture & Build Plan

Status: Milestone 1 implemented and tested (see README). This document is the source of truth for how the
system is split, what is stored, and what each milestone delivers. Anything not
listed as "implemented" below does **not** exist yet, and the UI says so.

## 0. Environment survey (dev sandbox, 2026-11-27)

| Capability | Available | Notes |
|---|---|---|
| FFmpeg / ffprobe | 6.1.1 | used for probing, thumbnails, later cutting/rendering |
| Python | 3.13 (uv) | backend + workers |
| Node | 22 | Next.js 16 frontend |
| PostgreSQL | 16 | primary database |
| Redis | 7.0 | job queue (arq) |
| Docker | client present | `infra/docker-compose.yml` for local Postgres/Redis/MinIO |
| GPU | none | Whisper (M2) must run on CPU (faster-whisper int8) or a hosted ASR API |
| Claude API | key not configured | needed from M2 (semantic analysis, clip discovery, hooks) |

## 1. Architecture

```
            ┌─────────────────────────┐
 Browser ──▶│ apps/web  (Next.js/TS)  │  UI only. No media work in the browser.
            └───────────┬─────────────┘
                        │ REST (JSON + chunked binary upload)
            ┌───────────▼─────────────┐
            │ API (FastAPI)           │  auth, validation, project state,
            │ clipforge.api           │  upload sessions, job submission
            └──┬──────────┬───────────┘
               │          │ enqueue (Redis / arq)
               │   ┌──────▼──────────────────────────────┐
               │   │ Workers (arq, async)                │
               │   │  • media worker  (probe, thumbs)  M1│
               │   │  • analysis worker (ASR, scenes)  M2│
               │   │  • AI orchestration (Claude)      M2│
               │   │  • render worker (FFmpeg)       M3-6│
               │   │  • publish worker (official APIs) M7│
               │   └──────┬──────────────────────────────┘
        ┌──────▼───┐  ┌───▼──────────────┐
        │PostgreSQL│  │ Object storage   │  local FS (dev) or S3-compatible
        └──────────┘  │ clipforge.storage│  (MinIO / R2 / S3)
                      └──────────────────┘
```

Module boundaries (one Python package, separate entry points):

- `clipforge.core` — settings, DB engine/session, logging.
- `clipforge.models` — SQLAlchemy models (the only place schema lives; Alembic migrates it).
- `clipforge.storage` — `Storage` interface with `LocalStorage` and `S3Storage`.
- `clipforge.media` — FFmpeg/ffprobe wrappers (pure functions, no DB).
- `clipforge.api` — FastAPI app and routers. Never runs FFmpeg on the request path.
- `clipforge.workers` — arq worker settings and tasks. Tasks own DB state transitions of jobs.
- Later: `clipforge.ai` (Claude orchestration), `clipforge.render`, `clipforge.social`.

Rules enforced in code:
- A project is `ready` only after the worker has probed the stored file successfully.
- Job progress is written by the worker at real step boundaries; the UI only displays it.
- Uploads are never deleted except by an explicit user delete/cancel.
- Long work never happens inside an HTTP request.

## 2. Folder structure

```
clipforge/
├── apps/web/                 Next.js 16 + Tailwind v4 (App Router, TypeScript)
│   └── src/{app,components,lib}
├── backend/
│   ├── clipforge/{core,models,storage,media,api,workers}
│   ├── alembic/              migrations
│   ├── tests/                pytest (real Postgres + real ffmpeg fixtures)
│   └── pyproject.toml
├── infra/docker-compose.yml  postgres, redis, minio
├── docs/ARCHITECTURE.md
└── Makefile / README.md
```

## 3. Database schema

M1 tables (implemented):

- **users** — id (uuid), email, display_name, created_at. M1 runs single-user
  (a seeded local user); OAuth login arrives before any multi-user/public deploy.
- **projects** — id, owner_id→users, name, status
  (`uploading|processing|ready|failed|cancelled`), status_message, source_asset_id→media_assets,
  created_at, updated_at.
- **upload_sessions** — id, project_id, filename, content_type, size_bytes, chunk_size,
  total_chunks, received_chunks (int[]), received_bytes, status
  (`active|completed|cancelled|failed`), staging_path, error, created_at, updated_at, completed_at.
- **media_assets** — id, project_id, kind (`source|thumbnail|…`), storage_backend, storage_key,
  filename, content_type, size_bytes, sha256, created_at.
- **video_metadata** — asset_id (pk), duration_s, width, height, display_width, display_height,
  rotation, fps, aspect_ratio (text "16:9"), orientation, video_codec, pixel_format, bit_rate,
  has_audio, audio_codec, audio_channels, audio_sample_rate, audio_track_count, container,
  raw_probe (jsonb).
- **jobs** — id, project_id, type (`probe_source|…`), status
  (`queued|running|succeeded|failed|cancelled`), progress (0–1), stage, attempts,
  max_attempts, error, payload (jsonb), result (jsonb), arq_job_id, timestamps.

Planned (not yet created):
- M2: `transcripts`, `transcript_words` (word, start, end, speaker, confidence),
  `scenes`, `speakers`, `analysis_runs`, `clip_candidates` (title, start, end, hook, category,
  reason, score breakdown jsonb, confidence, status), `scoring_profiles`.
- M3–5: `clips` (edit decision list jsonb, versioned), `clip_versions`, `subtitle_tracks`,
  `reframe_tracks`, `brand_presets`, `broll_suggestions`, `licensed_assets`.
- M6: `renders` (preset, output asset, qc_report jsonb), `exports`.
- M7: `social_accounts` (encrypted tokens), `publish_requests`, `platform_metrics`.

## 4. API endpoints (prefix `/api/v1`)

Implemented in M1:

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness + DB/Redis/ffprobe/storage checks |
| GET | `/dashboard` | real counts, storage used, recent projects |
| POST | `/uploads` | create project + upload session (validates name/size/type) |
| GET | `/uploads/{id}` | session status incl. received chunk list (for resume) |
| PUT | `/uploads/{id}/chunks/{index}` | upload one chunk (idempotent, size-checked) |
| POST | `/uploads/{id}/complete` | assemble, hash, move to storage, enqueue probe |
| DELETE | `/uploads/{id}` | cancel, delete staged bytes |
| GET | `/projects` | list (search, status filter, pagination) |
| GET | `/projects/{id}` | detail: metadata, upload, jobs |
| PATCH | `/projects/{id}` | rename |
| DELETE | `/projects/{id}` | explicit delete incl. stored files |
| POST | `/projects/{id}/reprocess` | re-run metadata extraction (e.g. after a failure) |
| GET | `/projects/{id}/source` | stream source video (HTTP Range) |
| GET | `/projects/{id}/thumbnail` | poster frame |
| GET | `/jobs/{id}` | job status/progress |
| POST | `/jobs/{id}/cancel` | cancel queued/running job when safe |

Planned: `/projects/{id}/analysis` (M2), `/projects/{id}/candidates` + select/reject/regenerate
(M2), `/clips/*` edit decisions, subtitles, reframing (M3–5), `/renders`, `/exports` (M6),
`/social/accounts`, `/publish` (M7).

## 5. Processing pipeline

```
upload chunks ─▶ complete ─▶ [probe_source] ─▶ ready
                                │ ffprobe → video_metadata
                                │ validate: has video stream, duration > 0, decodable
                                │ thumbnail at 10% duration
                                ▼
 M2  [extract_audio] ─▶ [transcribe (faster-whisper, word timestamps)] ─▶ [diarize]
     [scene_detect (ffmpeg scdet / PySceneDetect)] ─▶ [face_track sample frames]
     ─▶ [semantic_analysis (Claude, transcript+scene context)] ─▶ [clip_discovery + scoring]
 M3  [smart_boundaries (word/silence aware)] ─▶ [reframe track] ─▶ [subtitle track]
 M4  [audio_enhance (loudnorm, afftdn, compand)] ─▶ [animation plan] ─▶ [broll suggestions]
 M6  [render (ffmpeg, 1080x1920 H.264/AAC 30fps)] ─▶ [qc (probe, blackdetect, freezedetect,
     ebur128, subtitle bounds)] ─▶ export
 M7  [publish via official API] ─▶ [verify platform response] ─▶ [metrics sync]
```

Every stage is a `jobs` row; retries use exponential backoff for recoverable errors
(storage/network); deterministic failures (corrupt file) fail fast with a clear message.

## 6. Milestone 1 plan

Scope: dashboard, upload, metadata, storage, project persistence.

1. Backend skeleton: settings, async SQLAlchemy, Alembic migration for M1 tables.
2. Storage abstraction: local FS + S3-compatible (boto3), selected by env.
3. Resumable chunked upload API (create / chunk / status / complete / cancel).
4. Worker (arq): `probe_source` task — ffprobe metadata, validation, thumbnail, real progress.
5. Projects API: list/detail/rename/delete/reprocess; source streaming with Range; thumbnail.
6. Dashboard summary API.
7. Frontend: dark workspace shell with all 9 nav sections; Dashboard, New Project
   (drag-drop, picker, validation, per-byte progress, cancel, retry/resume),
   My Projects, Project detail (summary + metadata + job status + player).
   Sections for later milestones show an explicit "arrives in Milestone N" state.
8. Tests: pytest against real Postgres + ffmpeg-generated fixture videos (with/without audio,
   portrait, corrupt file); browser end-to-end upload via Playwright.
9. Docs: README run instructions.

Out of scope for M1 (no UI pretends otherwise): transcription, AI analysis, rendering,
publishing, analytics, OAuth login.

Known limits of M1 (tracked for later):
- Single-user local mode; OAuth before any shared deployment.
- Uploads abandoned without cancel keep their staged bytes (never silently deleted); a
  cleanup policy with user-visible expiry comes with M6 storage management.
- Status updates use polling (1.2–3 s); SSE/WebSocket can replace it when render jobs land.
