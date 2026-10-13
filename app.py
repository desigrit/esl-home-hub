import json
import os
import time
import threading
import datetime
import sys
import hmac
import subprocess
import copy
from runtime import ROOT, STATE_DIR, CONFIG_PATH, atomic_json, read_json, file_lock, redact
from scheduling import CalendarDaysTrigger
from flask import Flask, jsonify, render_template, request, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler

from todo_service import (
    MicrosoftTodoService,
    TodoAuthenticationRequired,
    TodoConfigurationError,
    TodoGraphError,
    build_todo_api_payload,
    build_todo_view,
)

app = Flask(__name__)
CONFIG_FILE = CONFIG_PATH
LOG_FILE = ROOT / 'logs.json'
_job_locks = {name: threading.Lock() for name in ('dota', 'weather', 'fitness', 'energy', 'f1', 'family', 'todo', 'WebScraper')}
_active_jobs = {}
_active_lock = threading.Lock()
_schedule_lock = threading.Lock()
JOB_NAMES = ('dota', 'weather', 'fitness', 'energy', 'f1', 'family', 'todo', 'WebScraper')

# --- CONFIG & LOGGING ---
def load_config():
    defaults = {
        'WebScraper': {'enabled': False, 'mode': 'schedule', 'interval': 180, 'times': ['06:05', '09:05', '12:05', '15:05', '18:05', '21:05'], 'days': 1},
        "dota":    {"enabled": False, "mode": "interval", "interval": 15, "times": ["08:00"], "days": 1},
        "weather": {"enabled": False, "mode": "interval", "interval": 30, "times": ["10:00", "14:00"], "days": 1},
        "fitness": {"enabled": False, "mode": "interval", "interval": 60, "times": ["22:00"], "days": 1},
        "energy":  {"enabled": False, "mode": "interval", "interval": 60, "times": ["08:00"], "days": 3},
        "f1":      {"enabled": False, "mode": "interval", "interval": 1440, "times": ["12:00"], "days": 1},
        "family":  {"enabled": False, "mode": "schedule", "interval": 60, "times": ["05:00", "12:00", "18:00"], "days": 1},
        "todo":    {"enabled": False, "tag_id": "", "layout_id": "4p20c_Todo", "client_id": "", "tenant_id": "consumers", "token_cache_path": "controllers/data/microsoft_todo_token_cache.json", "cache_seconds": 30, "task_concurrency": 4, "request_timeout_seconds": 15, "api_key": "", "max_lists": 8, "max_tasks": 6, "focus_list_index": 0, "display_mode": "overview", "mode": "schedule", "interval": 60, "times": ["06:00", "12:00", "18:00"], "days": 1},
        "system":  {"gateway_ip": "192.168.220.206", "store_code": ""}
    }
    
    if not os.path.exists(CONFIG_FILE): return defaults
    
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    for key, val in defaults.items():
        if key not in data: data[key] = val
        else:
            for k, v in val.items():
                if k not in data[key]: data[key][k] = v
    return data

def save_config(data):
    atomic_json(CONFIG_FILE, data)

def load_logs():
    logs = read_json(LOG_FILE, {})
    if not isinstance(logs, dict):
        raise ValueError('Run history is not a JSON object.')
    for name in JOB_NAMES:
        logs.setdefault(name, [])
    for entries in logs.values():
        for i, entry in enumerate(entries):
            if isinstance(entry, str):
                entries[i] = {'time': entry, 'status': 'Legacy', 'output': 'No details available.'}
            elif entry.get('status') == 'Success' and not entry.get('finished_at'):
                entries[i] = {**entry, 'status': 'Unverified', 'original_status': 'Success'}
    return logs

def log_run(job_name, status, output, **metadata):
    with file_lock(str(LOG_FILE) + '.lock'):
        logs = load_logs()
        timestamp = datetime.datetime.now().astimezone()
        entry = {'time': timestamp.strftime('%I:%M %p, %b %d'), 'status': status,
                 'output': output[-24000:], 'finished_at': timestamp.isoformat(), **metadata}
        logs.setdefault(job_name, []).insert(0, entry)
        logs[job_name] = logs[job_name][:10]
        atomic_json(LOG_FILE, logs)

