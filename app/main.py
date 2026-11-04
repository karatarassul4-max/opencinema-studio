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
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
from .director import CAMERAS as PRESETS, SCENES, MOODS, direct
from .benchmark import Benchmark, probe_video
from .gpu_monitor import GPUMonitor
from .durations import DURATIONS, duration_settings
from .settings import COMFY_URL, INFERENCE_ENABLED, data_path
from .hd_export import hd_workflow, validate_hd_output, inspect_source
LIMIT = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000
PUBLIC_HOST = os.getenv('OPENCINEMA_V2_PUBLIC_HOST', '').lower().strip()
DEMO_USER = os.getenv('OPENCINEMA_V2_DEMO_USER', 'jury')
DEMO_PASSWORD = os.getenv('OPENCINEMA_V2_DEMO_PASSWORD', '')
if PUBLIC_HOST and (not DEMO_PASSWORD or len(DEMO_PASSWORD) < 20):
    raise RuntimeError('Public mode requires OPENCINEMA_V2_DEMO_PASSWORD (20+ characters)')
if PUBLIC_HOST and (':' in PUBLIC_HOST or '/' in PUBLIC_HOST or PUBLIC_HOST == '*'):
    raise RuntimeError('OPENCINEMA_V2_PUBLIC_HOST must be one exact DNS hostname')


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
                valid = secrets.compare_digest(user.encode('utf-8'), DEMO_USER.encode('utf-8')) and secrets.compare_digest(password.encode('utf-8'), DEMO_PASSWORD.encode('utf-8'))
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


def workflow(image, prompt, seed, preset, job_id, scene=None, mood="calm", strength=0.8, frames=25, steps=8):
    mode = duration_settings(frames)
    if steps not in (6, 8) or (steps == 6 and frames != 97):
        raise ValueError('6 steps is supported only for 97 frames.')
    if steps == 6:
        mode = {**mode, 'workflow': 'ltx13b-v2-97f-6step-test-api.json'}
    graph = copy.deepcopy(json.loads((ROOT / 'workflows' / mode['workflow']).read_text(encoding='utf-8')))
    if graph['1338']['inputs']['num_frames'] != frames:
        raise ValueError('Workflow frame count does not match the selected duration.')
    graph['1206']['inputs']['image'] = image
    if strength not in (0.8, 0.85):
        raise ValueError('Unsupported conditioning strength.')
    graph['1338']['inputs']['strength'] = strength
    graph['6']['inputs']['text'] = direct(prompt, scene, preset, mood)['prompt']
    graph['1336']['inputs']['filename_prefix'] = f'opencinema/{job_id}'
    graph['1507']['inputs']['noise_seed'] = seed
    graph['1336']['inputs']['save_output'] = True
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

    async def submit_hd(self, job, source_path):
        queue = await self.get('/queue')
        if queue.get('queue_running') or queue.get('queue_pending'):
            raise ValueError('ComfyUI is busy with another job. Retry when its queue is empty.')
        graph = hd_workflow(source_path, job['id'], job['source_video'])
        if hasattr(self, 'on_prompt_sent'):
            self.on_prompt_sent(job)
        r = await self.http.post('/prompt', json={
            'prompt': graph, 'client_id': job['id'],
            'extra_data': {'opencinema_id': job['id']}})
        if r.status_code >= 500:
            r.raise_for_status()
        try:
            result = r.json()
        except ValueError:
            raise httpx.ReadError('Ambiguous HD prompt response')
        if r.status_code >= 400 or result.get('node_errors'):
            raise ValueError('ComfyUI rejected the HD workflow. Check VHS and RealESRGAN nodes.')
        if not isinstance(result.get('prompt_id'), str) or not result['prompt_id']:
            raise httpx.ReadError('Missing HD prompt ID; reconcile before retrying')
        return result['prompt_id'], graph

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
        graph = workflow(name, job['prompt'], job['seed'], job['preset'], job['id'], job.get('scene'), job.get('mood', 'calm'), job.get('strength', 0.8), job.get('frames', 25), job.get('steps', 8))
        if hasattr(self, 'on_prompt_sent'):
            self.on_prompt_sent(job)
        r = await self.http.post('/prompt', json={'prompt': graph, 'client_id': job['id'], 'extra_data': {'opencinema_id': job['id']}})
        if r.status_code >= 500:
            r.raise_for_status()
        try:
            result = r.json()
        except ValueError:
            raise httpx.ReadError('Ambiguous prompt response')
        if 400 <= r.status_code < 500 or result.get('node_errors'):
            raise ValueError('ComfyUI rejected the workflow. Check required models and nodes in the ComfyUI console.')
        if not isinstance(result.get('prompt_id'), str) or not result['prompt_id']:
            raise httpx.ReadError('Missing prompt ID; reconcile before retrying')
        return result['prompt_id'], graph


