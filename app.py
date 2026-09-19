import json
import os
import time
import threading
import datetime
import io
import contextlib
import sys
import hmac
from flask import Flask, jsonify, render_template, request, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler

# Import your controllers
from controllers import dota_controller, weather_controller, strava_controller, energy_controller, f1_controller, family_controller
from todo_service import (
    MicrosoftTodoService,
    TodoAuthenticationRequired,
    TodoConfigurationError,
    TodoGraphError,
    build_todo_api_payload,
    build_todo_view,
)

app = Flask(__name__)
CONFIG_FILE = 'config.json'
LOG_FILE = 'logs.json'

# --- CONFIG & LOGGING ---
def load_config():
    defaults = {
        "dota":    {"enabled": False, "mode": "interval", "interval": 15, "times": ["08:00"], "days": 1},
        "weather": {"enabled": False, "mode": "interval", "interval": 30, "times": ["10:00", "14:00"], "days": 1},
        "fitness": {"enabled": False, "mode": "interval", "interval": 60, "times": ["22:00"], "days": 1},
        "energy":  {"enabled": False, "mode": "interval", "interval": 60, "times": ["08:00"], "days": 3},
        "f1":      {"enabled": False, "mode": "interval", "interval": 1440, "times": ["12:00"], "days": 1},
        "family":  {"enabled": False, "mode": "schedule", "interval": 60, "times": ["05:00", "12:00", "18:00"], "days": 1},
        "todo":    {"client_id": "", "tenant_id": "consumers", "token_cache_path": "controllers/data/microsoft_todo_token_cache.json", "cache_seconds": 30, "task_concurrency": 4, "request_timeout_seconds": 15, "api_key": ""},
        "system":  {"gateway_ip": "192.168.220.206", "store_code": ""}
    }
    
    if not os.path.exists(CONFIG_FILE): return defaults
    
    with open(CONFIG_FILE, 'r') as f: 
        data = json.load(f)
    
    for key, val in defaults.items():
        if key not in data: data[key] = val
        else:
            for k, v in val.items():
                if k not in data[key]: data[key][k] = v
    return data

def save_config(data):
    with open(CONFIG_FILE, 'w') as f: json.dump(data, f, indent=2)

def load_logs():
    if not os.path.exists(LOG_FILE): 
        return {"dota": [], "weather": [], "fitness": [], "energy": [], "f1": [], "family": []}
    try:
        with open(LOG_FILE, 'r') as f: 
            logs = json.load(f)
            # Migration: If old logs are strings, convert them to dicts
            for k in logs:
                for i, entry in enumerate(logs[k]):
                    if isinstance(entry, str):
                        logs[k][i] = {"time": entry, "status": "Legacy", "output": "No details available."}
            return logs
    except:
        return {"dota": [], "weather": [], "fitness": [], "energy": [], "f1": [], "family": []}

def log_run(job_name, status, output):
    logs = load_logs()
    if job_name not in logs: logs[job_name] = []
    
    timestamp = datetime.datetime.now().strftime("%I:%M %p, %b %d")
    
    entry = {
        "time": timestamp,
        "status": status,
        "output": output
    }
    
    logs[job_name].insert(0, entry)
    logs[job_name] = logs[job_name][:10] # Keep last 10 runs
    
    with open(LOG_FILE, 'w') as f: json.dump(logs, f, indent=2)

# --- JOB WRAPPERS ---
def run_job(name, func, force=False):
    cfg = load_config()
    
    if force or cfg.get(name, {}).get('enabled'):
        trigger_type = "Manual" if force else "Scheduled"
        
        # Capture Stdout/Stderr
        capture_buffer = io.StringIO()
        status = "Success"
        
        # Redirect prints to buffer AND original terminal
        class Tee(object):
            def __init__(self, *files): self.files = files
            def write(self, obj):
                for f in self.files: f.write(obj)
            def flush(self):
                for f in self.files: f.flush()

        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        try:
            # Send output to both capture buffer and real terminal
            sys.stdout = Tee(sys.stdout, capture_buffer)
            sys.stderr = Tee(sys.stderr, capture_buffer)
            
            print(f"⏰ {trigger_type} Job: {name.capitalize()}")
            try:
                func.run(cfg)
            except Exception as e:
                status = "Failed"
                print(f"❌ {name.capitalize()} Job Failed: {e}")
                
        finally:
            # Restore stdout/stderr
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            
        log_run(name, status, capture_buffer.getvalue())
        
    else:
        # Scheduled run but disabled
        pass

