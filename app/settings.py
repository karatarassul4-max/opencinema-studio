"""V2 configuration never inherits production authentication or data settings."""
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
HOST = '127.0.0.1'
PORT = 8001
COMFY_URL = os.getenv('OPENCINEMA_V2_COMFY_URL', 'http://127.0.0.1:8189')
INFERENCE_ENABLED = os.getenv('OPENCINEMA_V2_ENABLE_INFERENCE', '0') == '1'

def data_path(value=None):
    path = Path(value or os.getenv('OPENCINEMA_V2_DATA', str(ROOT / 'artifacts/studio'))).resolve()
    if not path.is_relative_to(ROOT) or path == ROOT:
        raise ValueError('V2 storage must be a subdirectory of the v2 project.')
    return path