class Store:
    def __init__(self, directory):
        self.directory = data_path(directory)
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


def create_app(data=None, client=None, benchmark=None, gpu_monitor=None, output_probe=None):
    store = Store(data_path(data))
    comfy = client or Comfy(COMFY_URL)
    enabled = client is not None or INFERENCE_ENABLED
    lock = asyncio.Lock()
    bench = benchmark or Benchmark()
    gpu = gpu_monitor or GPUMonitor(store.directory,
        enabled=os.getenv('OPENCINEMA_V2_GPU_MONITOR', '0') == '1')
    inspect_output = output_probe or probe_video

    # HD_METRICS_V2_PATCH: timing and optional GPU telemetry for HD exports.
    def save_job(job):
        if job['status'] in ('completed', 'failed'):
            bench.finish(job)
            gpu.stop(job['id'])
        store.save(job)

    def prompt_sent(job):
        bench.mark(job, 'prompt_sent', 'before POST /prompt; includes submission latency')
        store.save(job)
    comfy.on_prompt_sent = prompt_sent

    def handle_event(job, event):
        data = event.get('data', {})
        if not isinstance(data, dict) or not job.get('prompt_id') or data.get('prompt_id') != job['prompt_id']:
            return
        kind = event.get('type')
        if kind in ('execution_start', 'executing', 'progress'):
            bench.mark(job, 'inference_started', 'WebSocket '+kind+' received; approximate')
        if kind == 'execution_success':
            bench.mark(job, 'inference_completed', 'WebSocket execution_success received; approximate')
        if kind == 'progress' and job.get('kind') != 'hd' and isinstance(data.get('value'), (int,float)) and isinstance(data.get('max'),(int,float)):
            job.update(progress=round(95 * data['value'] / max(1,data['max'])), message=f"Sampling {data['value']} / {data['max']}")
        save_job(job)


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
                save_job(job)
                return
        history = await comfy.get('/history/' + pid)
        record = history.get(pid)
        if record:
            bench.history(job, record)
            status = record.get('status', {})
            if status.get('status_str') == 'error':
                bench.mark(job, 'inference_completed', 'execution failure observed in HTTP history; approximate')
                job.update(status='failed', message='ComfyUI generation failed. Check its console for model, memory or node errors.')
            elif status.get('completed'):
                bench.mark(job, 'inference_completed', 'completion observed in HTTP history; approximate')
                save_job(job)
                outputs = record.get('outputs', {}).get('5' if job.get('kind') == 'hd' else '1336', {})
                items = [v for values in outputs.values() if isinstance(values, list) for v in values if isinstance(v, dict) and str(v.get('filename', '')).endswith('.mp4')]
                if not items:
                    raise ValueError('Completed workflow did not return an MP4.')
                params = validate_hd_output(items[0], job['id']) if job.get('kind') == 'hd' else safe_output(items[0], job['id'])
                bench.mark(job, 'retrieval_started')
                r = await comfy.http.get('/view', params=params)
                r.raise_for_status()
                if len(r.content) < 12 or r.content[4:8] != b'ftyp':
                    raise ValueError('ComfyUI returned an invalid MP4.')
                video_path = store.directory / (job['id'] + '.mp4')
                video_path.write_bytes(r.content)
                bench.mark(job, 'retrieval_completed')
                job.setdefault('benchmark', {})['output'] = {**await inspect_output(video_path), 'file_size_bytes': len(r.content)}
                if job.get('kind') == 'hd':
                    observed = job['benchmark']['output']
                    expected = job['settings']
                    if (observed.get('width') != expected['width'] or observed.get('height') != expected['height']
                            or observed.get('frames') != job['frames']):
                        video_path.unlink(missing_ok=True)
                        raise ValueError('HD output metadata mismatch; export was rejected.')
                (store.directory / (job['id'] + '-history.json')).write_text(json.dumps(record, indent=2))
                job.update(status='completed', progress=100, message='Your HD film is ready.' if job.get('kind') == 'hd' else 'Your film is ready.', finished=time.time())
            save_job(job)
            return
        queue = await comfy.get('/queue')
        running = [x[1] for x in queue.get('queue_running', [])]
        pending = [x[1] for x in queue.get('queue_pending', [])]
        if pid in running:
            bench.mark(job, 'inference_started', 'first observed in running queue; approximate')
            job['status'] = 'running'
            if job.get('kind') == 'hd':
                job['message'] = 'Upscaling video with RealESRGAN; please wait'
            elif not str(job.get('message', '')).startswith('Sampling'):
                job['message'] = 'Generating locally: model loading, sampling or decoding'
        elif pid in pending:
            job.update(status='queued', message='Queued in ComfyUI')
        else:
            job.update(status='failed', message='Job disappeared from ComfyUI queue and history. It may have restarted. Retry explicitly.')
        save_job(job)

    async def monitor():
        while True:
            async with lock:
                job = store.active()
                if job:
                    try:
                        await reconcile(job)
                    except (httpx.HTTPError, OSError):
                        job['message'] = 'Connection lost. Waiting for ComfyUI; job remains reserved.'
                        save_job(job)
                    except ValueError as e:
                        job.update(status='failed', message=str(e))
                        save_job(job)
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
                            if current:
                                handle_event(current, event)
            except (OSError, TimeoutError, websockets.WebSocketException):
                await asyncio.sleep(2)  # HTTP history remains authoritative.

    @asynccontextmanager
    async def lifespan(app):
        tasks = [asyncio.create_task(monitor()), asyncio.create_task(events())] if enabled else []
        yield
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        await gpu.close()
        await comfy.http.aclose()
        store.db.close()

    app = FastAPI(title='OpenCinema Studio v2', lifespan=lifespan)
    app.add_middleware(LocalUploadGuard)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'] + ([PUBLIC_HOST] if PUBLIC_HOST else []))
    app.add_middleware(DemoBasicAuth)
    app.state.store, app.state.reconcile = store, reconcile
    app.state.benchmark, app.state.gpu, app.state.handle_event = bench, gpu, handle_event

    @app.get('/api/health')
    async def health():
        if not enabled:
            return {'connected': False, 'inference_enabled': False, 'active_job': (store.active() or {}).get('id')}
        try:
            stats = await comfy.get('/system_stats')
            return {'connected': True, 'inference_enabled': True, 'devices': [d['name'] for d in stats.get('devices', [])], 'active_job': (store.active() or {}).get('id')}
        except (httpx.HTTPError, OSError):
            return {'connected': False, 'active_job': (store.active() or {}).get('id')}

    @app.get('/api/benchmarks')
    async def benchmarks(frames: int | None = Query(None), limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0)):
        if frames is not None and frames not in DURATIONS:
            raise HTTPException(422, 'Unsupported frame filter.')
        where = "active=0"
        values = []
        if frames is not None:
            where += " AND COALESCE(json_extract(body, '$.frames'), json_extract(body, '$.settings.frames'))=?"
            values.append(frames)
        rows = store.db.execute("SELECT body FROM jobs WHERE " + where + " ORDER BY json_extract(body, '$.created') DESC, id DESC LIMIT ? OFFSET ?", (*values, limit, offset)).fetchall()
        results = []
        for row in rows:
            job = json.loads(row[0])
            results.append({key:job.get(key) for key in ('id','kind','source_job_id','created','finished','status','message','seed','strength','frames','settings','benchmark')})
            if job.get('kind') == 'hd' and isinstance(job.get('created'), (int, float)) and isinstance(job.get('finished'), (int, float)):
                results[-1]['elapsed_seconds'] = max(0.0, job['finished'] - job['created'])
            results[-1]['gpu'] = gpu.summary(job['id'])
        return {'items': results, 'offset': offset, 'limit': limit, 'scope': 'v2 only',
                'manual_baselines_note': '25 and 49 frames: approximately 60 seconds each, manually reported; not instrumented measurements.'}

    @app.get('/api/presets')
    async def presets():
        return {'scenes': SCENES, 'cameras': PRESETS, 'moods': MOODS, 'strengths': [0.8, 0.85], 'durations': [duration_settings(frames) for frames in DURATIONS]}

    @app.post('/api/director')
    async def director(prompt: str = Form(..., min_length=1, max_length=3000), scene: str = Form('product'), preset: str = Form('static'), mood: str = Form('calm')):
        try:
            return direct(prompt, scene, preset, mood)
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.post('/api/jobs', status_code=202)
    async def submit(image: UploadFile = File(...), prompt: str = Form(..., min_length=1, max_length=3000), seed: int = Form(20261029, ge=0, le=4294967295), preset: str = Form('static'), scene: str | None = Form(None), mood: str = Form('calm'), strength: float = Form(0.8), frames: int = Form(25), steps: int = Form(8)):
        if not enabled:
            raise HTTPException(403, 'GPU generation is disabled. Approve a shared-GPU test before enabling v2 inference.')
        try:
            mode = duration_settings(frames)
            if steps not in (6, 8) or (steps == 6 and frames != 97):
                raise ValueError('6 steps is supported only for 97 frames.')
            if steps == 6:
                mode = {**mode, 'workflow': 'ltx13b-v2-97f-6step-test-api.json'}
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        if strength not in (0.8, 0.85) or mood not in MOODS or (scene is not None and scene not in SCENES):
            raise HTTPException(422, 'Unsupported generation settings.')
        if preset not in PRESETS or not prompt.strip():
            raise HTTPException(422, 'Choose a valid camera preset and nonempty prompt.')
        direction = direct(prompt, scene, preset, mood)
        raw = await image.read(LIMIT + 1)
        normalized = normalize_image(raw, image.content_type)
        async with lock:
            if store.active():
                raise HTTPException(409, 'One generation is already active. Wait for it to finish.')
            if PUBLIC_HOST:
                # Hard cap GPU usage per rolling 24h for a shared jury demo.
                recent = store.db.execute('SELECT body FROM jobs').fetchall()
                count = sum(json.loads(row[0]).get('created', 0) > time.time() - 86400 for row in recent)
                if count >= 30:
                    raise HTTPException(429, 'Daily demo generation limit reached. Please watch the recorded demo.')
            job = dict(id=uuid.uuid4().hex, prompt=prompt, seed=seed, preset=preset, scene=scene, mood=mood, strength=strength, frames=frames, steps=steps, camera_source=direction['camera_source'], camera_note=direction['camera_note'], enhanced_prompt=direction['prompt'], settings={'width': 512, 'height': 320, 'frames': frames, 'fps': mode['fps'], 'duration_seconds': mode['duration_seconds'], 'workflow': mode['workflow'], 'experimental': mode['experimental'], 'steps': steps, 'strength': strength, 'model': 'LTX-Video 13B 0.9.8 Distilled FP8'}, status='submitting', progress=0, message='Submitting workflow', created=time.time())
            bench.mark(job, 'submitted', 'v2 accepted validated job')
            try:
                save_job(job)
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'One generation is already active.')
            gpu.start(job['id'])
            try:
                (store.directory / (job['id'] + '.png')).write_bytes(normalized)
                pid, graph = await comfy.submit(job, normalized)
                bench.mark(job, 'accepted', 'POST /prompt response received')
                job.update(prompt_id=pid, status='queued', message='Queued in ComfyUI')
                (store.directory / (job['id'] + '-workflow.json')).write_text(json.dumps(graph, indent=2))
            except ValueError as e:
                job.update(status='failed', message=str(e))
            except (httpx.HTTPError, OSError):
                job.update(message='Submission connection interrupted. Reconciling with ComfyUI before allowing another job.')
            save_job(job)
            return job

    @app.post('/api/jobs/{jid}/hd', status_code=202)
    async def start_hd(jid: str):
        if not enabled:
            raise HTTPException(403, 'GPU inference is disabled.')
        if len(jid) != 32 or any(c not in '0123456789abcdef' for c in jid):
            raise HTTPException(404, 'Invalid job ID.')
        source = store.get(jid)
        if source.get('kind') == 'hd' or source['status'] != 'completed':
            raise HTTPException(409, 'A completed original video is required.')
        source_path = store.directory / (jid + '.mp4')
        if not source_path.is_file() or source_path.is_symlink():
            raise HTTPException(404, 'Original MP4 is missing.')
        async with lock:
            if store.active():
                raise HTTPException(409, 'A GPU job is already active.')
            # One completed HD export per source; retry is allowed only after a failure.
            existing = store.db.execute('SELECT body FROM jobs').fetchall()
            for row in existing:
                old = json.loads(row[0])
                if old.get('kind') == 'hd' and old.get('source_job_id') == jid and old.get('status') == 'completed':
                    return old
            source_video = await asyncio.to_thread(inspect_source, source_path)
            job = dict(id=uuid.uuid4().hex, kind='hd', source_job_id=jid, source_video=source_video,
                       status='submitting', progress=0, message='Submitting HD upscale',
                       created=time.time(), frames=source_video['frames'],
                       settings={'width': source_video['target_width'], 'height': source_video['target_height'], 'fps': source_video['fps'],
                                 'model': 'RealESRGAN_x4plus'})
            bench.mark(job, 'submitted', 'HD export accepted by v2')
            try:
                store.save(job)
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'A GPU job is already active.')
            gpu.start(job['id'])
            try:
                pid, graph = await comfy.submit_hd(job, source_path)
                bench.mark(job, 'accepted', 'HD POST /prompt response received')
                job.update(prompt_id=pid, status='queued', message='HD upscale queued in ComfyUI')
                (store.directory / (job['id'] + '-workflow.json')).write_text(json.dumps(graph, indent=2))
            except ValueError as exc:
                job.update(status='failed', message=str(exc))
            except (httpx.HTTPError, OSError):
                job.update(message='HD submission interrupted. Reconciling before another job.')
            save_job(job)
            return job

    @app.get('/api/jobs/{jid}')
    async def status(jid: str):
        job = store.get(jid)
        job['gpu'] = gpu.summary(jid)
        return job

    @app.get('/api/jobs/{jid}/hd')
    async def hd_status(jid: str):
        if len(jid) != 32 or any(c not in '0123456789abcdef' for c in jid):
            raise HTTPException(404)
        rows = store.db.execute('SELECT body FROM jobs').fetchall()
        exports = [json.loads(r[0]) for r in rows]
        exports = [j for j in exports if j.get('kind') == 'hd' and j.get('source_job_id') == jid]
        return max(exports, key=lambda j: j.get('created', 0)) if exports else {'status': 'none'}

    @app.get('/api/jobs/{jid}/video')
    async def video(jid: str, download: bool = False):
        job = store.get(jid)
        if job['status'] != 'completed':
            raise HTTPException(409, 'Video is not ready.')
        if len(jid) != 32 or any(c not in '0123456789abcdef' for c in jid):
            raise HTTPException(404)
        path = store.directory / (jid + '.mp4')
        if not path.is_file() or path.is_symlink():
            raise HTTPException(404, 'Video file is missing.')
        return FileResponse(path, media_type='video/mp4', filename=f'opencinema-{jid[:8]}.mp4', content_disposition_type='attachment' if download else 'inline')

    app.mount('/', StaticFiles(directory=ROOT / 'app/static', html=True), name='studio')
    return app


app = create_app()
