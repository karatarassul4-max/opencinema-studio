const $=id=>document.getElementById(id);
let preset='static', active=null, preview=null, polling=false, inferenceEnabled=false;
let displayedSource=null;
const showError=message=>{$('error').textContent=message;$('error').hidden=!message};
function selectFile(file){if(!file)return;if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>10*1024*1024){showError('Choose a PNG, JPEG or WebP image up to 10 MiB.');$('image').value='';return}showError('');if(preview)URL.revokeObjectURL(preview);preview=URL.createObjectURL(file);$('source').src=preview;$('source').hidden=false;$('drop-label').hidden=true;$('replace').hidden=false}
$('image').onchange=()=>selectFile($('image').files[0]);
for(const type of ['dragenter','dragover'])$('drop').addEventListener(type,e=>{e.preventDefault();$('drop').classList.add('drag')});
for(const type of ['dragleave','drop'])$('drop').addEventListener(type,e=>{e.preventDefault();$('drop').classList.remove('drag')});
$('drop').addEventListener('drop',e=>{const file=e.dataTransfer.files[0];if(file){const dt=new DataTransfer();dt.items.add(file);$('image').files=dt.files;selectFile(file)}});
document.querySelectorAll('[data-preset]').forEach(button=>{button.setAttribute('aria-pressed',button.classList.contains('selected'));button.onclick=()=>{preset=button.dataset.preset;document.querySelectorAll('[data-preset]').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-pressed',b===button)})}});
$('random').onclick=()=>{$('seed').value=crypto.getRandomValues(new Uint32Array(1))[0]};
$('prompt').oninput=()=>{$('count').textContent=`${$('prompt').value.length} / 3000`};$('prompt').oninput();
async function request(url,options){const r=await fetch(url,options);const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Invalid settings. Check your image, prompt and seed.');return data}
function renderHD(job){
  const sourceId=job.source_job_id;
  displayedSource=sourceId;
  active=['completed','failed'].includes(job.status)?null:job.id;
  $('generate').disabled=!!active||!inferenceEnabled;
  $('status-label').textContent=job.status.toUpperCase();
  $('message').textContent=job.message;
  $('progress').value=job.status==='completed'?100:0;
  $('percent').textContent=job.status==='completed'?'100%':'—';
  $('hd-export').hidden=job.status!=='failed';
  $('hd-export').disabled=!!active||!inferenceEnabled;
  $('hd-download').hidden=job.status!=='completed';
  if(job.status==='completed'){
    $('hd-download').href=`/api/jobs/${job.id}/video?download=true`;
    $('hd-download').download=`opencinema-hd-${sourceId.slice(0,8)}.mp4`;
    showError('');
  } else if(job.status==='failed') showError(job.message);
  if(!$('video').src.endsWith(`/api/jobs/${sourceId}/video`)) $('video').src=`/api/jobs/${sourceId}/video`;
  $('video').hidden=false;$('empty').hidden=true;
  $('download').href=`/api/jobs/${sourceId}/video?download=true`;
  $('download').hidden=false;
}
function render(job){
  if(job.kind==='hd'){renderHD(job);return;}
  displayedSource=job.id;
  active=['completed','failed'].includes(job.status)?null:job.id;
  $('hd-export').hidden=job.status!=='completed';
  $('hd-export').disabled=!!active||!inferenceEnabled;
  $('hd-download').hidden=true;
  if(job.status==='completed') refreshHD(job.id);$('metadata').hidden=false;$('metadata-text').textContent=JSON.stringify({settings:job.settings,scene:job.scene,mood:job.mood,seed:job.seed,direction:job.enhanced_prompt,camera_source:job.camera_source,benchmark:job.benchmark,gpu:job.gpu},null,2);active=['completed','failed'].includes(job.status)?null:job.id;$('hd-export').disabled=!!active||!inferenceEnabled;$('generate').disabled=!!active||!inferenceEnabled;$('generate').firstChild.textContent=active?'Rendering your scene… ':'Generate scene ';$('status-label').textContent=job.status.toUpperCase();$('message').textContent=job.message;$('progress').value=job.progress||0;$('percent').textContent=`${job.progress||0}%`;$('job-info').textContent=`SEED ${job.seed} · ${job.id.slice(0,8)} · ${job.settings?.frames||25} frames / ${((job.settings?.frames||25)/24).toFixed(2)} s`;if(job.status==='failed')showError(job.message+' You can adjust your direction and generate again.');if(job.status==='completed'){const url=`/api/jobs/${job.id}/video`;$('video').src=url;$('video').hidden=false;$('empty').hidden=true;$('download').href=url+'?download=true';$('download').download=`opencinema-${job.id.slice(0,8)}.mp4`;$('download').hidden=false;showError('')}}
async function poll(){if(polling||!active)return;polling=true;try{showError('');render(await request(`/api/jobs/${active}`))}catch(e){showError('Studio connection lost. Reconnecting automatically; do not start a duplicate job.')}finally{polling=false}}
async function refreshHD(sourceId){
  try{const hd=await request(`/api/jobs/${sourceId}/hd`);
    if(displayedSource!==sourceId||active)return;
    if(hd.status==='completed'){
      $('hd-export').hidden=true;
      $('hd-download').href=`/api/jobs/${hd.id}/video?download=true`;
      $('hd-download').download=`opencinema-hd-${sourceId.slice(0,8)}.mp4`;
      $('hd-download').hidden=false;
    }
  }catch(e){}
}
$('hd-export').onclick=async()=>{
  if(!displayedSource)return;
  $('hd-export').disabled=true;showError('');
  try{
    const job=await request(`/api/jobs/${displayedSource}/hd`,{method:'POST'});
    localStorage.setItem('opencinema-v2-job',job.id);
    render(job);
  }catch(e){showError(e.message);$('hd-export').disabled=false;}
};
$('form').onsubmit=async e=>{e.preventDefault();showError('');$('generate').disabled=true;$('video').pause();const body=new FormData();body.append('image',$('image').files[0]);body.append('prompt',$('prompt').value);body.append('seed',$('seed').value);body.append('preset',preset);body.append('scene',$('scene').value);body.append('mood',$('mood').value);body.append('strength',$('strength').value);body.append('frames',$('frames').value);body.append('steps',$('frames').value==='97'?$('steps').value:'8');try{const job=await request('/api/jobs',{method:'POST',body});localStorage.setItem('opencinema-v2-job',job.id);$('video').hidden=true;$('empty').hidden=false;$('download').hidden=true;$('hd-export').hidden=true;$('hd-download').hidden=true;render(job)}catch(e){showError(e.message);$('generate').disabled=!inferenceEnabled}};
async function health(){try{const h=await request('/api/health');inferenceEnabled=h.inference_enabled!==false;$('generate').disabled=!!active||!inferenceEnabled;$('connection').textContent=!inferenceEnabled?'Offline preview · GPU disabled':h.connected?'ComfyUI connected':'ComfyUI offline';$('connection').classList.toggle('offline',!h.connected);if(h.active_job&&!active){active=h.active_job;localStorage.setItem('opencinema-v2-job',active);await poll()}}catch{$('connection').textContent='Studio offline';$('connection').classList.add('offline')}}
// Preview is read-only: the backend remains the single source of truth for camera instructions.
function labelFinalPromptPreview(){
  const button=$('enhance');
  // Preserve decorative icons and nested markup; replace only existing label text.
  function rename(node){
    for(const child of node.childNodes){
      if(child.nodeType===Node.TEXT_NODE){
        child.textContent=child.textContent.replace(/Preview AI Director guidance/gi,'Preview Final Prompt');
      }else if(child.nodeType===Node.ELEMENT_NODE){rename(child)}
    }
  }
  rename(button);
}
labelFinalPromptPreview();
$('enhance').onclick=async()=>{
  try{
    const body=new FormData();
    for(const key of ['prompt','scene','mood'])body.append(key,$(key).value);
    body.append('preset',preset);
    const d=await request('/api/director',{method:'POST',body});
    $('direction-text').textContent=d.prompt;
    const selected=document.querySelector('[data-preset].selected');
    const cameraName=selected?.textContent.trim().replace(/\s+/g,' ')||preset;
    const overridden=d.camera_source==='description';
    const source=overridden?'User prompt':'Camera preset';
    const explanation=overridden
      ? `Selected preset (${cameraName}) was not added because your description contains camera instructions. Edit the prompt if you want the preset applied.`
      : `Selected preset (${cameraName}) was included as text guidance. LTX may not reproduce the camera motion exactly.`;
    $('camera-note').textContent=`Camera source: ${source}. ${explanation} ${d.camera_note||''}`;
    $('direction-preview').hidden=false;
    $('direction-preview').open=true;
    showError('');
  }catch(e){showError(e.message)}
};
for(const id of ['prompt','scene','mood'])$(id).addEventListener('input',()=>{$('direction-preview').hidden=true});
document.querySelectorAll('[data-preset]').forEach(b=>b.addEventListener('click',()=>{$('direction-preview').hidden=true}));
function updateDuration() {
  const frames = Number($('frames').value);
  const untested = frames === 97 || frames === 73;

  $('format-mode').textContent = untested
    ? 'UNTESTED EXPERIMENTAL'
    : frames === 49
      ? 'TESTED EXPERIMENTAL'
      : 'BASELINE';

  $('format-frames').textContent =
    `512 × 320 · ${frames} frames`;

  $('format-duration').textContent =
    `24 fps / ${(frames / 24).toFixed(2)} seconds / batch 1`;

  $('duration-note').textContent = untested
    ? `${frames} frames have not been GPU-validated on 12 GB VRAM. Memory use and runtime remain unknown.`
    : `${frames}-frame ${frames === 25 ? 'baseline' : 'experimental mode'}: successful GPU test manually reported.`;
}
let historyOffset=0, historyBusy=false;
function metricText(metric){return metric&&Number.isFinite(metric.seconds)?`${metric.quality==='approximate'?'≈ ':''}${metric.seconds.toFixed(2)} s`:'Unavailable'}
async function loadBenchmarks(){if(historyBusy)return;historyBusy=true;try{const filter=$('history-frames').value;const data=await request(`/api/benchmarks?limit=25&offset=${historyOffset}${filter?'&frames='+encodeURIComponent(filter):''}`);$('history-body').replaceChildren();for(const job of data.items){const row=document.createElement('tr'),b=job.benchmark||{},m=b.metrics||{},out=b.output||{},settings=job.settings||{};const frameCount=job.frames??settings.frames;const video=Number.isFinite(out.duration_seconds)?`${out.duration_seconds.toFixed(2)} s (container)`:Number.isFinite(settings.duration_seconds)?`${settings.duration_seconds.toFixed(2)} s (requested)`:'Unavailable';const peak=job.gpu?.peak_observed_memory_mib;const cells=[job.created?`${job.kind==='hd'?'HD Upscale · ':'LTX · '}${new Date(job.created*1000).toLocaleString()}`:'Unavailable',`${frameCount??'—'} / ${out.frames??'—'}`,video,(job.kind==='hd'&&Number.isFinite(job.elapsed_seconds)?`${job.elapsed_seconds.toFixed(2)} s (wall)` : metricText(m.total)),metricText(m.queue_wait),metricText(m.inference),Number.isFinite(peak)?`${peak.toFixed(0)} MiB (observed; ${job.gpu.status})`:`Unavailable (${job.gpu?.status||'unknown'})`,settings.width&&settings.height?`${settings.width} × ${settings.height}`:'Unavailable',job.seed??'—',job.strength??settings.strength??'—',job.status];for(const value of cells){const cell=document.createElement('td');cell.textContent=String(value);row.appendChild(cell)}row.title=`${job.id}: ${job.message||''}
Inference: ${m.inference?.source||'unavailable'}
Queue: ${m.queue_wait?.source||'unavailable'}`;$('history-body').appendChild(row)}$('manual-baselines').textContent=data.manual_baselines_note;$('history-message').textContent=data.items.length?`Showing ${historyOffset+1}–${historyOffset+data.items.length} v2 experiments.`:'No completed or failed v2 experiments on this page.';$('history-prev').disabled=historyOffset===0;$('history-next').disabled=data.items.length<25}catch(e){$('history-message').textContent='History unavailable. Refresh to retry.'}finally{historyBusy=false}}
$('history-refresh').onclick=loadBenchmarks;
$('history-frames').onchange=()=>{if(historyBusy)return;historyOffset=0;loadBenchmarks()};
$('history-prev').onclick=()=>{if(historyBusy)return;historyOffset=Math.max(0,historyOffset-25);loadBenchmarks()};
$('history-next').onclick=()=>{if(historyBusy)return;historyOffset+=25;loadBenchmarks()};
$('frames').onchange=updateDuration;
async function init(){ $('generate').disabled=true;try{const options=await request('/api/presets');$('frames').replaceChildren(...options.durations.map(mode=>new Option(mode.label,String(mode.frames))));$('frames').value='25';updateDuration();for(const [key,value] of Object.entries(options.scenes))$('scene').add(new Option(value.label,key));for(const key of Object.keys(options.moods))$('mood').add(new Option(key[0].toUpperCase()+key.slice(1),key));}catch(e){showError('Unable to load direction presets. Refresh to retry.');return;}const saved=localStorage.getItem('opencinema-v2-job');if(saved){try{render(await request(`/api/jobs/${saved}`))}catch{localStorage.removeItem('opencinema-v2-job')}}await health();await loadBenchmarks();setInterval(poll,1500);setInterval(health,10000);setInterval(loadBenchmarks,10000)}init();

// Keep experimental sampling selection limited to 97-frame mode.
$('steps').disabled = $('frames').value !== '97';
$('frames').addEventListener('change', () => {
  const enabled = $('frames').value === '97';
  $('steps').disabled = !enabled;
  if (!enabled) $('steps').value = '8';
});
