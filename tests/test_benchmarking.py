import asyncio
import hashlib
import json
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app.main import ROOT, create_app
from app.benchmark import Benchmark, capture_process, probe_video
from app.gpu_monitor import GPUMonitor, sample_device, number
from test_app import FakeComfy, submit


class Clock:
    wall = 1000.0
    mono = 0.0
    def set(self, elapsed, wall=None):
        self.mono = elapsed
        self.wall = 1000 + elapsed if wall is None else wall
    def benchmark(self):
        return Benchmark(lambda:self.wall,lambda:self.mono)


def test_phase3_workflow_hashes_and_exact_delta():
    manifest = json.loads((ROOT/'config/phase3-verification.json').read_text())['preserved']
    for name in ('workflows/ltx13b-v2-api.json','workflows/ltx13b-v2-49f-experimental-api.json','app/director.py'):
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == manifest[name]['after_sha256']
    original = json.loads((ROOT/'workflows/ltx13b-v2-49f-experimental-api.json').read_text(encoding='utf-8'))
    extended = json.loads((ROOT/'workflows/ltx13b-v2-73f-experimental-api.json').read_text(encoding='utf-8'))
    assert extended['1338']['inputs']['num_frames'] == 73 == 8*9+1
    extended['1338']['inputs']['num_frames'] = 49
    assert extended == original


def test_timing_separates_queue_execution_retrieval_and_wall_clock_jumps():
    clock=Clock();bench=clock.benchmark();job={'id':'a'*32,'status':'running'}
    bench.mark(job,'submitted');clock.set(2);bench.mark(job,'prompt_sent')
    clock.set(7);bench.mark(job,'inference_started')
    clock.set(67,wall=200);bench.mark(job,'inference_completed')
    bench.mark(job,'retrieval_started');clock.set(70,wall=100);bench.mark(job,'retrieval_completed')
    job['status']='completed';bench.finish(job)
    metrics=job['benchmark']['metrics']
    assert metrics['queue_wait']['seconds']==5 and metrics['queue_wait']['quality']=='approximate'
    assert metrics['inference']['seconds']==60 and metrics['inference']['quality']=='approximate'
    assert metrics['retrieval']['seconds']==3 and metrics['total']['seconds']==70
    clock.set(100);bench.finish(job)
    assert job['benchmark']['metrics']['total']['seconds']==70


def test_restart_and_missing_events_do_not_invent_times():
    clock=Clock();old=clock.benchmark();job={'id':'a'*32,'status':'running'}
    old.mark(job,'submitted');old.mark(job,'prompt_sent');clock.set(1);old.mark(job,'inference_started')
    restored=json.loads(json.dumps(job));new=clock.benchmark();clock.set(40)
    new.mark(restored,'inference_completed');new.mark(restored,'retrieval_started');clock.set(42);new.mark(restored,'retrieval_completed')
    metrics=restored['benchmark']['metrics']
    assert metrics['total']['seconds'] is None and metrics['inference']['seconds'] is None
    assert metrics['retrieval']['seconds']==2
    legacy={'status':'failed'};new.finish(legacy)
    assert all(value['seconds'] is None for value in legacy['benchmark']['metrics'].values())


def test_server_timestamp_pair_is_explicitly_approximate():
    bench=Benchmark();job={'prompt_id':'pid'}
    record={'status':{'messages':[['execution_start',{'prompt_id':'pid','timestamp':100000}],['execution_success',{'prompt_id':'pid','timestamp':160000}]]}}
    bench.history(job,record)
    value=job['benchmark']['metrics']['inference']
    assert value['seconds']==60 and value['quality']=='approximate' and 'server wall' in value['source']
    assert job['benchmark']['metrics']['queue_wait']['seconds'] is None
    other={'prompt_id':'pid'}
    bench.history(other,{'status':{'messages':[['execution_start',{'timestamp':'bad'}],['execution_success',{'timestamp':float('nan')}],['execution_start',{'prompt_id':'other','timestamp':1000}],['bad'],None]}})
    assert other['benchmark']['metrics']['inference']['seconds'] is None


