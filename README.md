# OpenCinema Studio

A local cinematic image-to-video workspace powered by **real ComfyUI workflows** and **LTX-Video 2B v0.9.5**. Upload a frame, describe a scene, choose camera inspiration, and render an MP4 on your GPU.

![OpenCinema Studio](docs/screenshots/studio-neutral.jpg)

## Verified configuration

Windows, RTX 3060 12GB, ComfyUI 0.43.1, dynamic offloading, tiled VAE decoding. Default output is **512×320, 25 frames, 24 fps, batch 1** (about 1.04 seconds). The first Studio browser render took **113.49 seconds in ComfyUI**. This is a measured single run, not a performance guarantee. Motion in the fox test is subtle. Camera presets append descriptive text; they do not provide deterministic camera trajectories.

## Windows setup

Prerequisites: Git, Python 3.11, and a working ComfyUI installation with the models below. Clone this repository to D: before running these commands.

Use a separate Python 3.11 environment for Studio. Do not install Studio packages into ComfyUI's environment or upgrade its PyTorch installation.

```powershell
cd D:\comguopensource
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The current workstation already has the application dependencies; `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` also works there.

### Models and workflow

Place these exact files in the following folders (already present on the verified workstation):

| File | Folder | Approximate storage |
| --- | --- | --- |
| `ltx-video-2b-v0.9.5.safetensors` | `models/checkpoints/` | 5.91 GiB |
| `t5xxl_fp8_e4m3fn_scaled.safetensors` | `models/text_encoders/` | 4.80 GiB |

Sources and exact hashes: [model lock](config/models.lock.json). Review [model licenses](docs/ATTRIBUTION.md) before obtaining weights. Both dependencies total about 10.71 GiB; allow additional storage for environments and outputs. Downloads are deliberately not part of application startup. No custom nodes are needed. The checkpoint contains the VAE. The unscaled FP8 file is not the tested encoder.

Update `config/extra_model_paths.yaml` if your checkout is elsewhere. Keep all model and artifact folders on D:. Import `workflows/ltx-i2v-ui.json` into ComfyUI to inspect the graph; the backend uses `workflows/ltx-i2v-api.json`. See [provenance](docs/workflow-provenance.md) and [Phase 2 evidence](docs/phase-2-report.md).

### Launch

Start ComfyUI first, using its existing environment. The script defaults to this workstation's Desktop installation and accepts `-ComfyRoot` for another installation:

```powershell
powershell -File scripts/start-comfy.ps1
```

In a second terminal:

```powershell
cd D:\comguopensource
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Open **http://127.0.0.1:8000**. Upload a PNG/JPEG/WebP up to 10 MiB and 20 megapixels. English descriptive prompts work with the tested workflow. Keep ComfyUI dedicated to Studio while rendering. The application rejects overlapping jobs; it does not maintain an unlimited queue. Other ComfyUI clients can still submit directly, so do not render concurrently from its own UI.

Optional environment variables: `COMFY_URL` (default `http://127.0.0.1:8188`) and `OPENCINEMA_DATA` (default `artifacts/studio`). Keep the latter on D:. This is a trusted, single-user loopback application, not an authenticated public service. Run exactly **one worker** and do not expose it to the Internet.

## API and recovery

| Endpoint | Purpose |
| --- | --- |
| `POST /api/jobs` | Multipart `image`, `prompt`, `preset` (`dolly`, `orbit`, `crane`, `static`), `seed` (0–4294967295); returns 202 and job |
| `GET /api/jobs/{id}` | Persisted status, sampling progress, message, seed and Comfy prompt ID |
| `GET /api/jobs/{id}/video` | Job-owned MP4, supports HTTP ranges for playback |
| `GET /api/health` | ComfyUI reachability, device names, active job ID |

SQLite stores the active reservation before submission. HTTP history and queue polling recover state after WebSocket disconnection or backend restart. An ambiguous submission is reconciled using its job tag; it is never automatically resubmitted. If ComfyUI is offline, restart it and leave Studio open. If queue/history no longer contain the job, Studio reports failure and allows an explicit retry. Do not clear ComfyUI history during an active generation.

Progress is sampling progress (0–95%); 100% means an MP4 has been retrieved. Model loading and decoding have no reliable percentage. A completed result survives a browser refresh. No cancel endpoint, automatic disk cleanup or job gallery is implemented yet.

Inputs are decoded and re-encoded with Pillow; filenames are generated UUIDs. The backend validates the specific SaveVideo output before fetching it, then serves only its local copy. Request bodies, image dimensions, MIME types, presets, seeds and prompt lengths are bounded. Cross-origin POSTs and unknown Host headers are rejected.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Automated tests use a fake Comfy service and do not consume GPU time. They cover upload validation, immutable graph injection, lifecycle, single-job reservation, restart reconciliation, operation without WebSocket, Comfy failures, safe output paths, range retrieval and HTTP guards. Actual browser/GPU verification is documented separately in [Phase 3 report](docs/phase-3-report.md).

## Architecture

```mermaid
flowchart LR
  UI[Studio browser] -->|multipart image + direction| API[FastAPI on loopback]
  API --> DB[(SQLite jobs)]
  API -->|deep-copy + inject| Graph[Versioned API graph]
  Graph -->|HTTP prompt| Comfy[ComfyUI]
  Comfy -->|WebSocket sampling events| API
  API -->|HTTP history recovery| Comfy
  Comfy --> GPU[LTX 2B + FP8 T5 / RTX 3060]
  GPU --> Output[Comfy MP4]
  Output -->|validated view retrieval| Files[Local job artifacts]
  Files -->|range-capable video endpoint| UI
```

Artifacts include normalized input, submitted workflow, history, sampled progress events and MP4. They live under ignored `artifacts/`; model weights are also ignored. UI screenshots are the only media explicitly allowed under `docs/screenshots/`. Do not commit generated videos or uploaded images. Demo media should be shared separately after confirming input rights.

## Hackathon

See [submission checklist and recording script](docs/SUBMISSION.md). The code is MIT; third-party workflows, models and example images retain their own terms. [Attribution](docs/ATTRIBUTION.md) explains the separation. No paid API, cloud inference or mock video is used.

### Reuse existing weights in another clone

Do not run the model downloader again. Keep the existing ComfyUI process running with its D: model configuration, then launch Studio from the new clone. Studio uploads inputs over HTTP and does not require a local copy of the weights. If restarting ComfyUI, set `base_path` in the clone's `config/extra_model_paths.yaml` to the existing model directory. No junction or copy is required.
