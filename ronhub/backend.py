"""Adapters for the live ESL runtime and a local preview over its existing HTTP API."""
import copy
import hashlib
import json
import re
import threading
from html.parser import HTMLParser
import requests
from .registry import fields_for


class Conflict(ValueError):
    pass


def revision(values):
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def public_settings(config, job):
    fields = fields_for(job)
    values = {}
    for f in fields:
        val = config.get(f['key'])
        if f['type'] == 'password':
            val = bool(val)
        values[f['key']] = val
    return dict(fields=fields, values=values, revision=revision(values))


def validate_values(job, values):
    fields = {f['key']: f for f in fields_for(job)}
    if not isinstance(values, dict) or set(values) - set(fields):
        raise ValueError('Settings contain an unsupported field.')
    result = {}
    for key, value in values.items():
        f = fields[key]
        kind = f['type']
        if kind == 'password' and value == '':
            continue
        if kind == 'checkbox':
            if not isinstance(value, bool):
                raise ValueError('Choose whether scheduled updates are enabled.')
        elif kind == 'number':
            try:
                value = float(value) if f.get('step') else int(value)
            except (ValueError, TypeError, OverflowError):
                raise ValueError(f"{f['label']} must be a number.")
            import math
            if not math.isfinite(value) or value < f.get('min', 0) or value > f.get('max', 10**18):
                raise ValueError(f"{f['label']} is outside the allowed range.")
        elif kind == 'times':
            if not isinstance(value, list) or len(value) > 48 or any(not isinstance(t, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', t) for t in value):
                raise ValueError('Use valid update times, such as 08:00.')
            value = sorted(set(value))
        else:
            if not isinstance(value, str) or len(value) > 2048:
                raise ValueError(f"Enter a valid {f['label'].lower()}.")
            value = value.strip()
            if f.get('required') and not value:
                raise ValueError(f"{f['label']} is required.")
            if kind == 'select' and value not in [x[0] for x in f['options']]:
                raise ValueError('Choose a valid schedule mode.')
        result[key] = value
    return result


class NativeBackend:
    def __init__(self, app, runtime):
        self.app, self.runtime = app, runtime

    def status(self):
        with self.app.app_context():
            return self.runtime['system_status']().get_json()

    def settings(self, job):
        return public_settings(self.runtime['load_config']().get(job, {}), job)

    def save(self, job, values, expected):
        patch = validate_values(job, values)
        rt = self.runtime
        with rt['file_lock'](str(rt['CONFIG_FILE']) + '.lock'):
            cfg = copy.deepcopy(rt['load_config']())
            current = public_settings(cfg.get(job, {}), job)
            if current['revision'] != expected:
                raise Conflict('These settings changed in another session. Reload them before saving.')
            cfg.setdefault(job, {}).update(patch)
            rt['validate_config'](cfg)
            rt['save_config'](cfg)
            rt['reschedule_all']()
        return self.settings(job)

    def trigger(self, job):
        if job not in self.runtime['JOB_NAMES']:
            raise KeyError(job)
        with self.app.test_request_context('/trigger/' + job, method='POST'):
            response = self.runtime['trigger_job'](job)
            if isinstance(response, tuple):
                response = response[0]
            return response.get_json()


class InputParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag != 'input' or not a.get('name'):
            return
        key = a['name']
        if a.get('type') in ('radio', 'checkbox') and 'checked' not in a:
            return
        self.values.setdefault(key, []).append(a.get('value', 'on'))


class RemoteBackend:
    def __init__(self, base):
        self.base = base.rstrip('/')
        self.lock = threading.Lock()

    def status(self):
        response = requests.get(self.base + '/api/status', timeout=8)
        response.raise_for_status()
        return response.json()

    def settings(self, job):
        response = requests.get(self.base + '/legacy', timeout=10)
        if response.status_code == 404:
            response = requests.get(self.base + '/', timeout=10)
        response.raise_for_status()
        parser = InputParser()
        parser.feed(response.text)
        values = {}
        for f in fields_for(job):
            name = f.get('form', job + '_' + f['key']) + ('[]' if f['type'] == 'times' else '')
            value = parser.values.get(name, [])
            values[f['key']] = (name in parser.values if f['type'] == 'checkbox' else value if f['type'] == 'times' else value[0] if value else '')
            if f['type'] == 'password':
                values[f['key']] = True
            if f['type'] == 'number' and values[f['key']] != '':
                values[f['key']] = float(values[f['key']]) if f.get('step') else int(values[f['key']])
        return public_settings(values, job)

    def save(self, job, values, expected):
        patch = validate_values(job, values)
        with self.lock:
            current = self.settings(job)
            if expected != current['revision']:
                raise Conflict('These settings changed. Reload them before saving.')
            merged = {**current['values'], **patch}
            data = []
            for f in fields_for(job):
                key, kind = f['key'], f['type']
                name = f.get('form', job + '_' + key)
                if kind == 'password':
                    value = patch.get(key, '')
                else:
                    value = merged[key]
                if kind == 'checkbox':
                    if value:
                        data.append((name, 'on'))
                elif kind == 'times':
                    data.extend((name + '[]', t) for t in value)
                else:
                    data.append((name, str(value)))
            response = requests.post(self.base + '/update', data=data, timeout=15, allow_redirects=False)
            if response.status_code not in (200, 302, 303):
                raise ValueError(response.json().get('error', 'The settings could not be saved.'))
        return self.settings(job)

    def trigger(self, job):
        fields_for(job)
        response = requests.post(self.base + '/trigger/' + job, timeout=12)
        response.raise_for_status()
        return response.json()