# --- SCHEDULING LOGIC ---
def reschedule_all():
    cfg = load_config()
    scheduler.remove_all_jobs()
    
    job_map = {
        'dota': dota_controller,
        'weather': weather_controller,
        'fitness': strava_controller,
        'energy': energy_controller,
        'f1': f1_controller,
        'family': family_controller
    }

    print("🔄 Rescheduling Jobs...")

    for name, controller in job_map.items():
        settings = cfg.get(name, {})
        
        # MODE 1: INTERVAL
        if settings.get('mode') == 'interval':
            minutes = int(settings.get('interval', 30))
            scheduler.add_job(
                run_job, 'interval', minutes=minutes, 
                args=[name, controller, False], id=f"{name}_interval"
            )
            print(f"   -> {name}: Every {minutes} mins")

        # MODE 2: SPECIFIC TIMES
        else:
            days_gap = int(settings.get('days', 1))
            times = settings.get('times', [])
            
            for t_str in times:
                try:
                    h, m = map(int, t_str.split(':'))
                    now = datetime.datetime.now()
                    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    if target <= now:
                        target += datetime.timedelta(days=1)
                    
                    scheduler.add_job(
                        run_job, 'interval', days=days_gap, start_date=target,
                        args=[name, controller, False], id=f"{name}_{t_str}"
                    )
                    print(f"   -> {name}: Every {days_gap} day(s) at {t_str}")

                except Exception as e:
                    print(f"   ⚠️ Invalid time format for {name}: {t_str}")

# --- INIT SCHEDULER ---
scheduler = BackgroundScheduler()
if os.environ.get('ESL_HUB_DISABLE_SCHEDULER') != '1':
    scheduler.start()
    threading.Timer(2.0, reschedule_all).start()

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
    if request.path in ('/todo', '/api/todo'):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.route('/todo')
def todo_page():
    config = load_config()
    force_refresh = request.args.get('refresh') == '1'

    try:
        snapshot = get_todo_service(config).get_snapshot(force=force_refresh)
        return render_template(
            'todo.html',
            state='ready',
            todo=build_todo_view(snapshot),
        )
    except TodoConfigurationError as error:
        return render_template(
            'todo.html',
            state='configuration_required',
            state_title='Connect Microsoft To Do',
            state_message=str(error),
            todo=None,
        )
    except TodoAuthenticationRequired as error:
        return render_template(
            'todo.html',
            state='authentication_required',
            state_title='Sign in to Microsoft',
            state_message=str(error),
            todo=None,
        )
    except TodoGraphError as error:
        app.logger.warning(
            'Microsoft Graph request failed: status=%s code=%s request_id=%s',
            error.status,
            error.code,
            error.request_id,
        )
        return render_template(
            'todo.html',
            state='upstream_error',
            state_title='Microsoft To Do is unavailable',
            state_message='RonHub could not load your tasks. Try again in a moment.',
            todo=None,
        ), 502
    except Exception:
        app.logger.exception('Unexpected Microsoft To Do page failure')
        return render_template(
            'todo.html',
            state='upstream_error',
            state_title='Microsoft To Do is unavailable',
            state_message='RonHub could not load your tasks. Try again in a moment.',
            todo=None,
        ), 502


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
    config = load_config()
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
        config['fitness']['client_secret'] = form.get('fit_client_secret')
        config['fitness']['refresh_token'] = form.get('fit_refresh_token')

    if 'energy_auth_key' in form:
        config['energy']['auth_key'] = form.get('energy_auth_key')
        config['energy']['device_id'] = form.get('energy_device_id')
        config['energy']['cost_per_kwh'] = float(form.get('energy_cost') or 0)

    save_config(config)
    reschedule_all()
    return redirect(url_for('index'))

@app.route('/trigger/<job_name>')
def trigger_job(job_name):
    jobs = {'dota': dota_controller, 'weather': weather_controller, 
            'fitness': strava_controller, 'energy': energy_controller, 'f1': f1_controller,
            'family': family_controller}
    
    if job_name in jobs:
        threading.Thread(target=run_job, args=(job_name, jobs[job_name], True)).start()
        
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
