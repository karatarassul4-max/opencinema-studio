# Submission and demo checklist

Official rules: https://comfy.org/open-source-higgsfield (checked 2026-10-30).
The published deadline is **October 30, 2026, 9am Pacific**, corresponding to **21:00 Asia/Qyzylorda**. Confirm the submission form and any additional fields before sending.

## Ready locally

- [x] Real ComfyUI HTTP/WebSocket integration and LTX inference.
- [x] Working upload → prompt graph → GPU generation → browser playback → MP4 download.
- [x] MIT application license and Windows setup instructions.
- [x] Reproducible graph, exact model filenames, hashes and dependency versions.
- [x] Tests and engineering evidence, including failed-run limitations.
- [x] Responsive Studio UI and local screenshots.
- [x] No partner inference nodes or closed paid inference APIs.

## Before submission

- [ ] Publish the Git repository and verify setup from a fresh clone. No public repository has been created in this phase.
- [ ] Replace the engineering fox input with an owned/licensed demo image and record a stronger motion example if practical. Current motion is subtle.
- [ ] Record and share the demo video, with the app working and an explanation of how it was built.
- [ ] Review screenshot/media rights before publishing. Never add weights or generated videos to Git.
- [ ] Complete registration and the official submission form; check all current form requirements.
- [ ] Verify the public links work without authentication.

The official page requires an open-source license and setup instructions. Local execution is allowed. Its Open Weights Only category excludes partner nodes and closed APIs. The LTX VFX bonus requires LTX as the core video model; this app satisfies that model condition, but a generic image-to-video fox test does not establish a compelling VFX entry or guarantee eligibility/prizes. Innovation must be explained in the demo for the innovation category. Do not claim a novel model, validated camera control, or real-time cold generation.

## Suggested 90–120 second recording

1. **0:00–0:15** — Show Studio and a licensed source frame. Explain: “OpenCinema is an open-source, local image-to-video workspace built around a real ComfyUI graph.”
2. **0:15–0:35** — Upload, edit scene direction, choose camera inspiration, set a seed. Say the presets are prompt templates, not calibrated trajectories.
3. **0:35–0:55** — Generate. Show the corresponding ComfyUI queue and graph plus Studio sampling progress. If cutting the wait, label the time jump and state the actual run duration.
4. **0:55–1:15** — Play the actual output and download it. Describe visible results honestly, including limited motion or artifacts.
5. **1:15–1:40** — Explain FastAPI, persisted single-job reservation, WebSocket progress with history recovery, FP8 T5 and tiled decoding on a 12GB GPU. Show architecture diagram and versioned graph.
6. **1:40–2:00** — Show public repository, license and setup instructions. Position the contribution as an approachable, reproducible local workflow UI; do not claim unsupported novelty.

Use OBS or the Windows recording tool at 1080p. Hide private paths and unrelated windows. Capture an actual generation, not a fabricated spinner. Keep full raw evidence locally and share MP4/demo externally rather than committing it.

## Final rules verification, October 30

The official accordion sections were expanded in the browser. Required: public GitHub app code, workflow files, open-source license and local setup instructions; a demo of at most two minutes; a social post linking the demo on Reddit, X, Instagram, LinkedIn, YouTube or TikTok with `#OpenSourceHiggsfield`. A deployed try-it link is optional. Entries must use ComfyUI, be lawful and SFW, contain no unlicensed IP or likenesses, and are limited to one submission per person. Submission grants the named organizers permission to feature the work with credit. The owner must review these terms before submitting.

Official submission form: https://form.typeform.com/to/V1dSQrkS
Registration: https://form.typeform.com/to/Ayn9Cwfj
Prepared copy: [FINAL-SUBMISSION.md](FINAL-SUBMISSION.md). Recording script and asset selection: [DEMO-SCRIPT.md](DEMO-SCRIPT.md).
