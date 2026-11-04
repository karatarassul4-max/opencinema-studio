"""Optional device-level observation. No GPU management operations."""
import asyncio
import importlib.util
import json
import math
import os
import re
import shutil
import time
from .benchmark import capture_process


def number(value, maximum=None):
    try:
        value = float(value)
        if math.isfinite(value) and value >= 0 and (maximum is None or value <= maximum):
            return value
    except (ValueError, TypeError):
        pass
    return None


async def sample_device(index=0):
    if importlib.util.find_spec('pynvml'):
        def read_nvml():
            import pynvml as nvml
            nvml.nvmlInit()
            try:
                handle = nvml.nvmlDeviceGetHandleByIndex(index)
                try:
                    memory = nvml.nvmlDeviceGetMemoryInfo(handle).used / (1024 * 1024)
                except nvml.NVMLError:
                    memory = None
                try:
                    utilization = nvml.nvmlDeviceGetUtilizationRates(handle).gpu
                except nvml.NVMLError:
                    utilization = None
                return {'memory_used_mib': number(memory), 'utilization_percent': number(utilization, 100), 'provider': 'nvml'}
            finally:
                nvml.nvmlShutdown()
        try:
            return await asyncio.wait_for(asyncio.to_thread(read_nvml), 2)
        except Exception:
            pass  # Installed but unusable NVML may fall back to the read-only CLI.
    executable = shutil.which('nvidia-smi')
    if not executable:
        raise OSError('No installed NVML or nvidia-smi provider')
    raw = await capture_process(executable, '--id='+str(index), '--query-gpu=memory.used,utilization.gpu', '--format=csv,noheader,nounits', timeout=2)
    values = raw.strip().split(',')
    if len(values) != 2:
        raise ValueError('Unexpected nvidia-smi response')
    return {'memory_used_mib': number(values[0]), 'utilization_percent': number(values[1], 100), 'provider': 'nvidia-smi'}


class GPUMonitor:
    def __init__(self, directory, enabled=False, interval=2.0, index=0, sampler=None):
        self.directory = directory
        self.enabled, self.interval, self.index = enabled, max(1.0, min(60.0, interval)), index
        self.sampler = sampler or sample_device
        self.jobs, self.tasks, self.stops = {}, {}, {}

    def path(self, jid):
        if not re.fullmatch('[0-9a-f]{32}', jid):
            raise ValueError('Invalid monitoring job ID')
        return self.directory / (jid + '-gpu.json')

    def start(self, jid):
        if jid in self.jobs:
            return
        self.path(jid)
        self.jobs[jid] = {'status': 'sampling' if self.enabled else 'disabled', 'scope': 'device-wide; not v2-exclusive',
            'sampling_interval_seconds': self.interval, 'device_index': self.index, 'peak_observed_memory_mib': None,
            'samples': [], 'sample_count': 0, 'errors': [], 'coverage': 'job observation window; polling may miss peaks',
            'started_at': time.time()}
        self.stops[jid] = asyncio.Event()
        self.tasks[jid] = asyncio.create_task(self.run(jid))

    async def persist(self, jid):
        # Disk I/O happens outside the generation path/event loop.
        payload = json.dumps(self.jobs[jid], allow_nan=False)
        path = self.path(jid)
        def write():
            temporary = path.with_suffix('.json.tmp')
            temporary.write_text(payload, encoding='utf-8')
            temporary.replace(path)
        try:
            await asyncio.to_thread(write)
        except OSError:
            self.jobs[jid]['storage_error'] = 'Unable to persist GPU samples'

    async def run(self, jid):
        state = self.jobs[jid]
        started = time.monotonic()
        try:
            while self.enabled and not self.stops[jid].is_set():
                try:
                    sample = await asyncio.wait_for(self.sampler(self.index), timeout=3)
                    if self.stops[jid].is_set():
                        break  # Do not attribute post-terminal samples to this job.
                    memory = number(sample.get('memory_used_mib'))
                    utilization = number(sample.get('utilization_percent'),100)
                    if memory is None and utilization is None:
                        raise ValueError('Metrics unsupported by provider')
                    state['provider'] = sample.get('provider', 'injected')
                    state['sample_count'] += 1
                    state['samples'].append({'unix_seconds': time.time(), 'elapsed_seconds': time.monotonic()-started,
                        'memory_used_mib': memory, 'utilization_percent': utilization})
                    # Keep storage bounded during indefinitely disconnected jobs.
                    state['samples'] = state['samples'][-3600:]
                    if memory is not None:
                        state['peak_observed_memory_mib'] = max(memory, state['peak_observed_memory_mib'] or 0)
                except (Exception,):
                    state['errors'].append({'unix_seconds': time.time(), 'message': 'GPU polling failed, timed out or unsupported'})
                    state['status'] = 'partial' if state['sample_count'] else 'unavailable'
                    break  # A failing monitor never stalls/retries generation.
                await self.persist(jid)
                try:
                    await asyncio.wait_for(self.stops[jid].wait(), self.interval)
                except TimeoutError:
                    pass
            if state['status'] == 'sampling':
                state['status'] = 'available' if state['sample_count'] else 'unavailable'
        except asyncio.CancelledError:
            state['status'] = 'partial' if state['sample_count'] else 'unavailable'
            state['errors'].append({'unix_seconds':time.time(), 'message':'Monitoring stopped with v2 process'})
        finally:
            state['finished_at'] = time.time()
            await self.persist(jid)

    def stop(self, jid):
        if jid in self.stops:
            self.stops[jid].set()

    def summary(self, jid):
        state = self.jobs.get(jid)
        if state is None:
            try:
                state = json.loads(self.path(jid).read_text(encoding='utf-8'))
                if state.get('status') == 'sampling':
                    state['status'] = 'partial'
                    state['coverage'] = 'interrupted process; monitoring was not resumed'
            except (OSError, ValueError):
                return {'status':'unavailable','peak_observed_memory_mib':None}
        return {key:value for key,value in state.items() if key != 'samples'}

    async def close(self):
        for jid in self.stops:
            self.stop(jid)
        if self.tasks:
            done,pending = await asyncio.wait(list(self.tasks.values()),timeout=4)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
