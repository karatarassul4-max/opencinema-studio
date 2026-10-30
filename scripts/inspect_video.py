"""Decode every generated frame and build a contact sheet for manual visual QA."""
import hashlib, json, pathlib, sys
import av
import numpy as np
from PIL import Image, ImageDraw

video=pathlib.Path(sys.argv[1]).resolve()
out=video.parent
container=av.open(str(video)); stream=container.streams.video[0]
frames=[f.to_ndarray(format='rgb24') for f in container.decode(video=0)]
if not frames: raise RuntimeError('No decoded video frames')
indices=sorted(set([0,len(frames)//4,len(frames)//2,3*len(frames)//4,len(frames)-1]))
width,height=frames[0].shape[1],frames[0].shape[0]
sheet=Image.new('RGB',(width*len(indices),height+28),'#111111'); draw=ImageDraw.Draw(sheet)
for i,index in enumerate(indices):
    sheet.paste(Image.fromarray(frames[index]),(i*width,28)); draw.text((i*width+8,8),f'Frame {index}',fill='white')
sheet.save(out/'contact-sheet.jpg')
changes=[float(np.abs(b.astype(np.float32)-a.astype(np.float32)).mean()) for a,b in zip(frames,frames[1:])]
report={'file':str(video),'sha256':hashlib.file_digest(video.open('rb'),'sha256').hexdigest(),'bytes':video.stat().st_size,'codec':stream.codec_context.name,'width':width,'height':height,'decoded_frames':len(frames),'fps':float(stream.average_rate),'duration_seconds':len(frames)/float(stream.average_rate),'mean_frame_pixel_change':float(np.mean(changes)),'min_frame_pixel_change':float(min(changes)),'first_last_mean_pixel_difference':float(np.abs(frames[-1].astype(np.float32)-frames[0].astype(np.float32)).mean()),'contact_sheet_indices':indices,'quality_note':'Pixel changes establish non-identical frames, not semantic motion quality. Contact sheet requires visual review.'}
(out/'video-inspection.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
