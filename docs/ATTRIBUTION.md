# Attribution and model terms

## Current v2 pipeline

- **LTX-Video 13B v0.9.8 Distilled FP8**: [Lightricks model repository](https://huggingface.co/Lightricks/LTX-Video) and [official code](https://github.com/Lightricks/LTX-Video). Review the exact selected checkpoint's model-card license; application MIT terms do not apply to weights. The historical 2B license below is not a substitute for the 13B license.
- **ComfyUI-LTXVideo**: [Lightricks custom nodes](https://github.com/Lightricks/ComfyUI-LTXVideo), used as a separate ComfyUI dependency; its upstream license applies.
- **VideoHelperSuite**: [Kosinkadink/ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite), video loading/MP4 output; upstream terms apply.
- **Real-ESRGAN**: [xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN), BSD-3-Clause code; `RealESRGAN_x4plus.pth` is used only for the optional HD stage and is not distributed here. Review upstream model terms as well.
- **Current screenshot**: `screenshots/studio-v2-offline.png` is a capture of this repository's interface with offline fixture data, no uploaded image and no generated video. It is covered by the application's MIT license. The demo-video link is a placeholder.

## Preserved upstream and historical credits

OpenCinema application code is MIT, copyright OpenCinema contributors. This does not relicense models, ComfyUI, upstream templates, or example media.

- **ComfyUI**: [comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI), GPL-3.0. Runs as a separate local service over HTTP/WebSocket; its source is not bundled here.
- **Workflow template**: adapted from the `ltxv_image_to_video.json` bundled with `comfyui-workflow-templates` 0.11.98. Upstream: [Comfy-Org/workflow_templates](https://github.com/Comfy-Org/workflow_templates). The original is preserved and changes are listed in `workflow-provenance.md`; upstream terms remain applicable to the original template.
- **LTX-Video 2B v0.9.5**, Lightricks: [model card](https://huggingface.co/Lightricks/LTX-Video). This exact release uses the [LTX Video 2B 0.9.5 Open RAIL-M license dated March 5, 2025](https://huggingface.co/Lightricks/LTX-Video/blob/main/ltx-video-2b-v0.9.5.license.txt), with use restrictions. It is open weights, not MIT. Model users must comply with those restrictions. Review the full license before use or distribution; weights are not included in this repository.
- **Scaled FP8 T5 XXL**: [comfyanonymous/flux_text_encoders](https://huggingface.co/comfyanonymous/flux_text_encoders), repository labeled Apache-2.0. Exact tested filename: `t5xxl_fp8_e4m3fn_scaled.safetensors`. This encoder is loaded with ComfyUI's `ltxv` CLIP type; no FLUX image model is used.
- **Engineering test image**: [ComfyUI LTX fox example](https://comfyanonymous.github.io/ComfyUI_examples/ltxv/fox.jpg). It is not an original OpenCinema asset. Local screenshots show this engineering result; confirm rights or replace it with an owned/licensed image before publishing promotional media. Do not assume that the app's MIT license covers the example photograph or its derivatives.

The workflow template repository is MIT-licensed; its full notice is preserved in [workflow-templates-MIT.txt](licenses/workflow-templates-MIT.txt). The fox screenshots and videos are excluded from the public source package pending rights confirmation. The public screenshot depicts an empty Studio workspace with a neutral prompt.

The application has no affiliation or endorsement from these projects. Generated output is subject to the model terms and rights in the input. Model license links were checked on 2026-10-30.
