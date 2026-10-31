"""Minute-by-minute, read-only Zebby collection, independent of an open browser."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import threading
import time
import requests
from .health import age, aggregate

SERVICE_URL = 'https://zebby-credits-9d5bde.westus2.cloudapp.azure.com'
SERVICES = [('azure', 'Azure'), ('stripe', 'Stripe'), ('supabase', 'Supabase')]
STALE_SECONDS = 150
_refresh_lock = threading.Lock()


def read(path):
    try:
        value = json.loads(Path(path).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def validate_report(report):
    if not isinstance(report, dict) or report.get('version') != 1 or not isinstance(report.get('services'), list):
        raise ValueError('Invalid status report')
    fresh = age(report.get('sampled_at'))
    if fresh is None or not -60 <= fresh <= STALE_SECONDS:
        raise ValueError('Stale status report')
    services = report['services']
    if len(services) != 2 or {s.get('id') for s in services} != {'stripe', 'supabase'}:
        raise ValueError('Incomplete service checks')
    for service in services:
        if service.get('status') not in ('healthy', 'error') or age(service.get('checked_at')) is None:
            raise ValueError('Invalid service check')
    transactions = report.get('transactions')
    if transactions is not None:
        days = transactions.get('days')
        if (type(transactions.get('total')) is not int or transactions['total'] < 0
                or not isinstance(days, list) or len(days) != 90 or transactions.get('timezone') != 'America/Los_Angeles'):
            raise ValueError('Invalid purchase totals')
        dates = []
        for day in days:
            dates.append(datetime.strptime(day['date'], '%Y-%m-%d').date())
            if type(day.get('count')) is not int or day['count'] < 0:
                raise ValueError('Invalid daily count')
        if len(set(dates)) != 90 or any((b-a).days != 1 for a,b in zip(dates, dates[1:])):
            raise ValueError('Incomplete daily history')
        if sum(day['count'] for day in days) > transactions['total'] or age(transactions.get('checked_at')) is None:
            raise ValueError('Inconsistent purchase totals')
    return dict(services=[{k:s.get(k) for k in ('id','name','status','detail','checked_at','latency_ms')} for s in services],
                transactions={k:transactions.get(k) for k in ('total','days','last_payment_at','checked_at','timezone')} if transactions else None)


def azure_check(get=requests.get):
    started = time.monotonic()
    try:
        response = get(SERVICE_URL + '/health', timeout=(3, 6), allow_redirects=False)
        if response.status_code != 200:
            raise ValueError('Health check failed')
        payload = response.json()
        if payload.get('ok') is not True or payload.get('mode') != 'live':
            raise ValueError('Service is not ready')
        result = dict(status='healthy', detail='Credit service responding')
    except (requests.RequestException, ValueError, AttributeError):
        result = dict(status='offline', detail='Credit service is unreachable')
    return dict(id='azure', name='Azure', checked_at=datetime.now(timezone.utc).isoformat(),
                latency_ms=round((time.monotonic()-started)*1000), **result)


def cloud_report(config, runner=subprocess.run):
    command = ['ssh', '-i', config['key_path'], '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
               '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + config['known_hosts'],
               config['host'], 'status']
    result = runner(command, capture_output=True, text=True, timeout=35)
    if result.returncode or len(result.stdout) > 65536:
        raise ValueError('Status reader did not respond')
    return validate_report(json.loads(result.stdout))


def collect(config, state_dir, runner=subprocess.run, get=requests.get):
    import fcntl
    directory = Path(state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.zebby-collector.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return read(directory / 'zebby.json')
        previous = read(directory / 'zebby.json')
        with ThreadPoolExecutor(max_workers=2) as pool:
            azure = pool.submit(azure_check, get)
            cloud = pool.submit(cloud_report, config, runner)
            try:
                result = cloud.result()
            except Exception:
                result = dict(services=[dict(id=i, name=n, status='unknown', detail='Cannot reach the Azure status reader',
                                           checked_at=datetime.now(timezone.utc).isoformat()) for i,n in SERVICES[1:]], transactions=None)
            transactions = result.get('transactions') or previous.get('transactions')
            report = dict(sampled_at=datetime.now(timezone.utc).isoformat(), services=[azure.result(), *result['services']],
                          transactions=transactions, transactions_current=result.get('transactions') is not None)
        target = directory / 'zebby.json'
        temporary = directory / 'zebby.json.tmp'
        temporary.write_text(json.dumps(report))
        temporary.chmod(0o600)
        temporary.replace(target)
        return report


def status(state_dir):
    report = read(Path(state_dir) / 'zebby.json')
    stale = age(report.get('sampled_at'))
    fresh = stale is not None and -60 <= stale <= STALE_SECONDS
    checks = report.get('services') or [dict(id=i, name=n, status='unknown', detail='Waiting for the first check') for i,n in SERVICES]
    services = [{**s} for s in checks]
    if not fresh:
        for service in services:
            service.update(status='unknown', detail='Status is stale' if report else 'Waiting for the first check')
    state = aggregate([s['status'] for s in services])
    summary = 'All services are responding' if state == 'healthy' else 'A service needs attention'
    if not fresh:
        summary = 'Status updates have stopped' if report else 'Waiting for the first service check'
    transactions = report.get('transactions')
    transaction_age = age((transactions or {}).get('checked_at'))
    current = fresh and report.get('transactions_current') is True and transaction_age is not None and -60 <= transaction_age <= STALE_SECONDS
    return dict(status=state, summary=summary, connected=fresh, checked_at=report.get('sampled_at'),
                data=dict(services=services, transactions=transactions, transactions_stale=bool(transactions) and not current),
                metrics=[dict(label='Successful purchases', value=transactions['total'])] if transactions else [])


def start_refresh(config, state_dir):
    if not config.get('key_path'):
        raise ValueError('Connect the Zebby status reader first.')
    if not _refresh_lock.acquire(blocking=False):
        return
    def run():
        try:
            collect(config, state_dir)
        finally:
            _refresh_lock.release()
    threading.Thread(target=run, name='zebby-refresh', daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    config = read(args.state_dir / 'config.json').get('zebby', {})
    if not config.get('key_path'):
        raise SystemExit('Configure the Zebby status reader first.')
    report = collect(config, args.state_dir)
    print(json.dumps({'checked_at': report.get('sampled_at'), 'services': {s['id']:s['status'] for s in report.get('services', [])}}))


if __name__ == '__main__':
    main()