# --- JOB WRAPPERS ---
def run_job(name, func=None, force=False):
    if name not in _job_locks:
        raise ValueError('Unknown job.')
    if not _job_locks[name].acquire(blocking=False):
        return False
    started = datetime.datetime.now().astimezone()
    monotonic_start = time.monotonic()
    cfg = {}
    status = 'Failed'
    output = ''
    try:
        cfg = load_config()
        if not force and not cfg.get(name, {}).get('enabled'):
            return False
        with _active_lock:
            _active_jobs[name] = started.isoformat()
        trigger = 'Manual' if force else 'Scheduled'
        output = f'{trigger} Job: {name.capitalize()}\n'
        limit = max(30, min(900, int(cfg.get('system', {}).get('job_timeout_seconds', 300))))
        result = subprocess.run(
            [sys.executable, '-u', str(ROOT / 'job_worker.py'), name],
            input=json.dumps(cfg), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', cwd=ROOT, timeout=limit,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
        )
        output += result.stdout
        status = {0: 'Success', 2: 'Pending', 3: 'Skipped'}.get(result.returncode, 'Failed')
    except subprocess.TimeoutExpired as error:
        partial = error.stdout or ''
        if isinstance(partial, bytes):
            partial = partial.decode('utf-8', 'replace')
        output += partial + '\nJob timed out. Delivery is unconfirmed; the job will retry on its next schedule.'
    except Exception as error:
        output += f'Job failed: {error}'
    finally:
        try:
            if output:
                output = redact(output, cfg)
                log_run(name, status, output, started_at=started.isoformat(),
                        duration_seconds=round(time.monotonic() - monotonic_start, 2), trigger='manual' if force else 'scheduled')
                print(output, end='' if output.endswith('\n') else '\n', flush=True)
        finally:
            with _active_lock:
                _active_jobs.pop(name, None)
            _job_locks[name].release()
    return True

# --- SCHEDULING LOGIC ---
def reschedule_all():
    with _schedule_lock:
        cfg = load_config()
        anchors_path = STATE_DIR / 'schedule_anchors.json'
        anchors = read_json(anchors_path, {})
        now = datetime.datetime.now().astimezone(scheduler.timezone)
        logs = load_logs()
        planned = []
        for name in JOB_NAMES:
            settings = cfg.get(name, {})
            if not settings.get('enabled'):
                continue
            if settings.get('mode') == 'interval':
                minutes = int(settings.get('interval', 30))
                if minutes < 1:
                    raise ValueError(f'{name}: interval must be positive.')
                planned.append((f'{name}_interval', name, 'interval', {'minutes': minutes}))
                continue
            days = int(settings.get('days', 1))
            times = sorted(set(settings.get('times', [])))
            if not times or days < 1:
                raise ValueError(f'{name}: choose a positive day interval and at least one time.')
            signature = json.dumps([days, times])
            previous = anchors.get(name, {})
            if previous.get('signature') == signature:
                anchor = previous['anchor']
            else:
                anchor = now.date().isoformat()
                # Seed multi-day schedules from their last scheduled run when
                # upgrading an installation that did not persist its anchor.
                if name not in anchors and days > 1:
                    for entry in logs.get(name, []):
                        if 'Scheduled Job:' in entry.get('output', ''):
                            try:
                                last = datetime.datetime.strptime(entry['time'], '%I:%M %p, %b %d').replace(year=now.year)
                                if last.date() > now.date():
                                    last = last.replace(year=now.year - 1)
                                anchor = last.date().isoformat()
                                break
                            except (KeyError, ValueError):
                                pass
                anchors[name] = {'signature': signature, 'anchor': anchor}
            for clock in times:
                h, m = map(int, clock.split(':'))
                trigger = CalendarDaysTrigger(days=days, hour=h, minute=m, anchor=anchor, timezone=scheduler.timezone)
                planned.append((f'{name}_{clock}', name, trigger, {}))
        # Validate every schedule before replacing any working jobs.
        atomic_json(anchors_path, anchors)
        scheduler.remove_all_jobs()
        for job_id, name, trigger, options in planned:
            scheduler.add_job(run_job, trigger, args=[name, None, False], id=job_id,
                              coalesce=True, max_instances=1, misfire_grace_time=3600, **options)
        print(f'Scheduled {len(planned)} updates.', flush=True)

# --- INIT SCHEDULER ---
scheduler = BackgroundScheduler()

# --- WEB ROUTES ---
@app.route('/')
def index():
    return render_template('index.html', config=load_config(), logs=load_logs())


_todo_service = None
_todo_service_key = None
_todo_service_lock = threading.Lock()


def get_todo_service(config):
    global _todo_service, _todo_service_key
    todo_config = config.get('todo', {})
    service_key = json.dumps(todo_config, sort_keys=True)

    with _todo_service_lock:
        if _todo_service is None or service_key != _todo_service_key:
            _todo_service = MicrosoftTodoService(todo_config)
            _todo_service_key = service_key
        return _todo_service


def no_store_json(payload, status=200, retry_after=None):
    response = jsonify(payload)
    response.status_code = status
    response.headers['Cache-Control'] = 'no-store'
    if retry_after:
        response.headers['Retry-After'] = retry_after
    return response


