"""Commit a real maintenance checkpoint at most every 25 days, even if builds fail."""
import datetime as dt
import json
from pathlib import Path
import subprocess

INTERVAL_DAYS = 25


def due(previous, now):
    return previous is None or (now - dt.datetime.fromisoformat(previous)).total_seconds() >= INTERVAL_DAYS * 86400


def main():
    path = Path('.maintenance/heartbeat.json')
    data = json.loads(path.read_text()) if path.exists() else {}
    now = dt.datetime.now(dt.timezone.utc)
    if not due(data.get('checked_at'), now):
        print('Maintenance checkpoint is current; no commit needed.')
        return
    data = {'checked_at': now.isoformat()}
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n')
    for args in [
        ['git', 'config', 'user.name', 'github-actions[bot]'],
        ['git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com'],
        ['git', 'add', '.maintenance/heartbeat.json'],
        ['git', 'commit', '-m', 'chore: maintenance [skip ci]'],
        ['git', 'push', 'origin', 'HEAD:main'],
    ]:
        subprocess.run(args, check=True)


if __name__ == '__main__':
    main()
