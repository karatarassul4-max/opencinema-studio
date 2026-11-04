import asyncio
import hashlib
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import ROOT, Comfy, create_app, workflow
from app.director import direct, SCENES, CAMERAS, MOODS
from app.durations import DURATIONS, duration_settings
from test_app import FakeComfy, png, submit


def test_rollback_baseline_unchanged():
    evidence = json.loads((ROOT / 'config/phase3-verification.json').read_text())
    name = 'workflows/ltx13b-v2-api.json'
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == evidence['preserved'][name]['after_sha256']



@pytest.mark.parametrize('frames', [25, 49, 73, 97])
def test_workflow_modes_and_installed_constraints(frames):
    mode = duration_settings(frames)
    graph = json.loads((ROOT / 'workflows' / mode['workflow']).read_text(encoding='utf-8'))
    baseline = json.loads((ROOT / 'workflows/ltx13b-v2-api.json').read_text(encoding='utf-8'))
    assert graph['1338']['inputs']['num_frames'] == frames
    graph['1338']['inputs']['num_frames'] = 25
    # Editor titles may differ; executable nodes may only change frame count.
    strip_titles = lambda g: {k:{'class_type':v['class_type'],'inputs':v['inputs']} for k,v in g.items()}
    assert strip_titles(graph) == strip_titles(baseline)
    evidence = json.loads((ROOT / 'config/ltx-frame-constraints-evidence.json').read_text())
    spec = evidence['live_required_inputs']['num_frames'][1]
    assert spec['min'] <= frames <= spec['max'] and (frames - 1) % spec['step'] == 0
    assert (frames - 1) // 8 + 1 == ({25:4,49:7,73:10,97:13}[frames])
    for field in ('width', 'height'):
        spec = evidence['live_required_inputs'][field][1]
        value = graph['1338']['inputs'][field]
        assert spec['min'] <= value <= spec['max'] and value % spec['step'] == 0
    visited = set()
    def visit(key, ancestors):
        assert key not in ancestors
        visited.add(key)
        for value in graph[key]['inputs'].values():
            if isinstance(value,list):
                assert len(value) == 2 and value[0] in graph and isinstance(value[1],int) and value[1] >= 0
                visit(value[0], ancestors | {key})
    visit('1336', set())
    assert visited == set(graph)
    assert graph['1336']['inputs']['frame_rate'] == 24
    assert graph['1241']['inputs']['frame_rate'] == pytest.approx(24)


@pytest.mark.parametrize('frames', [25, 49, 73, 97])
def test_api_to_real_adapter_propagation(tmp_path, frames):
    sent = []
    def handle(request):
        if request.url.path == '/queue': return httpx.Response(200,json={})
        if request.url.path == '/upload/image': return httpx.Response(200,json={'name':'safe.png'})
        if request.url.path == '/prompt':
            sent.append(json.loads(request.content))
            return httpx.Response(200,json={'prompt_id':'fake-pid'})
        return httpx.Response(200,json={})
    comfy = Comfy('http://offline-test')
    asyncio.run(comfy.http.aclose())
    comfy.http = httpx.AsyncClient(base_url=comfy.url,transport=httpx.MockTransport(handle))
    app = create_app(tmp_path, comfy)
    with TestClient(app) as client:
        data = dict(prompt='Fast dolly backward as the athlete sprints under neon light.',scene='action',mood='dramatic',preset='static',frames=frames,strength='0.80',seed=421)
        preview = client.post('/api/director',data=data).json()
        response = submit(client,**data)
        assert response.status_code == 202
        job = response.json()
        graph = sent[0]['prompt']
        assert graph['1338']['inputs']['num_frames'] == frames
        assert graph['1338']['inputs']['strength'] == 0.8
        assert graph['1338']['inputs']['width'] == 512 and graph['1338']['inputs']['height'] == 320
        assert graph['1507']['inputs']['noise_seed'] == 421
        assert graph['1206']['inputs']['image'] == 'safe.png'
        assert graph['6']['inputs']['text'] == preview['prompt'] == job['enhanced_prompt']
        assert 'locked-off' not in job['enhanced_prompt']
        assert job['camera_source'] == 'description'
        assert job['settings']['frames'] == job['frames'] == frames
        assert job['settings']['duration_seconds'] == frames / 24
        assert job['settings']['experimental'] is (frames != 25)
        assert job['settings']['workflow'] == DURATIONS[frames]['workflow']
        persisted = app.state.store.get(job['id'])
        assert persisted['settings'] == job['settings']
        saved = json.loads((tmp_path / (job['id']+'-workflow.json')).read_text())
        assert saved == graph