@app.after_request
def protect_todo_responses(response):
    if request.path == '/todo' or request.path.startswith('/todo/') or request.path == '/api/todo':
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


def get_todo_render_context(config, *, force_refresh=False):
    try:
        snapshot = get_todo_service(config).get_snapshot(force=force_refresh)
        return (dict(
            state='ready',
            todo=build_todo_view(snapshot),
        ), 200)
    except TodoConfigurationError as error:
        return (dict(
            state='configuration_required',
            state_title='Connect Microsoft To Do',
            state_message=str(error),
            todo=None,
        ), 200)
    except TodoAuthenticationRequired as error:
        return (dict(
            state='authentication_required',
            state_title='Sign in to Microsoft',
            state_message=str(error),
            todo=None,
        ), 200)
    except TodoGraphError as error:
        app.logger.warning(
            'Microsoft Graph request failed: status=%s code=%s request_id=%s',
            error.status,
            error.code,
            error.request_id,
        )
        return (dict(
            state='upstream_error',
            state_title='Microsoft To Do is unavailable',
            state_message='RonHub could not load your tasks. Try again in a moment.',
            todo=None,
        ), 502)
    except Exception:
        app.logger.exception('Unexpected Microsoft To Do page failure')
        return (dict(
            state='upstream_error',
            state_title='Microsoft To Do is unavailable',
            state_message='RonHub could not load your tasks. Try again in a moment.',
            todo=None,
        ), 502)


@app.route('/todo')
def todo_page():
    query = {'tab': 'todo'}
    if request.args.get('refresh') == '1':
        query['todo_refresh'] = '1'
    return redirect(url_for('index', **query))


@app.route('/todo/fragment')
def todo_fragment():
    context, status = get_todo_render_context(
        load_config(),
        force_refresh=request.args.get('refresh') == '1',
    )
    return render_template('_todo_panel.html', **context), status


@app.route('/api/todo')
def todo_api():
    config = load_config()
    todo_config = config.get('todo', {})
    expected_key = str(todo_config.get('api_key', '')).strip()
    supplied_key = request.headers.get('X-API-Key', '')

    if not expected_key:
        return no_store_json({
            'error': 'configuration_required',
            'message': 'Set todo.api_key before using this endpoint.',
        }, 503)

    if not hmac.compare_digest(
        supplied_key.encode('utf-8'), expected_key.encode('utf-8')
    ):
        return no_store_json({
            'error': 'unauthorized',
            'message': 'A valid X-API-Key header is required.',
        }, 401)

    try:
        snapshot = get_todo_service(config).get_snapshot(
            force=request.args.get('refresh') == '1'
        )
        return no_store_json(build_todo_api_payload(snapshot))
    except TodoConfigurationError:
        return no_store_json({
            'error': 'configuration_required',
            'message': 'Microsoft To Do has not been configured.',
        }, 503)
    except TodoAuthenticationRequired:
        return no_store_json({
            'error': 'authentication_required',
            'message': 'Run python3 todo_auth.py on the Raspberry Pi.',
        }, 503)
    except TodoGraphError as error:
        app.logger.warning(
            'Microsoft Graph request failed: status=%s code=%s request_id=%s',
            error.status,
            error.code,
            error.request_id,
        )
        return no_store_json({
            'error': 'microsoft_graph_error',
            'message': 'Microsoft Graph could not return the To Do data.',
        }, 503 if error.status in (429, 503) else 502, error.retry_after)
    except Exception:
        app.logger.exception('Unexpected Microsoft To Do API failure')
        return no_store_json({
            'error': 'todo_service_error',
            'message': 'Microsoft To Do is temporarily unavailable.',
        }, 502)

@app.route('/update', methods=['POST'])
def update_settings():
    try:
        with file_lock(str(CONFIG_FILE) + '.lock'):
            return _update_settings()
    except (TypeError, ValueError) as error:
        return jsonify({'error': str(error)}), 400

