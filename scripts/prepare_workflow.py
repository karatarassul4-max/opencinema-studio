"""Adapt the bundled official native-node graph; preserve its connections."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
w = json.loads((ROOT/'workflows/ltxv-official.json').read_text())
values = {
 '38': {'clip_name':'t5xxl_fp8_e4m3fn_scaled.safetensors','type':'ltxv','device':'default'},
 '44': {'ckpt_name':'ltx-video-2b-v0.9.5.safetensors'},
 '69': {'frame_rate':24.0},
 '71': {'steps':30,'max_shift':2.05,'base_shift':0.95,'stretch':True,'terminal':0.1},
 '73': {'sampler_name':'euler'},
 '72': {'add_noise':True,'noise_seed':20261029,'cfg':3.0},
 '78': {'image':'fox.jpg'},
 '77': {'width':512,'height':320,'length':25,'batch_size':1,'strength':0.85},
 '80': {'fps':24.0},
 '81': {'filename_prefix':'opencinema/ltx-first','format':'mp4','format.codec':'h264'},
 '8': {'tile_size':128,'overlap':32,'temporal_size':8,'temporal_overlap':4},
}
links = {l[0]:l for l in w['links']}
api = {}
for n in w['nodes']:
    if n['type'] in ['Note','MarkdownNote']: continue
    key=str(n['id']); inputs=values.get(key,{}).copy()
    if n['type']=='CLIPTextEncode': inputs['text']=n['widgets_values'][0]
    for item in n.get('inputs',[]):
        if item.get('link') is not None:
            link=links[item['link']]; inputs[item['name']]=[str(link[1]),link[2]]
    api[key]={'class_type':'VAEDecodeTiled' if key=='8' else n['type'],'inputs':inputs}
    if key=='38': n['widgets_values']=[values[key]['clip_name'],'ltxv','default']
    if key=='69': n['widgets_values']=[24]
    if key=='72': n['widgets_values']=[True,20261029,'fixed',3]
    if key=='78': n['widgets_values']=['fox.jpg','image']
    if key=='77': n['widgets_values']=[512,320,25,1,0.85]
    if key=='81': n['widgets_values']=['opencinema/ltx-first','mp4','h264']
    if key=='8': n['type']='VAEDecodeTiled'; n['widgets_values']=[128,32,8,4]; n['properties']['Node name for S&R']='VAEDecodeTiled'
(ROOT/'workflows/ltx-i2v-api.json').write_text(json.dumps(api,indent=2))
(ROOT/'workflows/ltx-i2v-ui.json').write_text(json.dumps(w,indent=2))
