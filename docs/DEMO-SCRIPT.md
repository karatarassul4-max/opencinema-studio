# 110-second demo script and asset selection

Record at 1080p with OBS or Windows recording. Use an owned/licensed image for publicly released footage. Do not show a mock output, imply a still screenshot is a generated video, or claim a fixed camera trajectory. Label any edit that skips generation time.

| Time | Screen | Narration |
| --- | --- | --- |
| 0–12s | Neutral Studio workspace | “This is OpenCinema Studio: an open-source image-to-video workspace powered by a real, local ComfyUI workflow.” |
| 12–28s | Upload licensed image; edit scene direction and seed | “Start with an opening frame, describe its next moment, and choose a reproducible seed. Camera presets add descriptive prompt guidance; they are not precise camera controls.” |
| 28–44s | Generate; show Studio status and matching ComfyUI queue | “FastAPI sends the validated image and a copy of our versioned graph to ComfyUI. LTX-Video 2B and scaled FP8 T5 run on this RTX 3060 with 12GB of VRAM.” |
| 44–57s | Sampling progress; clearly labeled time cut if needed | “Sampling progress comes from real WebSocket events. SQLite keeps the job reservation, and HTTP history recovery preserves the result after a disconnect.” |
| 57–74s | Play actual output; click Download MP4 | “This is the actual output: 512 by 320, 25 frames at 24 frames per second. It is a short feasibility preset with subtle movement. The MP4 can be played and downloaded directly.” |
| 74–94s | ComfyUI graph, architecture and tests | “The contribution is a simple creative interface with transparent, recoverable local execution. The graph, model hashes, setup instructions and tests are included so others can reproduce and extend it.” |
| 94–110s | Public README and repository | “The app is MIT-licensed, and the model licenses are documented separately. No paid inference service is required. OpenCinema makes a real ComfyUI pipeline easier to use, inspect and share.” |

## Best available assets

- **Public hero screenshot:** `docs/screenshots/studio-neutral.jpg`. It contains the UI and neutral prompt, with no third-party example photo or generated result.
- **Local desktop proof:** `docs/screenshots/studio-desktop.jpg` (ignored). Best overview of the working upload/result UI; shows fox imagery and requires rights review before publication.
- **Local mobile proof:** `docs/screenshots/studio-mobile.jpg` (ignored). Demonstrates the responsive layout; same media-rights caveat.
- **Primary actual output:** `artifacts/studio/d7238fb5e9a84f41b19178908db6cfbe.mp4`. Strongest verification chain: all frames decoded, browser playback confirmed, downloaded bytes matched SHA-256. Execution 113.49 seconds. 512×320, 25 frames, 24fps; motion is subtle.
- **Secondary actual output:** `artifacts/studio/e88c23c07e4048bf99a86609a5eaad72.mp4`. Seed 20261030, warm execution 10.12 seconds, 30 saved WebSocket progress events. Do not present this as cold-start performance.

These existing outputs are engineering evidence from the upstream fox example, not rights-cleared promotional assets. Do not publish them until rights are established. Recording/uploading the final demo and social post remain owner actions; no demo URL is invented in the submission copy.
