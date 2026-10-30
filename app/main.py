"""Local-only OpenCinema service. Run exactly one Uvicorn worker."""
import asyncio
import copy
import base64
import binascii
import secrets
import io
import json
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import httpx
import websockets
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
PRESETS = {
    'dolly': 'A slow cinematic dolly inward toward the subject, gentle forward camera motion.',
    'orbit': 'A gentle cinematic orbit around the subject, subtle lateral perspective change.',
    'crane': 'A slow crane upward, gradually revealing the surrounding scene.',
    'static': 'A locked-off cinematic composition, steady camera, subtle natural subject movement.',
}
LIMIT = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000
PUBLIC_HOST = os.getenv('OPENCINEMA_PUBLIC_HOST', '').lower().strip()
DEMO_USER = os.getenv('OPENCINEMA_DEMO_USER', 'jury')
DEMO_PASSWORD = os.getenv('OPENCINEMA_DEMO_PASSWORD', '')
if PUBLIC_HOST and (not DEMO_PASSWORD or len(DEMO_PASSWORD) < 20):
    raise RuntimeError('Public mode requires OPENCINEMA_DEMO_PASSWORD (20+ characters)')
if PUBLIC_HOST and (':' in PUBLIC_HOST or '/' in PUBLIC_HOST or PUBLIC_HOST == '*'):
    raise RuntimeError('OPENCINEMA_PUBLIC_HOST must be one exact DNS hostname')


class DemoBasicAuth:
    """Protect all pages, API endpoints and video files in public-demo mode."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not PUBLIC_HOST:
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        authorization = headers.get(b'authorization', b'')
        valid = False
        if authorization.startswith(b'Basic '):
            try:
                decoded = base64.b64decode(authorization[6:], validate=True).decode('utf-8')
                user, password = decoded.split(':', 1)
                valid = secrets.compare_digest(user, DEMO_USER) and secrets.compare_digest(password, DEMO_PASSWORD)
            except (ValueError, UnicodeError, binascii.Error):
                pass
        if not valid:
            return await JSONResponse({'detail': 'Authentication required'}, status_code=401,
                headers={'WWW-Authenticate': 'Basic realm="OpenCinema Jury Demo"', 'Cache-Control': 'no-store'})(scope, receive, send)
        return await self.app(scope, receive, send)


class LocalUploadGuard:
    """Bound request bodies before multipart parsing; block cross-site POSTs."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        origin = headers.get(b'origin')
        expected = (('https' if PUBLIC_HOST else scope.get('scheme', 'http')) + '://' + headers.get(b'host', b'').decode()).encode()
        if (PUBLIC_HOST and not origin) or (origin and origin != expected):
            return await JSONResponse({'detail': 'Cross-origin requests are not allowed.'}, 403)(scope, receive, send)
        # Bound the entire multipart body, including chunked uploads and form fields.
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > LIMIT + 65536:
                return await JSONResponse({'detail': 'Upload exceeds 10 MiB plus form allowance.'}, 413)(scope, receive, send)
            if not message.get('more_body'):
                break
        delivered = False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()
        await self.app(scope, bounded_receive, send)


def workflow(image, prompt, seed, preset, job_id):
    graph = copy.deepcopy(json.loads((ROOT / 'workflows/ltx-i2v-api.json').read_text()))
    graph['78']['inputs']['image'] = image
    graph['6']['inputs']['text'] = prompt.strip() + '\n' + PRESETS[preset]
    graph['72']['inputs']['noise_seed'] = seed
    graph['81']['inputs']['filename_prefix'] = f'opencinema/{job_id}'
    return graph


def normalize_image(raw, mime):
    if mime not in ('image/png', 'image/jpeg', 'image/webp'):
        raise HTTPException(415, 'Use a PNG, JPEG or WebP image.')
    if len(raw) > LIMIT:
        raise HTTPException(413, 'Image must be at most 10 MiB.')
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.format not in ('PNG', 'JPEG', 'WEBP') or im.width * im.height > 20_000_000:
                raise ValueError()
            im.load()
            out = io.BytesIO()
            ImageOps.exif_transpose(im).convert('RGB').save(out, format='PNG')
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(422, 'Invalid image or image exceeds 20 megapixels.')


def safe_output(item, job_id):
    name = item.get('filename', '')
    folder = item.get('subfolder', '')
    if (item.get('type') != 'output' or folder != 'opencinema'
            or not name.startswith(job_id + '_') or not name.endswith('.mp4')
            or any(c in name for c in '/\\:') or '..' in name):
        raise ValueError('Unexpected ComfyUI output location')
    return {'filename': name, 'subfolder': folder, 'type': 'output'}


