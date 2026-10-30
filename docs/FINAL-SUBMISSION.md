# OpenCinema Studio — submission copy

Prepared in English. Do not submit until the repository, demo and social links are verified and the owner approves submission.

## Project description

OpenCinema Studio is an open-source, local image-to-video workspace built around real ComfyUI workflows. A filmmaker uploads an opening frame, describes the scene, selects descriptive camera inspiration and a seed, then generates, previews and downloads an MP4. The interface makes a reproducible ComfyUI pipeline accessible without hiding the graph or relying on paid inference APIs.

## Technical implementation

The application uses a FastAPI backend and a responsive HTML/CSS/JavaScript frontend. Each job deep-copies a version-controlled ComfyUI API graph and injects a validated image, prompt, seed and prompt-based camera preset. ComfyUI performs all inference locally using LTX-Video 2B v0.9.5 and the scaled FP8 T5 XXL encoder. The tested configuration uses dynamic offloading and tiled VAE decoding on an NVIDIA RTX 3060 with 12GB VRAM.

SQLite persists job state and enforces one active Studio job. ComfyUI WebSocket events report sampling progress; HTTP queue and history reconciliation recover status after connection loss or backend restart. Upload validation, bounded request bodies and job-specific MP4 retrieval protect the local workflow. The default is 512×320, 25 frames, 24fps and batch size one.

## Innovation and contribution

Our contribution is a focused filmmaking interface paired with transparent, recoverable local execution on a consumer GPU. Direction, reproducibility and operational reliability are brought into one workspace: users can control the prompt and seed, inspect the exact workflow, watch actual sampling progress, and recover a result after reconnecting. Camera presets are explicitly presented as descriptive prompt guidance, not precise or experimentally validated camera trajectories. We do not claim a new model or a new camera-control algorithm.

## Reproducibility and validation

The repository includes Windows setup instructions, pinned application dependencies, the tested ComfyUI graph, exact model filenames and SHA-256 hashes, upstream attribution, an architecture diagram and automated tests. Models and generated media are excluded from Git. Existing weights can be reused through the running local ComfyUI service without downloading another copy.

Twenty automated tests passed in Phase 3. Two real browser-driven generations completed, including image upload, workflow submission, MP4 playback and download verification. The first Studio generation took 113.49 seconds; a follow-up with loaded models and cached nodes took 10.12 seconds. These are individual measurements, not performance guarantees. The tested clip lasts about 1.04 seconds and shows subtle motion. Full evidence and limitations are documented.

## Categories and dependencies

The inference workflow uses open weights and no partner inference nodes or closed-source inference APIs. LTX is the core video model. LTX bonus consideration is requested only subject to the judges' VFX criteria; the current generic image-to-video workflow does not establish a sophisticated VFX effect. Application code is MIT. LTX 2B v0.9.5 uses its separate Open RAIL-M model license; model terms remain applicable.

## Links to fill only after verification

- Repository: pending publication to `karatarassul4-max/opencinema-studio`.
- Demo video (at most 2 minutes): pending recording and upload.
- Social post linking the demo and tagging `#OpenSourceHiggsfield`: pending.
- Hosted app: not provided; local execution instructions are included. A deployed link is optional under the official rules.

## Final approval

The owner must review the final links and approve the hackathon submission. No form has been submitted.
