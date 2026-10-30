"""Publish Reddit and Shambu status. Never submits appeals or runs inference."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import tomllib
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler


def build_report(project, codex_home):
    spec = importlib.util.spec_from_file_location('ronhub_appeal_log', project / 'appeal_log.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = json.loads((project / 'config.json').read_text(encoding='utf-8-sig'))
    log = module.AppealLog(config)
    # This is an atomic append ledger. Retry an incomplete last line on the next tick.
    events = log.read_events()
    rows = log.rows(events)
    state = log.health(events)
    automation = codex_home / 'automations' / config['automation_id'] / 'automation.toml'
    status = 'UNKNOWN'
    if automation.exists():
        status = tomllib.loads(automation.read_text(encoding='utf-8')).get('status', 'UNKNOWN')
    return dict(sampled_at=datetime.now(timezone.utc).isoformat(), username=config['username'], records=len(rows), confirmed_submissions=sum(r['status'] == 'success' for r in rows), workflow_state=state, next_scheduled_local=next((e['scheduled_for'] for e in reversed(events) if e['kind'] == 'schedule'), None), automation_status=status, history=list(reversed(rows))[:30], last_record=rows[-1] if rows else None, resolved=any(r['status'] == 'resolved' for r in rows), window='03:00-06:00 America/Los_Angeles')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    next_reddit = 0
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None
    opener = build_opener(NoRedirect)
    def publish(kind, report):
        req = Request(config['url'].rstrip('/') + '/hub/api/reports/' + kind, data=json.dumps(report).encode(), headers={'Content-Type':'application/json','Authorization':'Bearer ' + config['report_key']}, method='POST')
        with opener.open(req, timeout=15) as response:
            if response.status != 200:
                raise RuntimeError('Status report rejected')
    while True:
        try:
            if time.monotonic() >= next_reddit:
                publish('reddit', build_report(Path(config['project']), Path(config['codex_home'])))
                next_reddit = time.monotonic() + 60
                if args.once:
                    print('Reddit status received by RonHub.')
        except Exception as error:
            if args.once:
                print('Status bridge failed: ' + type(error).__name__, file=sys.stderr)
                raise SystemExit(1)
        try:
            agent_path = Path(config.get('agent_config', str(Path(os.environ['LOCALAPPDATA']) / 'Shambu' / 'agent' / 'config.json')))
            agent = json.loads(agent_path.read_text(encoding='utf-8'))
            req = Request('http://127.0.0.1:11435/health', headers={'Authorization':'Bearer '+agent['pairingKey']})
            started = time.monotonic()
            with opener.open(req, timeout=8) as response:
                gpu = json.load(response)
            gpu['sampleAgeMs'] += int((time.monotonic() - started) * 1000)
            gpu['sampled_at'] = datetime.now(timezone.utc).isoformat()
            snapshot = gpu.get('snapshot', {})
            history = snapshot.get('gpuHistory')
            if isinstance(history, dict):
                history['burstCount'] = len(history.pop('bursts', []))
            publish('gpu',gpu)
            if args.once:
                print('Shambu status received by RonHub.')
        except Exception as error:
            if args.once:
                print('GPU status bridge failed: ' + type(error).__name__, file=sys.stderr)
                raise SystemExit(1)
        if args.once: break
        time.sleep(5)


if __name__ == '__main__':
    main()
