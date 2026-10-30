"""Export non-media evidence for completed Studio jobs, without input images."""
import hashlib
import json
import pathlib
import sqlite3

root = pathlib.Path(__file__).resolve().parents[1]
data = root / 'artifacts/studio'
db = sqlite3.connect(data / 'jobs.sqlite')
results = []
for row in db.execute('SELECT body FROM jobs'):
    job = json.loads(row[0])
    if job['status'] != 'completed':
        continue
    history = json.loads((data / (job['id'] + '-history.json')).read_text())
    times = {e[0]: e[1].get('timestamp') for e in history['status']['messages']}
    video = data / (job['id'] + '.mp4')
    events = data / (job['id'] + '-events.jsonl')
    results.append({
        **job,
        'execution_seconds': (times['execution_success'] - times['execution_start']) / 1000,
        'bytes': video.stat().st_size,
        'sha256': hashlib.sha256(video.read_bytes()).hexdigest(),
        'websocket_progress_events_saved': len(events.read_text().splitlines()) if events.exists() else 0,
        'cached_nodes': next((e[1]['nodes'] for e in history['status']['messages'] if e[0] == 'execution_cached'), []),
    })
db.close()
(root / 'docs/e2e-evidence.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2))