class Comfy:
    def __init__(self, url):
        self.url = url.rstrip('/')
        self.http = httpx.AsyncClient(base_url=self.url, timeout=30)

    async def get(self, path):
        r = await self.http.get(path)
        r.raise_for_status()
        return r.json()

    async def submit(self, job, image):
        queue = await self.get('/queue')
        if queue.get('queue_running') or queue.get('queue_pending'):
            raise ValueError('ComfyUI is busy with another job. Retry when its queue is empty.')
        r = await self.http.post('/upload/image', files={'image': (job['id'] + '.png', image, 'image/png')}, data={'type': 'input', 'overwrite': 'false'})
        r.raise_for_status()
        uploaded = r.json()
        name = uploaded['name']
        if uploaded.get('subfolder'):
            name = uploaded['subfolder'] + '/' + name
        graph = workflow(name, job['prompt'], job['seed'], job['preset'], job['id'])
        r = await self.http.post('/prompt', json={'prompt': graph, 'client_id': job['id'], 'extra_data': {'opencinema_id': job['id']}})
        if r.status_code != 200 or r.json().get('node_errors'):
            raise ValueError('ComfyUI rejected the workflow. Check required models and nodes in the ComfyUI console.')
        return r.json()['prompt_id'], graph


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.directory / 'jobs.sqlite', check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, active INTEGER, body TEXT)')
        self.db.execute('CREATE UNIQUE INDEX IF NOT EXISTS one_active ON jobs(active) WHERE active=1')
        self.db.commit()

    def save(self, job):
        active = int(job['status'] not in ('completed', 'failed'))
        self.db.execute('INSERT INTO jobs VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET active=excluded.active, body=excluded.body', (job['id'], active, json.dumps(job)))
        self.db.commit()

    def get(self, jid):
        row = self.db.execute('SELECT body FROM jobs WHERE id=?', (jid,)).fetchone()
        if not row:
            raise HTTPException(404, 'Job not found.')
        return json.loads(row[0])

    def active(self):
        row = self.db.execute('SELECT body FROM jobs WHERE active=1').fetchone()
        return json.loads(row[0]) if row else None


