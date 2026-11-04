import asyncio
import base64
import io
import json
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
import app.main as main
from app.director import direct, SCENES, CAMERAS
from app.settings import ROOT, HOST, PORT, data_path
from test_app import FakeComfy, png, submit


def test_graph_integrity_and_preserved_settings():
    original = json.loads((ROOT / 'workflows/ltx13b-api.json').read_text())
    graph = json.loads((ROOT / 'workflows/ltx13b-v2-api.json').read_text())
    assert set(original) - set(graph) == {'1598','1813','1888','1889'}
    visited = set()
    def walk(key, ancestors):
        assert key not in ancestors
        visited.add(key)
        for value in graph[key]['inputs'].values():
            if isinstance(value, list):
                assert len(value) == 2 and value[0] in graph and isinstance(value[1], int) and value[1] >= 0
                walk(value[0], ancestors | {key})
    walk('1336', set())
    assert visited == set(graph)
    assert all(graph[key] == original[key] for key in graph)


@pytest.mark.parametrize('scene', SCENES)
@pytest.mark.parametrize('camera', CAMERAS)
def test_director_maps_to_graph(scene, camera):
    direction = direct('A red bicycle', scene, camera, 'warm')
    graph = main.workflow('input.png', 'A red bicycle', 42, camera, 'abc', scene, 'warm', 0.85)
    assert graph['6']['inputs']['text'] == direction['prompt']
    assert graph['1338']['inputs']['strength'] == 0.85
    assert graph['1507']['inputs']['noise_seed'] == 42
    assert all(direction[key] for key in ('subject','camera','lighting','environment','motion_constraints'))


def test_isolation_and_offline_default(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENCINEMA_DATA', r'D:\comguopensource\artifacts\studio')
    monkeypatch.setattr(main, 'INFERENCE_ENABLED', False)
    assert data_path().is_relative_to(ROOT)
    assert (HOST, PORT) == ('127.0.0.1', 8001)
    with pytest.raises(ValueError):
        main.Store(ROOT.parent / 'comguopensource' / 'artifacts' / 'studio')
    with TestClient(main.create_app(tmp_path)) as client:
        assert client.get('/api/health').json()['inference_enabled'] is False
        assert submit(client).status_code == 403
        assert client.post('/api/director', data={'prompt':'A bicycle'}).status_code == 200
        assert client.get('/api/presets').json()['scenes'] == SCENES


def test_public_auth_and_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'PUBLIC_HOST', 'jury.example')
    monkeypatch.setattr(main, 'DEMO_USER', 'test')
    monkeypatch.setattr(main, 'DEMO_PASSWORD', 'synthetic-test-only-password')
    app = main.create_app(tmp_path, FakeComfy())
    auth = 'Basic ' + base64.b64encode(b'test:synthetic-test-only-password').decode()
    with TestClient(app, base_url='https://jury.example') as client:
        assert client.get('/').status_code == 401
        assert client.get('/api/benchmarks').status_code == 401
        assert client.get('/api/jobs/x/video').status_code == 401
        assert client.get('/',headers={'Authorization':'Basic !!!'}).status_code == 401
        client.headers['Authorization'] = auth
        assert client.get('/').status_code == 200
        assert submit(client).status_code == 403
        client.headers['Origin'] = 'https://jury.example'
        for i in range(30):
            app.state.store.save({'id':str(i),'status':'failed','created':main.time.time()})
        assert submit(client).status_code == 429
        assert client.get('/',headers={'Host':'evil.example'}).status_code == 400


@pytest.mark.parametrize('response', [httpx.Response(503), httpx.Response(200,json={}), httpx.Response(200,content=b'bad json')])
def test_ambiguous_adapter_response(response):
    def handle(request):
        if request.url.path == '/queue': return httpx.Response(200,json={})
        if request.url.path == '/upload/image': return httpx.Response(200,json={'name':'safe.png'})
        return response
    async def run():
        comfy = main.Comfy('http://fake')
        await comfy.http.aclose()
        comfy.http = httpx.AsyncClient(base_url='http://fake',transport=httpx.MockTransport(handle))
        try:
            with pytest.raises(httpx.HTTPError):
                await comfy.submit(dict(id='a'*32,prompt='scene',seed=1,preset='static'),png())
        finally: await comfy.http.aclose()
    asyncio.run(run())


def test_pixel_limit(monkeypatch):
    monkeypatch.setattr(Image, 'MAX_IMAGE_PIXELS', 100)
    with pytest.raises(main.HTTPException) as exc:
        main.normalize_image(png(), 'image/png')
    assert exc.value.status_code == 422


def test_metadata_download_and_invalid_mp4(tmp_path):
    fake = FakeComfy()
    app = main.create_app(tmp_path, fake)
    with TestClient(app) as client:
        job = submit(client,scene='portrait',mood='dramatic',strength='0.85').json()
        assert job['settings']['strength'] == 0.85
        assert 'facial' in job['enhanced_prompt']
        fake.history = {'pid':{'status':{'completed':True},'outputs':{'1336':{'gifs':[{'filename':job['id']+'_1.mp4','subfolder':'opencinema','type':'output'}]}}}}
        client.portal.call(app.state.reconcile,job)
        assert 'attachment' in client.get('/api/jobs/'+job['id']+'/video?download=true').headers['content-disposition']
        client.portal.call(fake.http.aclose)
        fake.http = httpx.AsyncClient(base_url='http://test',transport=httpx.MockTransport(lambda request:httpx.Response(200,content=b'not an mp4 file')))
        with pytest.raises(ValueError,match='invalid MP4'):
            client.portal.call(app.state.reconcile,job)
