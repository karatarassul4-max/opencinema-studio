"""Submit a real ComfyUI graph and record hardware samples and websocket events."""
import datetime, json, pathlib, subprocess, threading, time, uuid
import psutil, requests, websocket

ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8188'
run=ROOT/'artifacts'/('run-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
run.mkdir(parents=True)
stop=threading.Event(); samples=[]
def monitor():
    with (run/'metrics.jsonl').open('w') as log:
        while not stop.is_set():
            sample={'elapsed_s':time.monotonic()-start,'system_ram_used_bytes':psutil.virtual_memory().used,'system_ram_available_bytes':psutil.virtual_memory().available}
            try:
                raw=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True,creationflags=0x08000000)
                mem,util=raw.strip().split(','); sample.update(gpu_used_mib=int(mem),gpu_util_percent=int(util))
                processes=[]
                for p in psutil.process_iter(['name','cmdline','memory_info','pid']):
                    if 'python' in (p.info['name'] or '').lower() and 'main.py' in (p.info['cmdline'] or []):
                        processes.append({'pid':p.pid,'rss_bytes':p.info['memory_info'].rss})
                sample['comfy_processes']=processes
            except (OSError,psutil.Error) as e: sample['sampling_error']=str(e)
            samples.append(sample); log.write(json.dumps(sample)+'\n'); log.flush(); stop.wait(1)
client=str(uuid.uuid4()); ws=websocket.create_connection(BASE.replace('http','ws')+'/ws?clientId='+client,timeout=10)
workflow=json.loads((ROOT/'workflows/ltx-i2v-api.json').read_text())
(run/'workflow.json').write_text(json.dumps(workflow,indent=2))
(run/'system-before.json').write_text(json.dumps(requests.get(BASE+'/system_stats',timeout=10).json(),indent=2))
start=time.monotonic(); thread=threading.Thread(target=monitor); thread.start()
try:
    response=requests.post(BASE+'/prompt',json={'prompt':workflow,'client_id':client},timeout=30)
    (run/'submission.json').write_text(response.text); response.raise_for_status()
    pid=response.json()['prompt_id']; print('PROMPT',pid,'EVIDENCE',run,flush=True)
    with (run/'events.jsonl').open('w') as events:
        while True:
            try:
                message=ws.recv()
                if isinstance(message,str):
                    event=json.loads(message); events.write(json.dumps(event)+'\n'); events.flush()
                    if event['type'] in ['executing','progress','execution_error','execution_success']: print(json.dumps(event),flush=True)
            except websocket.WebSocketTimeoutException: pass
            history=requests.get(BASE+'/history/'+pid,timeout=20).json()
            if pid in history:
                (run/'history.json').write_text(json.dumps(history,indent=2)); break
    item=history[pid]
    if item['status']['status_str']!='success': raise RuntimeError('ComfyUI execution failed; see history.json')
finally:
    stop.set(); thread.join(); ws.close()
    summary={'wall_seconds':time.monotonic()-start,'samples':len(samples),'peak_device_vram_mib':max((s.get('gpu_used_mib',0) for s in samples),default=0),'peak_system_ram_used_bytes':max((s['system_ram_used_bytes'] for s in samples),default=0),'peak_comfy_rss_bytes':max((sum(p['rss_bytes'] for p in s.get('comfy_processes',[])) for s in samples),default=0),'measurement_note':'1-second polling, device-wide VRAM and host-wide RAM; RSS sums ComfyUI Python processes. Not isolated allocator peaks.'}
    (run/'summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary),flush=True)
