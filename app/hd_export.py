"""Bounded, metadata-aware RealESRGAN HD export."""
import json
import math
import subprocess
from pathlib import Path


def inspect_source(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError('Source MP4 is missing or unsafe.')
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,nb_frames,avg_frame_rate,duration',
            '-of', 'json', str(path)], capture_output=True, text=True, timeout=20, check=True)
        stream = json.loads(result.stdout)['streams'][0]
        width, height = int(stream['width']), int(stream['height'])
        numerator, denominator = map(int, stream['avg_frame_rate'].split('/'))
        fps = numerator / denominator
        frames = int(stream.get('nb_frames') or 0)
        if not frames:
            frames = round(float(stream['duration']) * fps)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError, ZeroDivisionError, TypeError) as exc:
        raise ValueError('Cannot inspect source video with ffprobe.') from exc
    if width < 64 or height < 64 or width > 1920 or height > 1080 or not 1 <= frames <= 97 or not 1 <= fps <= 60:
        raise ValueError('HD export supports 1–97 frames, FPS 1–60 and source up to 1920x1080.')
    # The proven 512x320 source becomes 1280x800. Other aspect ratios are preserved.
    target_width = 1280
    target_height = round((height / width * target_width) / 2) * 2
    if target_height < 2 or target_height > 2160:
        raise ValueError('Unsupported target dimensions.')
    return dict(width=width, height=height, frames=frames, fps=fps,
                target_width=target_width, target_height=target_height)


def hd_workflow(source_path, job_id, metadata):
    source_path = Path(source_path)
    if not source_path.is_file() or source_path.is_symlink():
        raise ValueError('Original video is missing or unsafe.')
    return {
        '1': {'class_type': 'VHS_LoadVideoPath', 'inputs': {
            'video': str(source_path), 'force_rate': 0, 'custom_width': 0,
            'custom_height': 0, 'frame_load_cap': metadata['frames'],
            'skip_first_frames': 0, 'select_every_nth': 1}},
        '2': {'class_type': 'UpscaleModelLoader', 'inputs': {
            'model_name': 'RealESRGAN_x4plus.pth'}},
        '3': {'class_type': 'ImageUpscaleWithModel', 'inputs': {
            'image': ['1', 0], 'upscale_model': ['2', 0]}},
        '4': {'class_type': 'ImageScale', 'inputs': {
            'crop': 'disabled', 'upscale_method': 'lanczos',
            'width': metadata['target_width'], 'height': metadata['target_height'],
            'image': ['3', 0]}},
        '5': {'class_type': 'VHS_VideoCombine', 'inputs': {
            'frame_rate': metadata['fps'], 'loop_count': 0, 'format': 'video/h264-mp4',
            'save_output': True, 'filename_prefix': f'opencinema/{job_id}',
            'images': ['4', 0], 'pingpong': False}}
    }


def validate_hd_output(item, job_id):
    name = item.get('filename', '')
    folder = item.get('subfolder', '')
    if (item.get('type') != 'output' or folder != 'opencinema'
            or not name.startswith(job_id + '_') or not name.endswith('.mp4')
            or any(c in name for c in '/\\:') or '..' in name):
        raise ValueError('Unexpected HD output location')
    return {'filename': name, 'subfolder': folder, 'type': 'output'}
