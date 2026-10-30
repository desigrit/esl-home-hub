import concurrent.futures
import json
import os
import platform
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
import requests
from .health import aggregate, age, calendar_health, display_health, insignia_health, now_iso, PACIFIC, reddit_health, timestamp
from .registry import DISPLAYS, SYSTEMS


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=True), encoding='utf-8')
    if os.name != 'nt':
        tmp.chmod(0o600)
    tmp.replace(path)


def host_status():
    if platform.system() != 'Linux':
        return dict(status='unknown', name='Raspberry Pi', summary='Host metrics become available on the Pi', metrics=[], services=[])
    import psutil
    memory, disk = psutil.virtual_memory(), shutil.disk_usage('/')
    temperature = None
    temp = Path('/sys/class/thermal/thermal_zone0/temp')
    if temp.exists():
        temperature = round(int(temp.read_text()) / 1000, 1)
    services = []
    for service, label in [('esl_hub', 'ESL scheduler'), ('note-calendar', 'Calendar controller')]:
        result = subprocess.run(['systemctl', 'is-active', service], capture_output=True, text=True, timeout=3)
        services.append(dict(name=label, id=service, status=result.stdout.strip() or 'unknown'))
    issues = []
    if any(x['status'] != 'active' for x in services):
        issues.append('A required service is not running')
    if memory.percent > 90:
        issues.append('Memory usage is above 90%')
    disk_percent = round(disk.used / disk.total * 100)
    if disk_percent > 90:
        issues.append('Storage usage is above 90%')
    if temperature is not None and temperature >= 80:
        issues.append('The CPU temperature is high')
    return dict(status='warning' if issues else 'healthy', name='Raspberry Pi', model=Path('/proc/device-tree/model').read_text().strip('\x00') if Path('/proc/device-tree/model').exists() else platform.machine(), hostname=platform.node(), summary='; '.join(issues) if issues else 'Online and responding', uptime_seconds=int(time.time() - psutil.boot_time()), checked_at=now_iso(), services=services, metrics=[dict(label='CPU usage', value=psutil.cpu_percent(interval=None), unit='%'), dict(label='Memory', value=memory.percent, unit='%', detail=f'{round(memory.used / 1024**2)} / {round(memory.total / 1024**2)} MB'), dict(label='Storage', value=disk_percent, unit='%', detail=f'{disk.used / 1024**3:.1f} / {disk.total / 1024**3:.1f} GB'), dict(label='Temperature', value=temperature, unit='°C')])


