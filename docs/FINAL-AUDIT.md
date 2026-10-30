# Final repository and submission audit

Checked 2026-10-30. No new features, inference runs or model downloads were introduced during final preparation.

## Source and privacy

- Reviewed the tracked source list, file sizes, generated-media exclusions and common secret patterns (private keys, GitHub tokens, AWS access keys, credential assignments and private Windows home paths). No matches remained after cleanup. This is a scoped source audit, not a guarantee against every possible secret format.
- Removed a personal home-directory path from the public report. The documented `D:/comguopensource` paths are deliberate setup examples and the configured model location.
- Git commits use the authenticated account's GitHub noreply identity rather than its personal email.
- No model weights, uploaded images, MP4s, SQLite databases, environments or runtime artifacts are tracked. `.gitignore` now also covers environment variants, private-key files and SQLite sidecars.
- Fox screenshots remain on disk but were removed from the index before the initial commit. The public screenshot is an empty Studio workspace with a neutral prompt. It is 95,915 bytes, the largest tracked file at the initial audit; no large files are included.
- App code is MIT. Included the upstream workflow-template MIT notice. LTX Open RAIL-M and encoder Apache-2.0 attribution remain separate. No assertion of publication rights for the fox image or its outputs is made.

## Fresh-clone installation

A real local Git clone was created under ignored `artifacts/final-audit/clean-clone` from commit `6a26dcc`. It contains no model files. Commands executed inside it:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --workers 1
```

The venv has `include-system-site-packages = false`. Installation succeeded. **20 tests passed in 5.27 seconds**, with one Starlette warning about its HTTPX test client; **no broken requirements**. The root environment also passed **20 tests in 6.53 seconds**, with one existing AnyIO alias warning. No dependency warning was suppressed or represented as a failure.

Fresh-clone HTTP smoke checks: `/` returned 200 with the neutral prompt; `/api/health` reported connected to the RTX 3060; ComfyUI `/object_info` listed both exact tested model filenames. We reused the existing ComfyUI process and D: storage. No weights were copied or downloaded. The tested venv package versions are captured in `requirements-lock.txt`; the final follow-up commit adds only audit/reproduction documentation and this lock, not application changes.

The clone was local because GitHub publication is still unavailable. Anonymous remote-clone verification cannot be claimed until publication succeeds.

## Workflow immutability

SHA-256 before and after preparation matched exactly:

| File | SHA-256 |
| --- | --- |
| `workflows/ltx-i2v-api.json` | `0948d96d663ffb9ed6843075c39b976208620abdef6e74c2d511bdf776b288ea` |
| `workflows/ltx-i2v-ui.json` | `ae9a27bd3ac83692c9267ffb6f85c08115af1001d5511b6280766847e80edc70` |
| `workflows/ltxv-official.json` | `8d41217612e91b4e067c71eaba261555b142d597b46ee7eca5bf3544ec9d80d7` |

Only the frontend default prompt was neutralized; backend injection continues to replace the graph's original fox prompt with user input.

## Public-link verification and blockers

Anonymous HTTP checks returned 200 for the official competition page, ComfyUI repository (redirecting to Comfy-Org), workflow-template repository, official LTX tutorial, upstream fox reference, LTX model card and v0.9.5 license, and the FP8 encoder repository. Registration and submission Typeform URLs timed out locally; the browser also timed out. Their links are confirmed on the official rules page, but form-specific questions could not be inspected.

The GitHub connector identifies `karatarassul4-max` but has no repository-creation capability. GitHub CLI was not found in PATH or standard install locations; noninteractive Git HTTPS credential lookup returned none. The available browser is signed out. The intended repository API returns **404 anonymously**; it is not published or publicly accessible. See `PUBLISH.md` for exact authentication/publication commands. Do not treat the intended URL as a live deliverable.

Official expanded rules require the ComfyUI app, public source/workflows/license/setup, a demo no longer than two minutes, and a social post linking the demo with `#OpenSourceHiggsfield`. They also require lawful/SFW work without unlicensed IP or likenesses, one entry per person, and consent to credited organizer featuring. Hosted execution is optional. Deadline remains October 30, 2026 at 9am Pacific / 16:00 UTC / 21:00 Asia/Qyzylorda.

Remaining: authenticate a publication-capable GitHub client; create/push and verify the public repository; confirm media rights or record with an owned input; upload demo and social post; check the form from a working network; obtain owner approval before submission. No hackathon form or social post has been submitted.
