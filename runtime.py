"""Private, atomic runtime state shared by the web app and job processes."""

from contextlib import contextmanager
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import threading

try:
    import fcntl
except ImportError:  # Windows development; the production host uses flock.
    fcntl = None

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / 'controllers' / 'data'
CONFIG_PATH = ROOT / 'config.json'
_locks = {}
_locks_guard = threading.Lock()


@contextmanager
def file_lock(path, *, blocking=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with _locks_guard:
        lock = _locks.setdefault(str(path.resolve()), threading.RLock())
    acquired = lock.acquire(blocking=blocking)
    if not acquired:
        raise BlockingIOError('This operation is already running.')
    try:
        with path.open('a+', encoding='utf-8') as handle:
            os.chmod(path, 0o600)
            if fcntl:
                flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
                fcntl.flock(handle.fileno(), flags)
            try:
                yield
            finally:
                if fcntl:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        lock.release()


def read_json(path, default=None):
    try:
        with Path(path).open(encoding='utf-8') as handle:
            return json.load(handle)
    except FileNotFoundError:
        return copy.deepcopy(default)


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def update_json(path, mutate, default=None):
    with file_lock(str(path) + '.lock'):
        data = read_json(path, default)
        mutate(data)
        atomic_json(path, data)
        return data


def redact(text, config=None):
    text = str(text)
    def visit(value):
        nonlocal text
        if isinstance(value, dict):
            for key, item in value.items():
                if re.search(r'secret|token|auth_key|api_key|password|private_key', key, re.I):
                    if isinstance(item, str) and len(item) >= 4:
                        text = text.replace(item, '[redacted]')
                elif isinstance(item, dict):
                    visit(item)
    visit(config or {})
    text = re.sub(r'(?i)(access_token|refresh_token|auth_key|client_secret|api_key)=([^&\s]+)', r'\1=[redacted]', text)
    return text.replace('\u2014', '-')


class JobSkipped(RuntimeError):
    """A valid response left no applicable data to publish."""


def updated_label(now):
    hour = now.hour % 12 or 12
    clock = f'{hour}:{now.minute:02d}' if now.minute else str(hour)
    return f"Last updated: {now.strftime('%b')} {now.day}, {clock} {'AM' if now.hour < 12 else 'PM'}"