def create_app(data=None, client=None):
    store = Store(data or os.getenv('OPENCINEMA_DATA', str(ROOT / 'artifacts/studio')))
    comfy = client or Comfy(os.getenv('COMFY_URL', 'http://127.0.0.1:8188'))
    lock = asyncio.Lock()

    async def reconcile(job):
        pid = job.get('prompt_id')
        if not pid:
            # Never blindly resubmit after an ambiguous POST or process crash.
            history = await comfy.get('/history')
            queue = await comfy.get('/queue')
            entries = [v['prompt'] for v in history.values()] + queue.get('queue_running', []) + queue.get('queue_pending', [])
            for entry in entries:
                if len(entry) > 3 and entry[3].get('opencinema_id') == job['id']:
                    pid = job['prompt_id'] = entry[1]
                    break
            if not pid:
                job.update(status='failed', message='Submission was interrupted; no matching job in ComfyUI history or queue. Retry explicitly.')
                store.save(job)
                return
        history = await comfy.get('/history/' + pid)
        record = history.get(pid)
        if record:
            status = record.get('status', {})
            if status.get('status_str') == 'error':
                job.update(status='failed', message='ComfyUI generation failed. Check its console for model, memory or node errors.')
            elif status.get('completed'):
                outputs = record.get('outputs', {}).get('81', {})
                items = [v for values in outputs.values() if isinstance(values, list) for v in values if isinstance(v, dict) and str(v.get('filename', '')).endswith('.mp4')]
                if not items:
                    raise ValueError('Completed workflow did not return an MP4.')
                params = safe_output(items[0], job['id'])
                r = await comfy.http.get('/view', params=params)
                r.raise_for_status()
                if len(r.content) < 12 or r.content[4:8] != b'ftyp':
                    raise ValueError('ComfyUI returned an invalid MP4.')
                (store.directory / (job['id'] + '.mp4')).write_bytes(r.content)
                (store.directory / (job['id'] + '-history.json')).write_text(json.dumps(record, indent=2))
                job.update(status='completed', progress=100, message='Your film is ready.', finished=time.time())
            store.save(job)
            return
        queue = await comfy.get('/queue')
        running = [x[1] for x in queue.get('queue_running', [])]
        pending = [x[1] for x in queue.get('queue_pending', [])]
        if pid in running:
            job['status'] = 'running'
            if not str(job.get('message', '')).startswith('Sampling'):
                job['message'] = 'Generating locally · model loading, sampling or decoding'
        elif pid in pending:
            job.update(status='queued', message='Queued in ComfyUI')
        else:
            job.update(status='failed', message='Job disappeared from ComfyUI queue and history. It may have restarted. Retry explicitly.')
        store.save(job)

    async def monitor():
        while True:
            async with lock:
                job = store.active()
                if job:
                    try:
                        await reconcile(job)
                    except (httpx.HTTPError, OSError):
                        job['message'] = 'Connection lost. Waiting for ComfyUI; job remains reserved.'
                        store.save(job)
                    except ValueError as e:
                        job.update(status='failed', message=str(e))
                        store.save(job)
            await asyncio.sleep(2)

    async def events():
        while True:
            job = store.active()
            if not job:
                await asyncio.sleep(1)
                continue
            try:
                url = comfy.url.replace('http://', 'ws://').replace('https://', 'wss://')
                async with websockets.connect(url + '/ws?clientId=' + job['id']) as ws:
                    while store.active():
                        raw = await asyncio.wait_for(ws.recv(), timeout=10)
                        if not isinstance(raw, str):
                            continue
                        event = json.loads(raw)
                        d = event.get('data', {})
                        async with lock:
                            current = store.active()
                            if current and d.get('prompt_id') == current.get('prompt_id') and event['type'] == 'progress':
                                current.update(progress=round(95 * d['value'] / max(1, d['max'])), message=f"Sampling {d['value']} / {d['max']}")
                                store.save(current)
                                with (store.directory / (current['id'] + '-events.jsonl')).open('a') as log:
                                    log.write(json.dumps({'received': time.time(), **event}) + '\n')
            except (OSError, TimeoutError, websockets.WebSocketException):
                await asyncio.sleep(2)  # HTTP history remains authoritative.

    @asynccontextmanager
    async def lifespan(app):
        tasks = [asyncio.create_task(monitor()), asyncio.create_task(events())]
        yield
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        await comfy.http.aclose()
        store.db.close()

    app = FastAPI(title='OpenCinema Studio', lifespan=lifespan)
    app.add_middleware(LocalUploadGuard)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'] + ([PUBLIC_HOST] if PUBLIC_HOST else []))
    app.add_middleware(DemoBasicAuth)
    app.state.store, app.state.reconcile = store, reconcile

    @app.get('/api/health')
    async def health():
        try:
            stats = await comfy.get('/system_stats')
            return {'connected': True, 'devices': [d['name'] for d in stats.get('devices', [])], 'active_job': (store.active() or {}).get('id')}
        except (httpx.HTTPError, OSError):
            return {'connected': False, 'active_job': (store.active() or {}).get('id')}

    @app.post('/api/jobs', status_code=202)
    async def submit(image: UploadFile = File(...), prompt: str = Form(..., min_length=1, max_length=3000), seed: int = Form(20261029, ge=0, le=4294967295), preset: str = Form('static')):
        if preset not in PRESETS or not prompt.strip():
            raise HTTPException(422, 'Choose a valid camera preset and nonempty prompt.')
        raw = await image.read(LIMIT + 1)
        normalized = normalize_image(raw, image.content_type)
        async with lock:
            if store.active():
                raise HTTPException(409, 'One generation is already active. Wait for it to finish.')
            if PUBLIC_HOST:
                # Hard cap GPU usage per rolling 24h for a shared jury demo.
                recent = store.db.execute('SELECT body FROM jobs').fetchall()
                count = sum(json.loads(row[0]).get('created', 0) > time.time() - 86400 for row in recent)
                if count >= 10:
                    raise HTTPException(429, 'Daily demo generation limit reached. Please watch the recorded demo.')
            job = dict(id=uuid.uuid4().hex, prompt=prompt, seed=seed, preset=preset, status='submitting', progress=0, message='Submitting workflow', created=time.time())
            try:
                store.save(job)
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'One generation is already active.')
            (store.directory / (job['id'] + '.png')).write_bytes(normalized)
            try:
                pid, graph = await comfy.submit(job, normalized)
                job.update(prompt_id=pid, status='queued', message='Queued in ComfyUI')
                (store.directory / (job['id'] + '-workflow.json')).write_text(json.dumps(graph, indent=2))
            except ValueError as e:
                job.update(status='failed', message=str(e))
            except (httpx.HTTPError, OSError):
                job.update(message='Submission connection interrupted. Reconciling with ComfyUI before allowing another job.')
            store.save(job)
            return job

    @app.get('/api/jobs/{jid}')
    async def status(jid: str):
        return store.get(jid)

    @app.get('/api/jobs/{jid}/video')
    async def video(jid: str):
        job = store.get(jid)
        if job['status'] != 'completed':
            raise HTTPException(409, 'Video is not ready.')
        if len(jid) != 32 or any(c not in '0123456789abcdef' for c in jid):
            raise HTTPException(404)
        path = store.directory / (jid + '.mp4')
        if not path.is_file() or path.is_symlink():
            raise HTTPException(404, 'Video file is missing.')
        return FileResponse(path, media_type='video/mp4', filename=f'opencinema-{jid[:8]}.mp4', content_disposition_type='inline')

    app.mount('/', StaticFiles(directory=ROOT / 'app/static', html=True), name='studio')
    return app


app = create_app()
