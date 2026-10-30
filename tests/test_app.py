import io
import json
import asyncio
import httpx
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app, workflow, normalize_image, safe_output, Store, Comfy
from fastapi import HTTPException


def png():
    b = io.BytesIO()
    Image.new('RGB', (32, 24), 'orange').save(b, 'PNG')
    return b.getvalue()


class FakeComfy:
    url = 'http://127.0.0.1:1'

    def __init__(self):
        self.history = {}
        self.queue = {'queue_running': [], 'queue_pending': []}
        self.error = None
        self.http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b'\x00\x00\x00\x18ftypisom' + b'x'*50)), base_url='http://test')

    async def get(self, path):
        if self.error:
            raise self.error
        if path == '/system_stats':
            return {'devices': [{'name': 'test GPU'}]}
        return self.queue if path == '/queue' else self.history

    async def submit(self, job, image):
        if self.error:
            raise self.error
        self.queue['queue_running'] = [[0, 'pid', {}, {'opencinema_id': job['id']}]]
        return 'pid', workflow(job['id']+'.png', job['prompt'], job['seed'], job['preset'], job['id'])


@pytest.fixture
def setup(tmp_path):
    fake = FakeComfy()
    app = create_app(tmp_path, fake)
    with TestClient(app) as c:
        yield c, app, fake


def submit(c, **data):
    return c.post('/api/jobs', files={'image': ('x.png', png(), 'image/png')}, data={'prompt': 'A fox in snow', **data})


def test_workflow():
    original = workflow('a.png', 'Hello', 1, 'dolly', 'a')
    other = workflow('b.png', 'World', 2, 'orbit', 'b')
    assert original['78']['inputs']['image'] == 'a.png'
    assert other['72']['inputs']['noise_seed'] == 2
    assert 'orbit' in other['6']['inputs']['text']
    assert original['77']['inputs']['length'] == 25
    assert original['77']['inputs']['width'] == 512
    assert original['80']['inputs']['fps'] == 24
    assert original['81']['inputs']['format.codec'] == 'h264'


@pytest.mark.parametrize('raw,mime,code', [(b'bad', 'image/png', 422), (b'x', 'text/html', 415), (b'x'*(10*1024*1024+1), 'image/png', 413)], ids=['corrupt','mime','oversize'])
def test_upload_rejection(raw, mime, code):
    with pytest.raises(HTTPException) as e:
        normalize_image(raw, mime)
    assert e.value.status_code == code


def test_upload_normalization():
    assert Image.open(io.BytesIO(normalize_image(png(), 'image/png'))).format == 'PNG'


def test_lifecycle_and_single_job(setup):
    c, app, fake = setup
    r = submit(c)
    assert r.status_code == 202
    job = r.json()
    assert submit(c).status_code == 409
    assert c.get('/api/jobs/'+job['id']+'/video').status_code == 409
    fake.history = {'pid': {'status': {'completed': True, 'status_str': 'success'}, 'outputs': {'81': {'images': [{'filename': job['id']+'_00001_.mp4', 'subfolder': 'opencinema', 'type': 'output'}]}}}}
    # Explicit history reconciliation succeeds without a functioning WebSocket.
    c.portal.call(app.state.reconcile, job)
    assert c.get('/api/jobs/'+job['id']).json()['status'] == 'completed'
    video = c.get('/api/jobs/'+job['id']+'/video')
    assert video.status_code == 200 and video.content[4:8] == b'ftyp'
    assert c.get('/api/jobs/'+job['id']+'/video', headers={'Range': 'bytes=0-11'}).status_code == 206
    assert submit(c).status_code == 202


def test_validation_and_errors(setup):
    c, app, fake = setup
    assert submit(c, preset='unsafe').status_code == 422
    assert submit(c, seed=-1).status_code == 422
    assert submit(c, prompt=' ').status_code == 422
    fake.error = ValueError('Missing models')
    assert submit(c).json()['status'] == 'failed'
    fake.error = httpx.ConnectError('offline')
    assert c.get('/api/health').json()['connected'] is False
    assert submit(c).json()['status'] == 'submitting'
    assert submit(c).status_code == 409