def test_job_lifecycle_persists_timing_and_observed_output(tmp_path):
    clock=Clock();bench=clock.benchmark();fake=FakeComfy()
    async def output(path):
        return {'frames':73,'duration_seconds':73/24,'verification':'container_metadata'}
    app=create_app(tmp_path,fake,benchmark=bench,output_probe=output)
    with TestClient(app) as client:
        job=submit(client,frames=73).json()
        assert 'submitted' in job['benchmark']['marks']
        clock.set(10)
        client.portal.call(app.state.handle_event,job,{'type':'execution_start','data':{'prompt_id':'pid'}})
        clock.set(70)
        fake.history={'pid':{'status':{'completed':True},'outputs':{'1336':{'gifs':[{'filename':job['id']+'_1.mp4','subfolder':'opencinema','type':'output'}]}}}}
        client.portal.call(app.state.reconcile,job)
        stored=app.state.store.get(job['id'])
        assert stored['benchmark']['output']['frames']==73
        assert stored['benchmark']['output']['file_size_bytes']==62
        assert stored['benchmark']['metrics']['inference']['seconds']==60
        assert stored['benchmark']['metrics']['total']['seconds']==70
        assert stored['benchmark']['metrics']['queue_wait']['seconds'] is None  # Fake adapter supplies no prompt-send mark.
        assert stored['benchmark']['status']=='completed'
        rows=client.get('/api/benchmarks?frames=73').json()['items']
        assert rows[0]['benchmark']['output']['frames']==73
        assert rows[0]['gpu']['status']=='disabled'
    assert (tmp_path/(job['id']+'-gpu.json')).is_file()


def test_failure_and_history_filter_pagination_legacy(tmp_path):
    fake=FakeComfy();fake.error=ValueError('Rejected workflow')
    app=create_app(tmp_path,fake)
    with TestClient(app) as client:
        failed=submit(client,frames=73).json()
        assert failed['benchmark']['error']=='Rejected workflow'
        assert failed['benchmark']['metrics']['inference']['seconds'] is None
        app.state.store.save({'id':'b'*32,'status':'completed','created':1,'frames':49,'settings':{'frames':49},'seed':1})
        app.state.store.save({'id':'c'*32,'status':'running','created':2,'frames':25})
        rows=client.get('/api/benchmarks').json()
        assert len(rows['items'])==2 and rows['items'][0]['id']==failed['id']
        assert 'manually reported' in rows['manual_baselines_note']
        legacy=client.get('/api/benchmarks?frames=49').json()['items'][0]
        assert legacy['benchmark'] is None and legacy['gpu']['peak_observed_memory_mib'] is None
        assert client.get('/api/benchmarks?limit=1&offset=1').json()['items'][0]['id']=='b'*32
        assert client.get('/api/benchmarks?frames=25').json()['items']==[]
        for query in ('frames=72','limit=201','limit=0','offset=-1'):
            assert client.get('/api/benchmarks?'+query).status_code==422
        assert client.get('/api/benchmarks',headers={'Host':'evil.example'}).status_code==400


@pytest.mark.parametrize('failure', [OSError('missing driver'),TimeoutError('slow helper'),ValueError('malformed')])
def test_gpu_failure_does_not_block_generation(tmp_path,failure):
    async def fail(index): raise failure
    gpu=GPUMonitor(tmp_path,enabled=True,sampler=fail)
    fake=FakeComfy();fake.error=ValueError('Rejected workflow')
    app=create_app(tmp_path,fake,gpu_monitor=gpu)
    with TestClient(app) as client:
        response=submit(client)
        assert response.status_code==202 and response.json()['status']=='failed'
    # Explicitly test sampling independently, since a fast failed job may stop before its first sample.
    async def check():
        monitor=GPUMonitor(tmp_path,enabled=True,sampler=fail)
        monitor.start('d'*32);await monitor.tasks['d'*32]
        state=monitor.summary('d'*32)
        assert state['status']=='unavailable' and state['errors'] and state['peak_observed_memory_mib'] is None
    asyncio.run(check())


def test_gpu_samples_are_device_level_bounded_and_separate(tmp_path):
    async def sample(index): return {'memory_used_mib':8000,'utilization_percent':88,'provider':'fake'}
    async def run():
        monitor=GPUMonitor(tmp_path,enabled=True,sampler=sample)
        for jid in ('a'*32,'b'*32):
            monitor.start(jid)
            async def wait_sample():
                while monitor.jobs[jid]['sample_count']==0: await asyncio.sleep(0)
            await asyncio.wait_for(wait_sample(),1)
            monitor.stop(jid);await monitor.tasks[jid]
            state=monitor.summary(jid)
            assert state['peak_observed_memory_mib']==8000 and state['status']=='available'
            assert 'not v2-exclusive' in state['scope'] and state['sampling_interval_seconds']==2
            saved=json.loads((tmp_path/(jid+'-gpu.json')).read_text())
            assert saved['samples'][0]['utilization_percent']==88
        assert monitor.path('a'*32)!=monitor.path('b'*32)
        with pytest.raises(ValueError):monitor.path('../escape')
    asyncio.run(run())