@pytest.mark.parametrize('frames', [0, 24, 48, 50, 57, -1, 'forty-nine'])
def test_invalid_duration_never_submits(tmp_path, frames):
    class NoSubmit(FakeComfy):
        async def submit(self, *args):
            pytest.fail('Invalid duration reached submission')
    app = create_app(tmp_path, NoSubmit())
    with TestClient(app) as client:
        assert submit(client,frames=frames).status_code == 422
        assert app.state.store.active() is None
        assert not list(tmp_path.glob('*.png'))


def test_legacy_default_is_25_frames(tmp_path):
    with TestClient(create_app(tmp_path, FakeComfy())) as client:
        job = submit(client).json()
        assert job['frames'] == 25 and job['settings']['frames'] == 25
        assert client.get('/api/presets').json()['durations'] == [duration_settings(25),duration_settings(49),duration_settings(73),duration_settings(97)]


@pytest.mark.parametrize('frames', [24, 48, 57, True, 49.0])
def test_builder_rejects_unsupported_duration(frames):
    with pytest.raises(ValueError):
        workflow('x.png','scene',1,'static','id',frames=frames)


@pytest.mark.parametrize('description', [
    'A dolly forward toward the car.', 'A fast dolly backward.',
    'The camera pulls back quickly.', 'An orbit counterclockwise around the dancer.',
    'Do not orbit; dolly out instead.', 'No camera motion.',
    'A locked-off shot of an athlete sprinting.', 'A rapid pan left.',
    'Tilt down to reveal the table.', 'Handheld tracking follows the runner.',
    'A crane descends.', 'Zoom out rapidly.', 'A drone flies over the mountains.',
])
@pytest.mark.parametrize('selected', ['static','dolly','orbit','crane'])
def test_explicit_camera_never_gets_a_second_movement(description, selected):
    result = direct(description,'action',selected,'dramatic')
    assert result['camera_source'] == 'description'
    assert result['subject'] == description
    assert result['camera'] == 'Follow the camera directions and restrictions in the scene description.'
    assert CAMERAS[selected] not in result['prompt']


@pytest.mark.parametrize('scene', SCENES)
@pytest.mark.parametrize('camera', CAMERAS)
@pytest.mark.parametrize('mood', MOODS)
def test_scene_mood_preservation_do_not_restrict_motion(scene,camera,mood):
    result = direct('The athlete sprints, leaps and spins rapidly under harsh neon lighting.',scene,camera,mood)
    assert result['camera_source'] == 'preset'
    assert result['camera'] == CAMERAS[camera]
    appended = ' '.join(result[key] for key in ('lighting','environment','motion_constraints','mood')).lower()
    for forbidden in ('subtle motion only','one small','small expressions','avoid abrupt','soft studio','locked-off','fixed composition'):
        assert forbidden not in appended
    assert result['lighting'] == 'Use the lighting described in the scene.'
    assert '\n' not in result['prompt']
    if camera != 'static': assert 'locked-off' not in result['prompt']


def test_legacy_prompt_also_respects_explicit_camera():
    graph = workflow('input.png','Dolly backward quickly',7,'static','id',frames=49)
    assert 'locked-off' not in graph['6']['inputs']['text']
    assert 'Dolly backward quickly' in graph['6']['inputs']['text']