class HubService:
    def __init__(self, backend, config, state_dir):
        self.backend, self.config = backend, config
        self.state_dir = Path(state_dir)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix='ronhub-status')
        self.lock = threading.Lock()
        self.report_lock = threading.Lock()
        self.cached = None
        self.cached_at = 0
        self.external = None
        self.external_at = 0

    def esl(self):
        data = self.backend.status()
        jobs = []
        for meta in DISPLAYS:
            job = data.get('jobs', {}).get(meta['id'], {})
            state, summary = display_health(job)
            jobs.append({**meta, **job, 'status': state, 'summary': summary})
        enabled = [j for j in jobs if j.get('enabled')]
        state = aggregate([j['status'] for j in enabled]) if enabled else 'paused'
        summary = f"{len(enabled)} of {len(jobs)} displays scheduled"
        if not data.get('scheduler_running'):
            state, summary = 'error', 'The ESL update scheduler is stopped'
        return dict(status=state, summary=summary, jobs=jobs, scheduler_running=data.get('scheduler_running'), checked_at=now_iso(), metrics=[dict(label='Scheduled displays', value=len(enabled)), dict(label='Paused', value=len(jobs) - len(enabled))])

    def calendar(self):
        response = requests.get(self.config['note_url'] + '/api/status', timeout=(2, 5))
        response.raise_for_status()
        data = response.json()
        state, summary = calendar_health(data)
        return dict(status=state, summary=summary, data=data, checked_at=now_iso(), metrics=[dict(label='Upcoming events', value=data.get('total', 0)), dict(label='On display', value=data.get('shown', 0))], next_run=data.get('next_update'))

    def insignia(self):
        cfg = self.config.get('insignia') or {}
        if not cfg.get('key_path'):
            return dict(status='unknown', summary='Connect the Azure status reader', connected=False, checked_at=None)
        if self.external is not None and time.monotonic() - self.external_at < 45:
            return self.external
        command = ['ssh', '-i', cfg['key_path'], '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + cfg['known_hosts'], cfg['host'], cfg.get('command', 'status')]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=9)
            if result.returncode:
                raise ConnectionError('Azure status reader did not respond')
            data = json.loads(result.stdout)
            state, summary = insignia_health(data)
            value = dict(status=state, summary=summary, connected=True, data=data, checked_at=now_iso(), next_run=data.get('next_scan_at'), metrics=[dict(label='Posts tracked', value=data.get('seen', 0)), dict(label='Pending notifications', value=data.get('pending', 0))])
            write_json(self.state_dir / 'insignia-last.json', value)
        except (OSError, ValueError, subprocess.SubprocessError, ConnectionError):
            previous = read_json(self.state_dir / 'insignia-last.json', {})
            local = datetime.now(PACIFIC)
            quiet = local.hour < 6 or local.hour >= 22
            value = {**previous, 'status': 'sleeping' if quiet else 'offline', 'summary': 'VM unreachable during scheduled quiet hours' if quiet else 'Cannot reach the Azure status reader', 'connected': False, 'checked_at': now_iso(), 'last_observed_at': previous.get('checked_at'), 'next_run': None, 'metrics': previous.get('metrics', [])}
            if quiet and previous.get('status') in ('error', 'warning'):
                value.update(status=previous['status'], summary=previous['summary'] + '. VM is currently in its scheduled quiet hours.')
        self.external, self.external_at = value, time.monotonic()
        return value

    def reddit(self):
        try:
            report = read_json(self.state_dir / 'reddit.json')
        except ValueError:
            return dict(status='error', summary='The Windows status report could not be read', checked_at=None)
        if not report:
            return dict(status='unknown', summary='Waiting for the Windows status bridge', checked_at=None, connected=False)
        data = report['data']
        fresh = age(report.get('received_at'))
        sampled = age(data.get('sampled_at'))
        state, summary = reddit_health(data)
        if fresh is None or sampled is None or fresh > 180 or sampled > 180:
            state, summary = 'unknown', 'Windows status is stale. Check that the PC and status bridge are running.'
        return dict(status=state, summary=summary, connected=fresh is not None and fresh <= 180 and sampled is not None and sampled <= 180, checked_at=report.get('received_at'), data=data, next_run=data.get('next_scheduled_local') if data.get('automation_status') == 'ACTIVE' and not data.get('workflow_state', {}).get('blocked') else None, metrics=[dict(label='Confirmed appeals', value=data.get('confirmed_submissions', 0)), dict(label='Recorded attempts', value=data.get('records', 0))])

    def receive_reddit(self, data):
        if not isinstance(data, dict) or not isinstance(data.get('workflow_state'), dict) or not isinstance(data.get('history'), list):
            raise ValueError('A workflow state and history are required.')
        sampled = age(data.get('sampled_at'))
        if sampled is None or sampled > 180 or sampled < -60:
            raise ValueError('The Windows report timestamp is not current.')
        allowed = {'sampled_at', 'username', 'records', 'confirmed_submissions', 'workflow_state', 'next_scheduled_local', 'automation_status', 'history', 'resolved', 'window', 'last_record'}
        data = {k: v for k, v in data.items() if k in allowed}
        data['history'] = data['history'][:30]
        with self.report_lock:
            write_json(self.state_dir / 'reddit.json', dict(received_at=now_iso(), data=data))
        self.cached_at = 0

    def receive_gpu(self, data):
        if not isinstance(data, dict) or not isinstance(data.get('snapshot'), dict):
            raise ValueError('A GPU snapshot is required.')
        elapsed = age(data.get('sampled_at'))
        if elapsed is None or elapsed > 65 or elapsed < -60:
            raise ValueError('The GPU report timestamp is not current.')
        if data.get('protocolVersion') != 1 or not isinstance(data.get('sampleAgeMs'), (int, float)) or data['sampleAgeMs'] < 0 or data['sampleAgeMs'] > 65000:
            raise ValueError('The GPU companion report is invalid or stale.')
        snapshot = data['snapshot']
        checks = snapshot.get('checks')
        if snapshot.get('mode') != 'host' or not isinstance(checks, list) or len(checks) != 5 or {c.get('id') for c in checks if isinstance(c, dict)} != {'ollama','tailscale','forwarding','gpu','models'}:
            raise ValueError('The GPU companion checks are incomplete.')
        allowed = {'gpuMetrics','checkedAtMs','externalEndpoint','gpuName','checks','version','latencyMs','modelCount','loadedModels','installedModels','gpuHistory','serverName','mode'}
        data = {k: data[k] for k in ('sampled_at','sampleAgeMs','protocolVersion')}
        data['snapshot'] = {k:v for k,v in snapshot.items() if k in allowed}
        with self.report_lock:
            write_json(self.state_dir / 'gpu.json', dict(received_at=now_iso(), data=data))
        self.cached_at = 0

    def gpu(self):
        report = read_json(self.state_dir / 'gpu.json')
        if not report:
            return dict(status='unknown', summary='Waiting for the Shambu host companion', connected=False, checked_at=None)
        data = report['data']
        snapshot = dict(data['snapshot'])
        elapsed = max(0, age(data.get('sampled_at')) or 0)
        fresh = elapsed + data['sampleAgeMs'] / 1000 <= 65
        checks = snapshot.get('checks', [])
        bad = [c for c in checks if c.get('state') not in ('ok','idle')]
        state = 'healthy'
        summary = 'Ollama and Tailscale are ready'
        if bad:
            state = 'error' if any(c.get('state') in ('error','failed','offline') for c in bad) else 'warning'
            summary = '; '.join(c.get('detail') or c.get('label') or c['id'] for c in bad)
        if not fresh:
            state, summary = 'unknown', 'GPU status is stale. Check the PC and Windows status bridge.'
        metrics = snapshot.get('gpuMetrics')
        if not isinstance(metrics, dict) or elapsed + metrics.get('sampleAgeMs', 999999) / 1000 > 15:
            snapshot['gpuMetrics'] = None
        return dict(status=state, summary=summary, connected=fresh, checked_at=report.get('received_at'), data=snapshot, sampled_at=data.get('sampled_at'), metrics=[dict(label='Available models',value=snapshot.get('modelCount', 0)),dict(label='GPU',value=snapshot.get('gpuName') or 'Unknown')])

    def insignia_action(self, action):
        if action not in ('pause', 'resume'):
            raise ValueError('Unknown monitor action.')
        cfg = self.config.get('insignia') or {}
        if not cfg.get('key_path'):
            raise ValueError('Connect the Azure status reader first.')
        result = subprocess.run(['ssh', '-i', cfg['key_path'], '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + cfg['known_hosts'], cfg['host'], action], capture_output=True, text=True, timeout=18)
        if result.returncode:
            raise ValueError('The monitor action could not be confirmed. Refresh status before trying again.')
        self.external_at = self.cached_at = 0
        return json.loads(result.stdout)

    def snapshot(self, force=False):
        with self.lock:
            if self.cached is not None and not force and time.monotonic() - self.cached_at < 12:
                return self.cached
            adapters = {'esl': self.esl, 'calendar': self.calendar, 'insignia': self.insignia, 'reddit': self.reddit, 'gpu': self.gpu}
            futures = {key: self.pool.submit(fn) for key, fn in adapters.items()}
            host_future = self.pool.submit(host_status)
            systems, issues, activity = [], [], []
            for meta in SYSTEMS:
                try:
                    result = futures[meta['id']].result(timeout=12)
                except Exception:
                    result = dict(status='offline', summary=f"Cannot read {meta['name']} status. Check its service connection.", checked_at=now_iso())
                item = {**meta, **result}
                if meta['id'] == 'insignia':
                    item['manage_url'] = (self.config.get('insignia') or {}).get('portal_url', 'https://portal.azure.com/')
                systems.append(item)
                if item['status'] in ('error', 'warning', 'offline', 'unknown'):
                    issues.append(dict(id=meta['id'], title=meta['name'], detail=item['summary'], status=item['status'], path=meta['path'], action='Review system'))
                if meta['id'] == 'esl':
                    for job in item.get('jobs', []):
                        if job['status'] in ('error', 'warning', 'unknown') and job.get('enabled'):
                            issues.append(dict(id='esl-' + job['id'], title=job['name'], detail=job['summary'], status=job['status'], path='/systems/esl/' + job['id'], action='Review display'))
                        for log in job.get('logs', [])[:5]:
                            activity.append(dict(system='esl', name=job['name'], path='/systems/esl/' + job['id'], timestamp=log.get('finished_at'), status={'Success': 'healthy', 'Failed': 'error', 'Pending': 'warning'}.get(log.get('status'), 'unknown'), label=log.get('status', 'Unknown'), output=log.get('output', ''), duration=log.get('duration_seconds')))
                if meta['id'] == 'reddit':
                    for event in item.get('data', {}).get('history', [])[:5]:
                        activity.append(dict(system='reddit', name='Reddit appeal', path=meta['path'], timestamp=event.get('finished_at', event.get('timestamp')), status={'success': 'healthy', 'failure': 'error', 'unknown': 'warning'}.get(event.get('status'), 'unknown'), label=event.get('status', 'Unknown').capitalize(), output=event.get('detail', '')))
            try:
                host = host_future.result(timeout=4)
            except Exception:
                host = dict(status='unknown', name='Raspberry Pi', summary='Host metrics are unavailable', metrics=[], services=[])
            if host['status'] in ('error', 'warning', 'offline', 'unknown'):
                issues.insert(0, dict(id='host', title='Raspberry Pi', detail=host['summary'], status=host['status'], path='/settings', action='Review host'))
            # Display failures already carry more useful detail than the ESL summary.
            if any(i['id'].startswith('esl-') for i in issues):
                issues = [i for i in issues if i['id'] != 'esl']
            activity.sort(key=lambda x: timestamp(x.get('timestamp')).timestamp() if timestamp(x.get('timestamp')) else 0, reverse=True)
            self.cached = dict(checked_at=now_iso(), timezone='America/Los_Angeles', systems=systems, host=host, issues=issues, activity=activity[:18], status=aggregate([x['status'] for x in systems] + [host['status']]))
            self.cached_at = time.monotonic()
            return self.cached
