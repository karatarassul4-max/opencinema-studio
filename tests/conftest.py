"""Block outbound sockets; allow only Python's internal Windows socketpair."""
import os
from pathlib import Path
os.environ['OPENCINEMA_V2_ENABLE_INFERENCE'] = '0'
os.environ['OPENCINEMA_V2_GPU_MONITOR'] = '0'
os.environ['OPENCINEMA_V2_DATA'] = str(Path(__file__).resolve().parents[1] / 'artifacts/offline-tests/default-store')
os.environ['OPENCINEMA_V2_PUBLIC_HOST'] = ''

import socket
import sys
import pytest

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    original = socket.socket.connect
    def blocked(sock, address):
        caller = sys._getframe(1)
        if caller.f_code.co_name == 'socketpair' and caller.f_code.co_filename == socket.__file__:
            return original(sock, address)
        raise OSError('Network disabled by offline test suite')
    def blocked_ex(*args, **kwargs):
        raise OSError('Network disabled by offline test suite')
    monkeypatch.setattr(socket.socket, 'connect', blocked)
    monkeypatch.setattr(socket.socket, 'connect_ex', blocked_ex)

@pytest.fixture(autouse=True)
def no_output_helpers(monkeypatch):
    async def unavailable(path):
        return {'frames':None, 'duration_seconds':None, 'verification':'unavailable'}
    monkeypatch.setattr('app.main.probe_video', unavailable)

@pytest.fixture
def tmp_path(tmp_path_factory):
    # Store enforces project-local data; retain that boundary in portable tests.
    import tempfile
    import shutil
    root = Path(__file__).resolve().parents[1] / 'artifacts/offline-tests'
    root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='case-', dir=root))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)
