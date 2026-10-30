"""Install RonHub into the existing ESL app, preserving a rollback snapshot."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('/home/ronhub/esl_hub'))
    parser.add_argument('--expected-app-sha256', required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    app = root / 'app.py'
    original = app.read_bytes()
    if hashlib.sha256(original).hexdigest() != args.expected_app_sha256.lower():
        raise SystemExit('The live app changed. Review it before deploying.')
    with urlopen('http://127.0.0.1:5000/api/status', timeout=10) as response:
        status = json.load(response)
    if any(job.get('running') for job in status['jobs'].values()):
        raise SystemExit('An ESL update is running. Deploy after it completes.')
    source = Path(__file__).resolve().parents[1] / 'ronhub'
    text = original.decode('utf-8')
    marker = "if __name__ == '__main__':\n"
    hook = "    from ronhub import install\n    install(app, globals())\n"
    if hook not in text:
        if text.count(marker) != 1:
            raise SystemExit('The app entry point needs manual review.')
        text = text.replace(marker, marker + hook)
    compile(text, str(app), 'exec')
    for module in source.rglob('*.py'):
        compile(module.read_text(encoding='utf-8'), str(module), 'exec')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = root / '.runtime' / 'ronhub' / 'backups' / stamp
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(app, backup / 'app.py')
    (backup / 'schedule-before.json').write_text(json.dumps({k: {f: v.get(f) for f in ('enabled', 'next_run')} for k,v in status['jobs'].items()}, indent=2))
    current = root / 'ronhub'
    if current.exists():
        shutil.copytree(current, backup / 'ronhub', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    staging = root / ('.ronhub-staging-' + stamp)
    shutil.copytree(source, staging, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    if current.exists():
        current.rename(backup / 'previous-module')
    staging.rename(current)
    temp = app.with_suffix('.ronhub-new.py')
    temp.write_text(text, encoding='utf-8')
    shutil.copymode(app, temp)
    temp.replace(app)
    exclude = root / '.git' / 'info' / 'exclude'
    if exclude.is_file():
        existing = exclude.read_text()
        if '.runtime/ronhub/' not in existing.splitlines():
            with exclude.open('a') as file:
                file.write('\n.runtime/ronhub/\n')
    print(json.dumps({'installed': str(current), 'backup': str(backup), 'restart': 'sudo systemctl restart esl_hub'}))


if __name__ == '__main__':
    main()
