#!/usr/bin/python3
"""Restricted SSH entry point: sanitized status plus timer pause/resume only."""
import json
import os
import sqlite3
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

command = os.environ.get('SSH_ORIGINAL_COMMAND', 'status').strip()
if command in ('pause', 'resume'):
    args = ['sudo', '-n', 'systemctl', 'disable' if command == 'pause' else 'enable', '--now', 'insignia-monitor.timer']
    subprocess.run(args, check=True, capture_output=True, timeout=12)
    print(json.dumps({'ok': True, 'action': command}))
elif command == 'status':
    # A read-only database connection works while the scanner holds its process lock.
    script = r'''
import json, sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
db=sqlite3.connect('file:/var/lib/insignia-monitor/monitor.sqlite3?mode=ro',uri=True,timeout=3)
db.row_factory=sqlite3.Row
meta=dict(db.execute('select key,value from metadata').fetchall())
counts=dict(db.execute('select count(*) as seen, coalesce(sum(baseline=0 and delivered_at is null),0) as pending, coalesce(sum(blocked=1),0) as blocked from posts').fetchone())
keys=('checkpoint','paused','last_result','delivery_paused','last_failure_reason','health_state')
result={**counts,**{k:meta.get(k) for k in keys},'scan_failures':int(meta.get('scan_failures') or 0),'recovery_streak':int(meta.get('recovery_streak') or 0),'next_scan_at':meta.get('scan_next_attempt'),'active_now':6<=datetime.now(ZoneInfo('America/Los_Angeles')).hour<22}
print(json.dumps(result))
'''
    result = subprocess.run(['sudo', '-n', '-u', 'insignia-monitor', '/usr/bin/python3', '-c', script], check=True, capture_output=True, text=True, timeout=8)
    data = json.loads(result.stdout)
    timer = subprocess.run(['systemctl', 'is-active', 'insignia-monitor.timer'], capture_output=True, text=True, timeout=3)
    data['timer_active'] = timer.stdout.strip() == 'active'
    data['checked_at'] = datetime.now(ZoneInfo('UTC')).isoformat()
    print(json.dumps(data))
else:
    raise SystemExit('Unsupported RonHub action')
