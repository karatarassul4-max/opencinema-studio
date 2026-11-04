# OpenCinema Studio v2 architecture

The v2 release uses LTX-Video 13B 0.9.8 Distilled FP8. LTX 2.5 is a separate research effort, not part of this release.

| Module | Responsibility |
|---|---|
| app/main.py | Upload/auth/origin validation, persisted reservations, endpoints and reconciliation |
| app/settings.py | Comfy URL, offline default, project-local storage boundary |
| app/director.py + config/scenes.json | Deterministic scene/mood/camera/lighting prompt composition |
| app/durations.py | 25/49/73/97-frame allowlist |
| app/hd_export.py | ffprobe source inspection, RealESRGAN graph, output ownership checks |
| app/benchmark.py | Persisted timing quality/source and optional output probing |
| app/gpu_monitor.py | Optional read-only device-wide samples, disabled by default |
| app/static | Existing vanilla-JS interface, polling, preview and downloads |

## Generation and recovery

One worker and an application lock reserve a SQLite job before POST /prompt. A database uniqueness guard also prevents simultaneous active reservations. The Comfy adapter checks its queue, uploads the normalized image, injects a deterministic Director prompt and per-job output prefix into the selected workflow, and submits with an opencinema_id tag.

Status proceeds through submitting, queued/running and completed/failed. WebSocket events supply sampling progress. HTTP history/queue reconciliation handles lost events and restarts. If POST /prompt has an ambiguous response, the persisted reservation is searched by tag rather than automatically resubmitted. Retained Comfy history is necessary for this recovery; this is not an unlimited durable distributed queue.

Completed output must be job-owned and an MP4. Studio copies it into its project-local data directory and serves it through the job endpoint; arbitrary filesystem paths are not accepted for downloads.

## HD export

POST /api/jobs/{id}/hd requires a completed original and enabled inference. It checks source metadata with ffprobe, rejects unsupported dimensions/frame counts/rates, acquires the same active-job reservation and submits a distinct VHS/RealESRGAN workflow. A completed export is reused; a failed job can be retried explicitly. Output ownership, width, height and frame count are checked before completion. ffprobe must be installed; metadata inspection failures are not silently accepted.

The browser computes active state from the new job before assigning the HD button state. Export becomes enabled synchronously when eligible completion is rendered; an asynchronous HD lookup can reveal an existing download but cannot overwrite a different or active job. No inference graph is altered for this UI behavior.

## Storage and deployment

Default data: artifacts/studio below the repository. OPENCINEMA_V2_DATA must remain a resolved subdirectory of the clone. Uploads, MP4s, jobs.sqlite, benchmark histories and telemetry are runtime artifacts, excluded from Git. No automatic cleanup or user tenancy is implemented.

Use one Uvicorn worker, normally loopback port8001, and independently managed ComfyUI on8189. Multiple Studio processes/databases or other Comfy clients can still contend for one GPU. HD uses a local MP4 path and requires filesystem visibility from ComfyUI. Private-demo Basic Auth is an optional single-user boundary behind HTTPS, not a public SaaS security model.

## API

| Route | Purpose |
|---|---|
| GET /api/health | Connection, inference flag and active job |
| GET /api/presets | Scenes, cameras, moods, strengths and durations |
| POST /api/director | Read-only final prompt preview |
| POST /api/jobs | Validate upload/settings and submit generation |
| GET /api/jobs/{id} | Persisted job/progress |
| GET /api/jobs/{id}/video | Preview or download validated local MP4 |
| POST /api/jobs/{id}/hd | Submit/reuse a separate HD export |
| GET /api/jobs/{id}/hd | Latest HD export status for a source |
| GET /api/benchmarks | Paginated history, optional frame filter |

See [README](../README.md) for commands and limitations. Tests use mocks and block network access; no API endpoint was called against the running demo for this release.
