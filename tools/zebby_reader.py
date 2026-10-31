#!/usr/bin/python3
"""Restricted Azure reader. Emits health and aggregate live purchases only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shlex
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo('America/Los_Angeles')
MAX_PAGES = 20
PAGE_SIZE = 500


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def get_json(url, headers=None):
    """GET only, with bounded responses and no credential-bearing redirects."""
    request = Request(url, headers={'Accept': 'application/json', **(headers or {})}, method='GET')
    with build_opener(NoRedirect).open(request, timeout=6) as response:
        body = response.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            raise ValueError('Response too large')
        return json.loads(body)


def environment(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        parts = shlex.split(value, comments=False)
        values[key.strip()] = parts[0] if len(parts) == 1 else value.strip()
    return values


def rows(base, key, table, query, fetch=get_json):
    headers = {'apikey': key}
    if key.startswith('eyJ'):
        headers['Authorization'] = 'Bearer ' + key
    result = []
    for page in range(MAX_PAGES):
        data = fetch(f'{base}/rest/v1/{table}?{query}&limit={PAGE_SIZE}&offset={page * PAGE_SIZE}', headers)
        if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
            raise ValueError('Invalid database response')
        result.extend(data)
        if len(data) < PAGE_SIZE:
            return result
    raise ValueError('Report limit reached')


def purchase_counts(purchases, entries, now):
    """Use the unique credited purchase and its settlement time, not checkout creation."""
    paid = {p['id'] for p in purchases}
    settled = {}
    for entry in entries:
        reference = entry.get('reference')
        if reference not in paid or reference in settled:
            continue
        stamp = datetime.fromisoformat(entry['created_at'].replace('Z', '+00:00'))
        if stamp.tzinfo is None or stamp > now + timedelta(minutes=1):
            raise ValueError('Invalid purchase timestamp')
        settled[reference] = stamp
    if set(settled) != paid:
        raise ValueError('A paid purchase has no settlement record')
    today = now.astimezone(PACIFIC).date()
    counts = {(today - timedelta(days=i)).isoformat(): 0 for i in reversed(range(90))}
    for stamp in settled.values():
        day = stamp.astimezone(PACIFIC).date().isoformat()
        if day in counts:
            counts[day] += 1
    return dict(total=len(paid), days=[dict(date=day, count=count) for day, count in counts.items()],
                last_payment_at=max(settled.values()).isoformat() if settled else None,
                checked_at=now.isoformat(), timezone='America/Los_Angeles')


def problem(error):
    if isinstance(error, HTTPError):
        if error.code in (401, 403):
            return 'Access needs attention'
        if error.code == 429:
            return 'Rate limited. Retrying shortly'
        return 'Service returned an error'
    return 'Check did not complete'


def check_stripe(config, fetch=get_json):
    started = time.monotonic()
    try:
        key = config['STRIPE_SECRET_KEY']
        if not key.startswith(('sk_live_', 'rk_live_')):
            raise ValueError('Live service key required')
        data = fetch('https://api.stripe.com/v1/checkout/sessions?limit=1', {'Authorization': 'Bearer ' + key})
        if data.get('object') != 'list' or not isinstance(data.get('data'), list):
            raise ValueError('Invalid checkout response')
        result = dict(status='healthy', detail='Checkout API responding')
    except Exception as error:
        result = dict(status='error', detail=problem(error))
    return dict(id='stripe', name='Stripe', checked_at=datetime.now(timezone.utc).isoformat(),
                latency_ms=round((time.monotonic() - started) * 1000), **result)


def check_supabase(config, fetch=get_json, now=None):
    started = time.monotonic()
    now = now or datetime.now(timezone.utc)
    transactions = None
    try:
        base = config['SUPABASE_URL'].rstrip('/')
        url = urlsplit(base)
        if url.scheme != 'https' or not url.hostname.endswith('.supabase.co') or url.username or url.port:
            raise ValueError('Invalid database origin')
        key = config['SUPABASE_SERVICE_ROLE_KEY']
        purchases = rows(base, key, 'zebby_purchases', 'select=id&paid=eq.true&session_id=like.cs_live_*&order=id.asc', fetch)
        entries = rows(base, key, 'zebby_ledger', 'select=reference,created_at&kind=eq.purchase&order=id.asc', fetch)
        transactions = purchase_counts(purchases, entries, now)
        result = dict(status='healthy', detail='Purchase ledger accessible')
    except Exception as error:
        result = dict(status='error', detail=problem(error))
    return dict(id='supabase', name='Supabase', checked_at=now.isoformat(),
                latency_ms=round((time.monotonic() - started) * 1000), **result), transactions


def report(config):
    with ThreadPoolExecutor(max_workers=2) as pool:
        stripe = pool.submit(check_stripe, config)
        database, transactions = pool.submit(check_supabase, config).result()
        return dict(version=1, sampled_at=datetime.now(timezone.utc).isoformat(),
                    services=[stripe.result(), database], transactions=transactions)


if __name__ == '__main__':
    import signal
    signal.alarm(30)
    if len(sys.argv) != 1:
        raise SystemExit('This reader accepts no arguments.')
    try:
        config = environment('/etc/zebby/credits.env')
        print(json.dumps(report(config), separators=(',', ':')))
    except Exception:
        print(json.dumps({'error': 'The Zebby status reader is not configured.'}))
        raise SystemExit(1)
