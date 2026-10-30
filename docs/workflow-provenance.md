# Phase 2 workflow provenance

The baseline is the `ltxv_image_to_video.json` template bundled with
`comfyui-workflow-templates==0.11.98`, preserved as `workflows/ltxv-official.json`.
Official guide: https://docs.comfy.org/tutorials/video/ltxv

The runnable API graph and editable UI graph are produced by
`python scripts/prepare_workflow.py`. They preserve the template connections.
Changes: 512x320, 25 frames, batch 1, 24 fps for both conditioning and export,
seed 20261029, image strength 0.85, scaled FP8 T5, tiled VAE decode (128/32 spatial, 8/4 temporal), MP4/H.264.
Euler, 30 steps, CFG 3 and scheduler settings come from the original graph.
The positive/negative prompts are the original fox example prompts.

Reference image: https://comfyanonymous.github.io/ComfyUI_examples/ltxv/fox.jpg
Used for an engineering test; not claimed as an original OpenCinema asset.
Choose an owned/licensed image for the public demo.

## Scaled FP8 encoder compatibility

Publisher file:
https://huggingface.co/comfyanonymous/flux_text_encoders/blob/main/t5xxl_fp8_e4m3fn_scaled.safetensors

This is the scaled variant, approximately 5.16 GB, not the 4.89 GB unscaled file.
The installed ComfyUI `comfy/sd.py` routes the LTXV CLIP type through
`ltxv_te(**t5xxl_detect(...))`; `ltxv_te` delegates to the Mochi T5 implementation,
and `sd3_clip.t5_xxl_detect` passes detected quantization metadata onward.
This supports the format at the loader level. A successful actual generation
is the required end-to-end compatibility check, recorded separately.

Downloads go directly into ignored `models/` folders on D:, without an HF cache
copy. `config/models.lock.json` records sizes and publisher SHA-256 verification.
No core dependency upgrades or custom-node installation are planned.

## Measurement

`scripts/run_generation.py` writes raw WebSocket events, submission response,
ComfyUI history, the exact submitted graph, and requested one-second metric samples into
an ignored, timestamped `artifacts/run-*` directory. Device-wide VRAM includes
desktop applications; host RAM includes all applications. ComfyUI RSS is also
recorded separately. Actual Phase 2 sampling averaged 2.70 seconds because of collection overhead; short peaks may be missed.

The 49-frame initial attempt did not produce an MP4. The 25-frame graph succeeded; see the Phase 2 and Phase 3 reports for measurements and quality limits.
