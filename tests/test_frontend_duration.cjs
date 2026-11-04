// Offline DOM harness: no browser server, sockets, uploads or GPU calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {value:'',textContent:'',hidden:false,disabled:false,files:[],options:[],children:[],childNodes:[],src:'',appendChild(child){this.children.push(child);},firstChild:{textContent:''},
    classList:{add(){},remove(){},toggle(){},contains(){return false;}},
    addEventListener(){},setAttribute(){},pause(){},add(option){this.options.push(option);},replaceChildren(...options){this.options=options;this.children=[...options];}});
  return elements.get(id);
}
element('prompt').value='Dolly forward toward a red bicycle.';
element('seed').value='421';element('strength').value='0.8';
element('image').files=[new Blob(['offline image placeholder'],{type:'image/png'})];
const cameras = ['static','dolly','orbit','crane'].map(preset=>({...element('camera-'+preset),dataset:{preset}}));
const submitted=[], requestedUrls=[];
const modes=[{frames:25,label:'25 baseline'},{frames:49,label:'49 tested experimental'},{frames:73,label:'73 unverified experimental'},{frames:97,label:'97 untested experimental'}];
const context={document:{getElementById:element,createElement:tag=>({tag,children:[],appendChild(child){this.children.push(child);}}),querySelector:()=>cameras[0],querySelectorAll:()=>cameras},Option:class{constructor(text,value){this.text=text;this.value=value;}},
  Node:{TEXT_NODE:3,ELEMENT_NODE:1},FormData,Blob,URL,crypto:require('node:crypto').webcrypto,Uint32Array,
  localStorage:{getItem(){return null;},setItem(){},removeItem(){}},setInterval(){},
  fetch:async(url,options)=>{
    requestedUrls.push(url);
    let body;
    if(url==='/api/presets')body={durations:modes,scenes:{product:{label:'Product'}},moods:{calm:'calm'}};
    else if(url==='/api/health')body={inference_enabled:false,connected:false};
    else if(url.startsWith('/api/benchmarks'))body={items:[{id:'history-id',created:1,frames:73,settings:{width:512,height:320,duration_seconds:73/24},status:'failed',message:'<script>bad</script>',benchmark:{metrics:{total:{seconds:15,quality:'measured'},inference:{seconds:12,quality:'approximate'}}},gpu:{status:'unavailable',peak_observed_memory_mib:null}}],manual_baselines_note:'Manually reported, not instrumented'};
    else if(url==='/api/director')body={prompt:'Dolly forward toward a red bicycle.',camera_note:'Explicit camera wording takes precedence over the selected preset.'};
    else if(url==='/api/jobs') {submitted.push(options.body);const frames=Number(options.body.get('frames'));body={id:'a'.repeat(32),status:'queued',seed:421,message:'Queued',settings:{frames,fps:24},enhanced_prompt:'Dolly forward'};}
    else throw Error('Unexpected request '+url);
    return {ok:true,json:async()=>body};
  }};
(async()=>{
 vm.runInNewContext(fs.readFileSync('app/static/app.js','utf8'),context);
 await new Promise(setImmediate);
 assert.equal(element('frames').value,'25');
 assert.equal(element('frames').options.length,4);
 assert.match(element('format-duration').textContent,/1.04/);
 assert.equal(element('generate').disabled,true);
 element('scene').value='product';element('mood').value='calm';
 await element('enhance').onclick();
 assert.match(element('camera-note').textContent,/takes precedence/);
 for(const frames of ['25','49','73','97']) {
   element('frames').value=frames;element('frames').onchange();
   assert.match(element('format-frames').textContent,new RegExp(frames+' frames'));
   if(frames==='73') {assert.match(element('duration-note').textContent,/not been GPU-validated/);assert.match(element('format-duration').textContent,/3.04/);}
   if(frames==='97'){assert.match(element('duration-note').textContent,/not been GPU-validated/);element('steps').value='6';}
   if(frames==='49')assert.match(element('duration-note').textContent,/manually reported/);
   // Exercise handler wiring directly; the UI button remains gated offline.
   await element('form').onsubmit({preventDefault(){}});
   assert.equal(submitted.at(-1).get('frames'),frames);
   assert.equal(submitted.at(-1).get('strength'),'0.8');
   assert.equal(submitted.at(-1).get('steps'),frames==='97'?'6':'8');
   assert.match(element('job-info').textContent,new RegExp(frames+' frames'));
 }
 assert.equal(element('history-body').children.length,1);
 assert.equal(element('history-body').children[0].children[5].textContent,'≈ 12.00 s');
 assert.match(element('history-body').children[0].children[6].textContent,/Unavailable/);
 assert.match(element('manual-baselines').textContent,/not instrumented/);
 element('history-frames').value='73';element('history-frames').onchange();await new Promise(setImmediate);
 assert.ok(requestedUrls.some(url=>url.includes('/api/benchmarks?')&&url.endsWith('&frames=73')));
 // Completion must enable Export HD synchronously, before refreshHD resolves.
 vm.runInContext('inferenceEnabled=true',context);
 let resolveHD;
 context.fetch=async()=>({ok:true,json:()=>new Promise(resolve=>{resolveHD=resolve;})});
 const source={id:'b'.repeat(32),status:'running',message:'Rendering',seed:1,settings:{frames:25}};
 context.render(source);
 assert.equal(element('hd-export').disabled,true);
 context.render({...source,status:'completed'});
 assert.equal(element('hd-export').hidden,false);
 assert.equal(element('hd-export').disabled,false);
 await new Promise(setImmediate);
 resolveHD({id:'c'.repeat(32),status:'completed'});await new Promise(setImmediate);
 assert.equal(element('hd-export').hidden,true);
 assert.equal(element('hd-download').hidden,false);
 context.renderHD({id:'c'.repeat(32),kind:'hd',source_job_id:source.id,status:'queued',message:'HD queued'});
 assert.equal(element('generate').disabled,true);
 context.renderHD({id:'c'.repeat(32),kind:'hd',source_job_id:source.id,status:'failed',message:'Retry'});
 assert.equal(element('hd-export').hidden,false);
 assert.equal(element('hd-export').disabled,false);
 context.render({...source,status:'completed'});await new Promise(setImmediate);
 context.render({...source,id:'d'.repeat(32),status:'running'});
 resolveHD({id:'c'.repeat(32),status:'completed'});await new Promise(setImmediate);
 assert.equal(element('hd-download').hidden,true);
 vm.runInContext('inferenceEnabled=false',context);
 context.render({...source,status:'completed'});
 assert.equal(element('hd-export').disabled,true);
 console.log('Frontend offline checks passed: defaults, duration labels, warning, Director note, all four multipart modes and HD completion/retry/stale-response states, result metadata, benchmark labels and history filtering.');
})().catch(error=>{console.error(error);process.exitCode=1;});