def _update_settings():
    config = copy.deepcopy(load_config())
    form = request.form
    
    def process_tab(key):
        # A settings form rendered before this job's tab existed carries none of
        # its fields. Without this guard such a save would read the checkbox as
        # absent, set enabled to False and blank the schedule, silently stopping
        # a live job. Every tab's scheduler always posts a mode radio.
        if f'{key}_mode' not in form:
            return
        config[key]['enabled'] = f'{key}_enabled' in form
        config[key]['mode'] = form.get(f'{key}_mode', 'interval')
        config[key]['interval'] = int(form.get(f'{key}_interval', 30))
        config[key]['days'] = int(form.get(f'{key}_days', 1))
        config[key]['times'] = [t for t in form.getlist(f'{key}_times[]') if t]

    process_tab('dota')
    process_tab('weather')
    process_tab('fitness')
    process_tab('energy')
    process_tab('f1')
    process_tab('family')
    process_tab('todo')
    process_tab('WebScraper')

    if 'sys_gateway_ip' in form:
        config['system']['gateway_ip'] = form.get('sys_gateway_ip')
        config['system']['store_code'] = form.get('sys_store_code')
    
    # Same guard as above. These were unconditional, so a form that did not carry
    # them nulled real credentials, including Strava's rotating refresh token.
    if 'dota_steam_id' in form:
        config['dota']['steam_id'] = form.get('dota_steam_id')
        config['dota']['baseline_mmr'] = int(form.get('dota_baseline_mmr') or 0)
        config['dota']['target_mmr'] = int(form.get('dota_target_mmr') or 0)
        config['dota']['baseline_match_id'] = int(form.get('dota_baseline_match_id') or 0)

    if 'fit_client_id' in form:
        config['fitness']['client_id'] = form.get('fit_client_id')
        for field, key in (('fit_client_secret', 'client_secret'), ('fit_refresh_token_new', 'refresh_token')):
            if form.get(field, '').strip():
                config['fitness'][key] = form[field].strip()

    if 'energy_auth_key' in form:
        if form.get('energy_auth_key', '').strip():
            config['energy']['auth_key'] = form['energy_auth_key'].strip()
        config['energy']['device_id'] = form.get('energy_device_id')
        config['energy']['cost_per_kwh'] = float(form.get('energy_cost') or 0)

    if 'todo_tag_id' in form:
        config['todo']['tag_id'] = form.get('todo_tag_id', '').strip()
        config['todo']['layout_id'] = (
            form.get('todo_layout_id', '').strip() or '4p20c_Todo'
        )

    validate_config(config)
    save_config(config)
    reschedule_all()
    return redirect(url_for('index'))

@app.route('/trigger/<job_name>', methods=['GET', 'POST'])
def trigger_job(job_name):
    if job_name not in JOB_NAMES:
        return jsonify({'error': 'Unknown job.'}), 404
    with _active_lock:
        if job_name in _active_jobs:
            if request.method == 'POST':
                return jsonify({'status': 'Running', 'job': job_name}), 202
            return redirect(url_for('index'))
        _active_jobs[job_name] = datetime.datetime.now().astimezone().isoformat()
    threading.Thread(target=run_job, args=(job_name, None, True), daemon=True).start()
    if request.method == 'POST':
        return jsonify({'status': 'Running', 'job': job_name}), 202
    return redirect(url_for('index'))


def validate_config(config):
    for name in JOB_NAMES:
        item = config.get(name, {})
        if int(item.get('interval', 30)) < 1 or int(item.get('days', 1)) < 1:
            raise ValueError(f'{name}: interval and days must be at least 1.')
        if item.get('mode') not in ('interval', 'schedule'):
            raise ValueError(f'{name}: invalid schedule mode.')
        for clock in item.get('times', []):
            datetime.datetime.strptime(clock, '%H:%M')
        if item.get('enabled') and item.get('mode') == 'schedule' and not item.get('times'):
            raise ValueError(f'{name}: choose at least one update time.')
    system = config.get('system', {})
    if not str(system.get('gateway_ip', '')).strip() or not str(system.get('store_code', '')).strip():
        raise ValueError('Gateway address and store code are required.')


@app.route('/api/status')
def system_status():
    config = load_config()
    logs = load_logs()
    with _active_lock:
        active = dict(_active_jobs)
    jobs = {}
    for name in JOB_NAMES:
        entries = logs.get(name, [])
        next_times = [job.next_run_time.isoformat() for job in scheduler.get_jobs()
                      if job.id.startswith(name + '_') and getattr(job, 'next_run_time', None)]
        jobs[name] = {'enabled': config.get(name, {}).get('enabled', False),
                      'running': name in active, 'started_at': active.get(name),
                      'next_run': min(next_times) if next_times else None,
                      'logs': entries}
    return no_store_json({'scheduler_running': scheduler.running, 'jobs': jobs})


@app.route('/healthz')
def healthz():
    try:
        validate_config(load_config())
        load_logs()
        ready = scheduler.running
        return no_store_json({'status': 'ok' if ready else 'scheduler_stopped'}, 200 if ready else 503)
    except (OSError, ValueError, TypeError):
        return no_store_json({'status': 'invalid_runtime_state'}, 503)

if __name__ == '__main__':
    if os.environ.get('ESL_HUB_DISABLE_SCHEDULER') != '1':
        reschedule_all()
        scheduler.start()
    app.run(host='0.0.0.0', port=5000, debug=False)