@pytest.mark.parametrize('field,value', [('filename', '../x.mp4'), ('filename', 'a_foo\\x.mp4'), ('subfolder', '../'), ('type', 'input'), ('filename', 'other.mp4')])
def test_safe_outputs(field, value):
    item = {'filename': 'a_00001_.mp4', 'subfolder': 'opencinema', 'type': 'output'}
    item[field] = value
    with pytest.raises(ValueError):
        safe_output(item, 'a')


def test_restart_recovery(tmp_path):
    store = Store(tmp_path)
    job = {'id': 'a'*32, 'status': 'submitting', 'created': 0}
    store.save(job)
    store.db.close()
    fake = FakeComfy()
    fake.queue['queue_running'] = [[0, 'recovered', {}, {'opencinema_id': job['id']}]]
    app = create_app(tmp_path, fake)
    with TestClient(app) as c:
        c.portal.call(app.state.reconcile, app.state.store.get(job['id']))
        recovered = c.get('/api/jobs/'+job['id']).json()
        assert recovered['prompt_id'] == 'recovered'
        assert recovered['status'] == 'running'


def test_generation_failure(setup):
    c, app, fake = setup
    job = submit(c).json()
    fake.history = {'pid': {'status': {'status_str': 'error'}}}
    c.portal.call(app.state.reconcile, job)
    assert c.get('/api/jobs/'+job['id']).json()['status'] == 'failed'
    assert c.get('/api/jobs/unknown/video').status_code == 404


def test_database_concurrency_guard(tmp_path):
    import sqlite3
    a, b = Store(tmp_path), Store(tmp_path)
    a.save({'id': 'first', 'status': 'running'})
    with pytest.raises(sqlite3.IntegrityError):
        b.save({'id': 'second', 'status': 'queued'})
    b.db.rollback()
    assert a.active()['id'] == 'first'
    a.db.close()
    b.db.close()


def test_request_body_and_origin_guard(setup):
    c, app, fake = setup
    assert c.post('/api/jobs', content=b'x'*(10*1024*1024+65537)).status_code == 413
    assert c.post('/api/jobs', headers={'Origin': 'https://evil.example'}).status_code == 403
    assert c.get('/api/health', headers={'Host': 'evil.example'}).status_code == 400


def test_missing_output_and_lost_job(setup):
    c, app, fake = setup
    job = submit(c).json()
    fake.history = {'pid': {'status': {'completed': True}, 'outputs': {}}}
    with pytest.raises(ValueError, match='MP4'):
        c.portal.call(app.state.reconcile, job)
    fake.history, fake.queue = {}, {}
    c.portal.call(app.state.reconcile, job)
    assert c.get('/api/jobs/'+job['id']).json()['status'] == 'failed'


@pytest.mark.parametrize('mode', ['busy', 'missing_model', 'success'])
def test_real_comfy_adapter_contract(mode):
    seen = []
    def handle(request):
        seen.append(request.url.path)
        if request.url.path == '/queue':
            return httpx.Response(200, json={'queue_running': [[0, 'other']] if mode == 'busy' else [], 'queue_pending': []})
        if request.url.path == '/upload/image':
            return httpx.Response(200, json={'name': 'safe.png', 'subfolder': ''})
        if request.url.path == '/prompt':
            body = json.loads(request.content)
            assert body['prompt']['78']['inputs']['image'] == 'safe.png'
            assert body['extra_data']['opencinema_id'] == 'a'*32
            if mode == 'missing_model':
                return httpx.Response(400, json={'node_errors': {'44': 'missing checkpoint'}})
            return httpx.Response(200, json={'prompt_id': 'real-adapter-id'})
        raise AssertionError(request.url)
    async def run():
        client = Comfy('http://comfy')
        await client.http.aclose()
        client.http = httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url=client.url)
        try:
            job = dict(id='a'*32, prompt='Scene', preset='static', seed=1)
            if mode == 'success':
                pid, graph = await client.submit(job, png())
                assert pid == 'real-adapter-id'
            else:
                with pytest.raises(ValueError):
                    await client.submit(job, png())
                if mode == 'busy':
                    assert seen == ['/queue']
        finally:
            await client.http.aclose()
    asyncio.run(run())