def test_gpu_disabled_never_calls_provider(tmp_path):
    async def forbidden(index):pytest.fail('Disabled monitor queried GPU')
    async def run():
        monitor=GPUMonitor(tmp_path,enabled=False,sampler=forbidden)
        monitor.start('a'*32);await monitor.close()
        assert monitor.summary('a'*32)['status']=='disabled'
    asyncio.run(run())


def test_readonly_smi_command_and_unsupported_values(monkeypatch):
    import app.gpu_monitor as module
    seen=[]
    monkeypatch.setattr(module.importlib.util,'find_spec',lambda name:None)
    monkeypatch.setattr(module.shutil,'which',lambda name:'nvidia-smi')
    async def capture(*args,**kwargs):seen.append(args);return '8192, 90'
    monkeypatch.setattr(module,'capture_process',capture)
    result=asyncio.run(sample_device(0))
    assert result['memory_used_mib']==8192 and result['utilization_percent']==90
    assert seen==[('nvidia-smi','--id=0','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits')]
    for value in ('N/A','[Not Supported]',float('nan'),-1):assert number(value) is None
    assert number(101,100) is None


def test_installed_nvml_is_preferred(monkeypatch):
    import sys
    import app.gpu_monitor as module
    calls=[]
    nvml=SimpleNamespace(nvmlInit=lambda:calls.append('init'),nvmlShutdown=lambda:calls.append('shutdown'),
        nvmlDeviceGetHandleByIndex=lambda i:i,nvmlDeviceGetMemoryInfo=lambda handle:SimpleNamespace(used=1024*1024*5),
        nvmlDeviceGetUtilizationRates=lambda handle:SimpleNamespace(gpu=40),NVMLError=OSError)
    monkeypatch.setitem(sys.modules,'pynvml',nvml)
    monkeypatch.setattr(module.importlib.util,'find_spec',lambda name:object())
    result=asyncio.run(sample_device())
    assert result['provider']=='nvml' and result['memory_used_mib']==5 and calls==['init','shutdown']


def test_owned_helper_timeout_cleanup(monkeypatch):
    import app.benchmark as module
    class Process:
        returncode=None
        killed=False
        async def communicate(self):raise TimeoutError()
        def kill(self):self.killed=True;self.returncode=-9
        async def wait(self):return self.returncode
    process=Process()
    async def create(*args,**kwargs):return process
    monkeypatch.setattr(module.asyncio,'create_subprocess_exec',create)
    with pytest.raises(TimeoutError):asyncio.run(capture_process('fake-read-only-helper'))
    assert process.killed


@pytest.mark.parametrize('payload,expected', [('bad',None),('{"streams":[]}',None),('{"streams":[{"nb_frames":"73","duration":"3.041667"}]}',73),('{"streams":[{"nb_frames":"N/A","duration":"N/A"}]}',None)])
def test_probe_output_is_observed_not_requested(monkeypatch,payload,expected,tmp_path):
    import app.benchmark as module
    monkeypatch.setattr(module.shutil,'which',lambda name:'ffprobe')
    async def capture(*args,**kwargs):return payload
    monkeypatch.setattr(module,'capture_process',capture)
    result=asyncio.run(probe_video(tmp_path/'fake.mp4'))
    assert result['frames']==expected


def test_failed_execution_duration_and_unrelated_events():
    bench=Benchmark();job={'prompt_id':'pid'}
    bench.history(job,{'status':{'messages':[['execution_start',{'timestamp':100000}],['execution_error',{'timestamp':130000}]]}})
    value=job['benchmark']['metrics']['inference']
    assert value['seconds']==30 and 'execution_error' in value['source']


def test_gpu_storage_failure_is_nonfatal(tmp_path,monkeypatch):
    from pathlib import Path
    original=Path.write_text
    def deny(path,*args,**kwargs):
        if '-gpu' in path.name:raise OSError('disk unavailable')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'write_text',deny)
    async def run():
        monitor=GPUMonitor(tmp_path,enabled=False)
        monitor.start('a'*32);await monitor.close()
        assert 'storage_error' in monitor.summary('a'*32)
    asyncio.run(run())
