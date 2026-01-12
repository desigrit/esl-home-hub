import json
import os
import time
import threading
import datetime
import io
import contextlib
import sys
from flask import Flask, render_template, request, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler

# Import your controllers
from controllers import dota_controller, weather_controller, strava_controller, energy_controller

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
        return {"dota": [], "weather": [], "fitness": [], "energy": []}
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
        return {"dota": [], "weather": [], "fitness": [], "energy": []}

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
        'energy': energy_controller
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
scheduler.start()
threading.Timer(2.0, reschedule_all).start()

# --- WEB ROUTES ---
@app.route('/')
def index():
    return render_template('index.html', config=load_config(), logs=load_logs())

@app.route('/update', methods=['POST'])
def update_settings():
    config = load_config()
    form = request.form
    
    def process_tab(key):
        config[key]['enabled'] = f'{key}_enabled' in form
        config[key]['mode'] = form.get(f'{key}_mode', 'interval')
        config[key]['interval'] = int(form.get(f'{key}_interval', 30))
        config[key]['days'] = int(form.get(f'{key}_days', 1))
        config[key]['times'] = [t for t in form.getlist(f'{key}_times[]') if t]

    process_tab('dota')
    process_tab('weather')
    process_tab('fitness')
    process_tab('energy')

    config['system']['gateway_ip'] = form.get('sys_gateway_ip')
    config['system']['store_code'] = form.get('sys_store_code')
    
    config['dota']['steam_id'] = form.get('dota_steam_id')
    config['dota']['baseline_mmr'] = int(form.get('dota_baseline_mmr') or 0)
    config['dota']['target_mmr'] = int(form.get('dota_target_mmr') or 0)
    config['dota']['baseline_match_id'] = int(form.get('dota_baseline_match_id') or 0)

    config['fitness']['client_id'] = form.get('fit_client_id')
    config['fitness']['client_secret'] = form.get('fit_client_secret')
    config['fitness']['refresh_token'] = form.get('fit_refresh_token')

    config['energy']['auth_key'] = form.get('energy_auth_key')
    config['energy']['device_id'] = form.get('energy_device_id')
    config['energy']['cost_per_kwh'] = float(form.get('energy_cost') or 0)

    save_config(config)
    reschedule_all()
    return redirect(url_for('index'))

@app.route('/trigger/<job_name>')
def trigger_job(job_name):
    jobs = {'dota': dota_controller, 'weather': weather_controller, 
            'fitness': strava_controller, 'energy': energy_controller}
    
    if job_name in jobs:
        threading.Thread(target=run_job, args=(job_name, jobs[job_name], True)).start()
        
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)