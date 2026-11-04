"""HD lifecycle checks use fake ComfyUI and fake ffprobe; no GPU or subprocess."""
import json
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
import app.main as main
from app.hd_export import inspect_source, hd_workflow, validate_hd_output
from test_app import FakeComfy

META = dict(width=512, height=320, frames=25, fps=24, target_width=1280, target_height=800)

class FakeHD(FakeComfy):
    def __init__(self):
        super().__init__()
        self.submissions = 0
    async def submit_hd(self, job, path):
        self.submissions += 1
        return 'hd-pid', hd_workflow(path, job['id'], job['source_video'])

def test_probe_and_workflow(tmp_path, monkeypatch):
    path = tmp_path/'source.mp4'; path.write_bytes(b'fake')
    calls = []
    def probe(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=json.dumps({'streams':[dict(width=512,height=320,nb_frames='25',avg_frame_rate='24/1')]}))
    monkeypatch.setattr('app.hd_export.subprocess.run', probe)
    assert inspect_source(path) == META
    assert calls[0][0] == 'ffprobe'
    graph = hd_workflow(path, 'a'*32, META)
    assert graph['1']['inputs']['frame_load_cap'] == 25
    assert graph['2']['inputs']['model_name'] == 'RealESRGAN_x4plus.pth'
    assert graph['4']['inputs']['width'] == 1280 and graph['4']['inputs']['height'] == 800
    assert graph['5']['inputs']['frame_rate'] == 24

@pytest.mark.parametrize('changes', [dict(width=2048),dict(height=1200),dict(nb_frames='98'),dict(avg_frame_rate='0/1'),dict(avg_frame_rate='24/0')])
def test_probe_rejects_unsupported_input(tmp_path, monkeypatch, changes):
    path = tmp_path/'source.mp4'; path.write_bytes(b'fake')
    stream = dict(width=512,height=320,nb_frames='25',avg_frame_rate='24/1'); stream.update(changes)
    monkeypatch.setattr('app.hd_export.subprocess.run', lambda *a,**k:SimpleNamespace(stdout=json.dumps({'streams':[stream]})))
    with pytest.raises(ValueError): inspect_source(path)

@pytest.mark.parametrize('changes', [dict(filename='../bad.mp4'),dict(filename='b'*32+'_0001.mp4'),dict(subfolder='elsewhere'),dict(type='temp')])
def test_hd_output_ownership(changes):
    item=dict(filename='a'*32+'_0001.mp4',subfolder='opencinema',type='output');item.update(changes)
    with pytest.raises(ValueError):validate_hd_output(item,'a'*32)

@pytest.mark.parametrize('mismatch', [False, True])
def test_hd_completion_and_duplicate_protection(tmp_path, monkeypatch, mismatch):
    fake=FakeHD()
    monkeypatch.setattr(main,'inspect_source',lambda path:META)
    async def probe(path):return dict(width=640 if mismatch else 1280,height=800,frames=25,duration_seconds=25/24,verification='mock')
    app=main.create_app(tmp_path,fake,output_probe=probe)
    source=dict(id='a'*32,status='completed',kind='generation',created=1,settings={'frames':25})
    with TestClient(app) as client:
        app.state.store.save(source)
        (tmp_path/(source['id']+'.mp4')).write_bytes(b'fake source')
        response=client.post('/api/jobs/'+source['id']+'/hd')
        assert response.status_code==202
        job=response.json();assert job['kind']=='hd'
        assert client.post('/api/jobs/'+source['id']+'/hd').status_code==409
        fake.history={'hd-pid':{'status':{'completed':True,'status_str':'success'},'outputs':{'5':{'gifs':[dict(filename=job['id']+'_0001.mp4',subfolder='opencinema',type='output')]}}}}
        if mismatch:
            with pytest.raises(ValueError,match='metadata mismatch'):client.portal.call(app.state.reconcile,job)
            assert not (tmp_path/(job['id']+'.mp4')).exists()
        else:
            client.portal.call(app.state.reconcile,job)
            assert client.get('/api/jobs/'+source['id']+'/hd').json()['status']=='completed'
            assert client.get('/api/jobs/'+job['id']+'/video?download=true').status_code==200
            assert client.post('/api/jobs/'+source['id']+'/hd').json()['id']==job['id']
            assert fake.submissions==1
