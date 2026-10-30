"""Download only the two approved weights directly to D:, checking publisher hashes."""
import hashlib
import json
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ('Lightricks/LTX-Video', 'ltx-video-2b-v0.9.5.safetensors', 'checkpoints', '720d15c9f19f7d0f6b2a92bbbc34410e2cfb2f6856a100b38f734fbf973d4adf'),
    ('comfyanonymous/flux_text_encoders', 't5xxl_fp8_e4m3fn_scaled.safetensors', 'text_encoders', 'a498f0485dc9536735258018417c3fd7758dc3bccc0a645feaa472b34955557a'),
]
records = []
for repo, name, folder, expected in FILES:
    dest = ROOT / 'models' / folder / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f'https://huggingface.co/{repo}/resolve/main/{name}'
    if not dest.exists():
        part = dest.with_suffix('.part')
        with requests.get(url, stream=True, timeout=(30, 120)) as response:
            response.raise_for_status()
            size = 0
            mark = 0
            with part.open('wb') as output:
                for chunk in response.iter_content(8 * 1024 * 1024):
                    output.write(chunk)
                    size += len(chunk)
                    if size - mark >= 512 * 1024 * 1024:
                        print(f'{name}: {size / 2**30:.2f} GiB', flush=True)
                        mark = size
        part.rename(dest)
    digest = hashlib.file_digest(dest.open('rb'), 'sha256').hexdigest()
    if digest != expected:
        raise RuntimeError(f'Hash mismatch: {name}: {digest}')
    records.append({'filename': name, 'source': url, 'sha256': digest, 'bytes': dest.stat().st_size})
    print(f'VERIFIED {name}', flush=True)
(ROOT / 'config' / 'models.lock.json').write_text(json.dumps(records, indent=2))
