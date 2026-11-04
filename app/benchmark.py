"""Observed job timing. Never subtract monotonic clocks across processes."""
import asyncio
import json
import math
import os
import shutil
import subprocess
import time
import uuid


def metric(seconds=None, quality='unavailable', source='not observed'):
    return {'seconds': seconds, 'quality': quality, 'source': source}


class Benchmark:
    def __init__(self, wall=time.time, monotonic=time.monotonic):
        self.wall, self.monotonic = wall, monotonic
        self.session = uuid.uuid4().hex

    def ensure(self, job):
        b = job.setdefault('benchmark', {})
        b.setdefault('version', 1)
        b.setdefault('marks', {})
        b.setdefault('metrics', {})
        b.setdefault('output', {'frames': None, 'duration_seconds': None, 'file_size_bytes': None, 'verification': 'unavailable'})
        return b

    def mark(self, job, name, source='local observation'):
        benchmark = self.ensure(job)
        if name not in benchmark['marks']:
            benchmark['marks'][name] = {'unix_seconds': self.wall(), 'monotonic_seconds': self.monotonic(),
                                       'process_session': self.session, 'source': source}
        self.refresh(job)

    def elapsed(self, job, start, end, approximate=False):
        marks = self.ensure(job)['marks']
        a, b = marks.get(start), marks.get(end)
        if not a or not b:
            return metric()
        if a['process_session'] != b['process_session']:
            return metric(source='process restarted; no cross-process monotonic subtraction')
        seconds = b['monotonic_seconds'] - a['monotonic_seconds']
        if seconds < 0:
            return metric(source='invalid observation order')
        return metric(seconds, 'approximate' if approximate else 'measured', 'local monotonic observations')

    def refresh(self, job):
        b = self.ensure(job)
        b['metrics'] = {
            'queue_wait': self.elapsed(job, 'prompt_sent', 'inference_started', True),
            'inference': self.elapsed(job, 'inference_started', 'inference_completed', True),
            'retrieval': self.elapsed(job, 'retrieval_started', 'retrieval_completed'),
            'total': self.elapsed(job, 'submitted', 'retrieval_completed' if 'retrieval_completed' in b['marks'] else 'terminal'),
        }
        # A complete server event pair is preferable to delayed polling observations.
        server = b.get('server_events', {})
        end = 'execution_success' if 'execution_success' in server else 'execution_error'
        if 'execution_start' in server and end in server:
            delta = server[end] - server['execution_start']
            if 0 <= delta <= 7 * 86400:
                b['metrics']['inference'] = metric(delta, 'approximate', 'ComfyUI server wall timestamps; includes loading, sampling, decoding and encoding; end='+end)

    def history(self, job, record):
        b = self.ensure(job)
        events = b.setdefault('server_events', {})
        for entry in record.get('status', {}).get('messages', []):
            if not isinstance(entry, (list, tuple)) or len(entry) != 2 or not isinstance(entry[1], dict):
                continue
            kind, data = entry
            if kind not in ('execution_start', 'execution_success', 'execution_error'):
                continue
            if data.get('prompt_id') not in (None, job.get('prompt_id')):
                continue
            stamp = data.get('timestamp')
            if isinstance(stamp, (int, float)) and not isinstance(stamp, bool) and math.isfinite(stamp) and stamp > 0:
                events.setdefault(kind, stamp / 1000)  # ComfyUI event timestamps are milliseconds.
        self.refresh(job)

    def finish(self, job):
        self.mark(job, 'terminal')
        b = self.ensure(job)
        b['status'] = job['status']
        b['error'] = job.get('message') if job['status'] == 'failed' else None


async def capture_process(*args, timeout=3):
    """Bounded read-only helper. Termination only targets our own helper handle."""
    process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout)
        if process.returncode:
            raise OSError('Read-only helper failed')
        return stdout.decode('utf-8', errors='replace')
    finally:
        if process.returncode is None:
            try:
                process.kill()  # Never look up or terminate a service by name/port.
            except ProcessLookupError:
                pass
            await process.wait()


async def probe_video(path):
    """Optional CPU metadata read; do not invent output counts from requested frames."""
    result = {'frames': None, 'duration_seconds': None, 'verification': 'unavailable'}
    executable = shutil.which('ffprobe')
    if not executable:
        return {**result, 'reason': 'ffprobe not installed'}
    try:
        raw = await capture_process(executable, '-v', 'error', '-select_streams', 'v:0', '-show_entries',
            'stream=nb_frames,duration,width,height,r_frame_rate', '-of', 'json', str(path), timeout=5)
        stream = json.loads(raw)['streams'][0]
        if not isinstance(stream, dict):
            raise ValueError('Invalid stream metadata')
        count = stream.get('nb_frames')
        duration = stream.get('duration')
        if str(count).isdigit() and int(count) > 0:
            result['frames'] = int(count)
        if duration not in (None, 'N/A') and math.isfinite(float(duration)) and float(duration) >= 0:
            result['duration_seconds'] = float(duration)
        result.update(verification='container_metadata', source='ffprobe (not full frame decode)',
                      width=stream.get('width'), height=stream.get('height'), frame_rate=stream.get('r_frame_rate'))
        return result
    except (OSError, TimeoutError, ValueError, KeyError, IndexError, TypeError):
        return {**result, 'reason': 'ffprobe unavailable, timed out or could not read metadata'}
