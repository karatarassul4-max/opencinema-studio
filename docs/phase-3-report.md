# Phase 3 — OpenCinema Studio verification

Date: 2026-10-30. Local Windows workstation, RTX 3060 12GB. No new models, paid services or core ComfyUI/PyTorch upgrades were used. Existing system Python application packages were sufficient.

## Delivered

FastAPI job API, SQLite persistence and active reservation, ComfyUI HTTP/WebSocket adapter, history/queue reconciliation, validated uploads and MP4 retrieval. A responsive buildless Studio interface includes image preview, scene direction, four descriptive camera presets, seed/randomize, progress, video playback and download. The verified 512×320 / 25-frame / 24fps graph is unchanged by default.

New source files: `app/__init__.py`, `app/main.py`, `app/static/index.html`, `app/static/style.css`, `app/static/app.js`, `tests/test_app.py`, `requirements.txt`, `scripts/start-comfy.ps1`, `scripts/export_evidence.py`.

New delivery files: `README.md`, `LICENSE`, `docs/ATTRIBUTION.md`, `docs/SUBMISSION.md`, this report, `docs/e2e-evidence.json`, desktop/mobile screenshots under `docs/screenshots/`. Updated `.gitignore` and workflow provenance. Existing workflow JSON and model weights were retained.

## Automated verification

`python -m pytest -q`: **20 passed**, **1 warning** (Starlette's deprecated AnyIO BlockingPortal alias), **5.52 seconds** on the final test run. No failed tests. Test cases cover MIME/content/size validation, normalization, workflow injection/defaults, lifecycle, output range requests, one-job reservation including independent database connections, missing models and busy ComfyUI adapter responses, downtime, restart recovery, completion through HTTP while WebSocket is unavailable, missing outputs, failed/lost jobs, output traversal, request body size, Host and Origin checks.

These tests use fake inference responses. They do not claim to benchmark GPU execution. No automated malicious-file corpus or public-service security audit was performed.

## Real browser-to-GPU execution

The browser uploaded the official engineering fox image through Studio's file chooser. Studio submitted its API graph to the existing local ComfyUI instance. Two new outputs completed:

| Run | Job | Comfy prompt | Execution | Notes |
| --- | --- | --- | --- | --- |
| First | `d7238fb5e9a84f41b19178908db6cfbe` | `c0a68cd0-4e19-4cd9-95ee-d25974a23008` | 113.49 s (console) | New browser submission, seed 20261029 |
| Follow-up | `e88c23c07e4048bf99a86609a5eaad72` | `70deff3d-2199-4d3b-bd9a-142b95742084` | 10.12 s (console) | Warm models, cached nodes 38/7/73/44/6, seed 20261030 |

The warm result is not a general speed claim. Both used real sampling and video decoding. History timestamps and output hashes are exported in `e2e-evidence.json`. No Phase 3 peak VRAM/RAM measurements were collected; the accepted Phase 2 sampled peak of 11,406 MiB must not be mislabeled as a new measurement.

First video: 64,732 bytes, H.264, 512×320, 25 decoded frames, 24fps, 1.041667 seconds. SHA-256:

`3d826fca9dbc4e6e99299a32272a7b92402d81c82ea069643046976a33f46bd1`

Browser video element reported readyState 4, width 512, height 320, duration 1.041667. After clicking play it reported `paused=false`, `currentTime=0.6154`; there was no media error. Clicking Download MP4 produced `Downloads/opencinema-d7238fb5.mp4`, whose SHA-256 matched the server copy exactly.

The browser tool briefly lost its tab binding; reopening Studio recovered the completed job. The backend was then restarted to load additional guards, and the completed result persisted. The second render recorded actual WebSocket progress events and HTTP status samples at 95%, then completed at 100%. Sampling messages and history remain available locally. Browser console error inspection returned an empty list. Desktop (1366px) and mobile (390px) layouts were checked and screenshots saved.

Local evidence:

- `artifacts/studio/<job-id>.mp4`: output copy used by Studio.
- `artifacts/studio/<job-id>-workflow.json`: exact submitted graph.
- `artifacts/studio/<job-id>-history.json`: Comfy execution and output metadata.
- `artifacts/studio/e88c23c07e4048bf99a86609a5eaad72-events.jsonl`: real WebSocket sampling progress.
- `artifacts/studio/e2e-progress.jsonl`: HTTP status observations.
- `artifacts/studio/video-inspection.json`: full first-video decode inspection.

## Limits and submission status

The engineering output is recognizable and stable, with very subtle movement. No precise camera control or strong VFX effect has been validated. Clips are about one second; longer clips remain outside this tested default. There is no authentication, cancellation, gallery or automatic disk cleanup. The one-worker backend reserves one Studio job; external clients using ComfyUI directly can bypass that reservation. Use a dedicated local ComfyUI queue.

Restart recovery depends on ComfyUI retaining its queue/history. It cannot reconstruct a job after both ComfyUI state and local metadata are lost; ambiguous submissions are not blindly retried. OOM failures are surfaced as generation errors with ComfyUI console inspection required.

Local technical demonstration is ready. Submission is **not yet complete**: public GitHub publication, fresh-clone verification, licensed demo media, recording and submission form remain. The LTX core-model condition is met, but a bonus/prize claim would be premature. See `SUBMISSION.md` for the official source and remaining steps.
