# Phase 2: real local LTX generation

Verified output: artifacts/output/opencinema/ltx-first_00001_.mp4
Prompt ID: 41875f78-49e0-46c5-a289-4fe907c80132
Evidence: artifacts/run-20261029-230307/ (history, events, metrics, submitted graph).

- ComfyUI execution: success, 105.71 seconds; client wall time 107.06 seconds.
- H.264 MP4, 512x320, 25 frames, 24 fps, 1.0417 seconds, 65,980 bytes.
- SHA256: 7e75de1a60d00f9d53c9e925c82e34ec9368037b148adb8eb3d2a5a26c8734ef
- Sampled peak device VRAM: 11,406 MiB (includes desktop applications).
- Sampled peak system RAM: 25.74 GiB; ComfyUI process RSS sum: 12.65 GiB.
- 40 samples, actual average interval 2.70 seconds (range 2.55–3.59 seconds).
  Sampling includes command overhead; these are not exact allocator peaks.
- Dynamic VRAM loading and CPU offload were active. No OOM traceback in successful run.
- Both approved model files passed publisher SHA256 verification; see config/models.lock.json.
  Model storage is approximately 10.71 GiB, on D:, below the 30 GiB allowance.

## Failure and recovery

The original 49-frame attempt completed sampling but disappeared during VAE decoding.
No MP4 or conclusive OOM traceback was recovered. Its raw evidence remains in
artifacts/run-20261029-224431/. Do not report it as successful or a confirmed OOM.
Retry retained the same models and resolution, reduced length to 25 frames,
used VAE tiles 128/32 with temporal size 8/overlap 4, and reserved 2 GiB VRAM.
No core package upgrades or custom nodes were required.

## Quality

All 25 frames decode. First/last mean pixel difference is 2.88/255.
Five sampled frames show a recognizable, stable fox and snow background with
very subtle motion. This is a functioning generation baseline, not yet a strong
cinematic demo. Smoothness was not assessed through full-speed visual playback.
The public demo needs an owned/licensed input image and stronger visible motion.

## Reproduce

Use the existing ComfyUI environment. Launch main.py with:
--extra-model-paths-config D:/comguopensource/config/extra_model_paths.yaml
--input-directory D:/comguopensource/artifacts/input
--output-directory D:/comguopensource/artifacts/output --reserve-vram 2

Place the documented reference image at artifacts/input/fox.jpg.
Run python scripts/prepare_workflow.py, then python scripts/run_generation.py.
The inspection script uses the existing ComfyUI Python environment (PyAV/Pillow).
API graph: workflows/ltx-i2v-api.json; UI graph: workflows/ltx-i2v-ui.json.
Weights and generated media are ignored by Git.

## Proposed Phase 3

Build a FastAPI adapter around this tested API graph with a single active GPU job,
validated image uploads, bounded parameters, persistent job metadata, ComfyUI
WebSocket progress, history reconciliation, and safe MP4 retrieval. Add integration
tests for upload rejection, graph parameters, execution failure, disconnect recovery,
and output path containment. Then build the responsive upload/prompt/preset/seed/
progress/preview/export interface. Camera presets should be described as prompt
presets until their actual effects are validated. No frontend has been started.
