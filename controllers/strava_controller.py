import requests
import json
import datetime
import time
import calendar
import os

# CONSTANTS
CONFIG_FILE = 'config.json'
TARGET_WORKOUTS = 14
MAX_BAR_WIDTH = 100

def run(full_config):
    # 1. LOAD CONFIG
    sys = full_config['system']
    cfg = full_config['fitness']
    
    CLIENT_ID = cfg['client_id']
    CLIENT_SECRET = cfg['client_secret']
    REFRESH_TOKEN = cfg['refresh_token']
    
    GATEWAY_IP = sys['gateway_ip']
    STORE_CODE = sys['store_code']
    TAG_ID = cfg['tag_id']
    LAYOUT_ID = "4p20c_NORMAL"

    # 2. HELPER: TOKEN REFRESH & AUTO-SAVE
    def get_access_token():
        print("🔑 Refreshing Strava Access Token...")
        payload = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'refresh_token': REFRESH_TOKEN,
            'grant_type': 'refresh_token',
            'f': 'json'
        }
        try:
            r = requests.post("https://www.strava.com/oauth/token", data=payload)
            if r.status_code == 200:
                data = r.json()
                
                # --- AUTO-UPDATE CONFIG IF TOKEN ROTATES ---
                new_refresh = data.get('refresh_token')
                if new_refresh and new_refresh != REFRESH_TOKEN:
                    print("⚠️ Token Rotated! Updating config.json...")
                    update_config_token(new_refresh)
                
                return data['access_token']
            print(f"❌ Auth Failed: {r.text}")
        except Exception as e:
            print(f"❌ Connection Error: {e}")
        return None

    def update_config_token(new_token):
        # Reads the JSON, updates just the token, and saves back
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
            data['fitness']['refresh_token'] = new_token
            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f, indent=2)

    def fetch_activities(access_token):
        print("🏃 Fetching Activities...")
        now = datetime.datetime.now()
        start_of_month = datetime.datetime(now.year, now.month, 1)
        epoch_time = int(start_of_month.timestamp())
        
        headers = {'Authorization': f"Bearer {access_token}"}
        params = {'after': epoch_time, 'per_page': 50}
        
        try:
            r = requests.get("https://www.strava.com/api/v3/athlete/activities", headers=headers, params=params)
            if r.status_code == 200:
                return r.json()
            print(f"❌ API Error: {r.text}")
        except Exception as e:
            print(f"❌ Fetch Error: {e}")
        return []

    # 3. PROCESS DATA
    token = get_access_token()
    if not token: return
    
    activities = fetch_activities(token)
    if isinstance(activities, dict): return # Error check

    now = datetime.datetime.now()
    grid = ["0"] * 35 
    start_day_index, days_in_month = calendar.monthrange(now.year, now.month)
    
    # Initialize empty grid
    for day in range(1, days_in_month + 1):
        grid_idx = start_day_index + (day - 1)
        if grid_idx < 35: grid[grid_idx] = "1" 

    run_count = 0
    xfit_count = 0
    last_run = {"hr_avg": "-", "hr_peak": "-"}
    last_xfit = {"hr_avg": "-", "hr_peak": "-"}
    
    for act in activities:
        if not isinstance(act, dict): continue
        if 'start_date_local' not in act or 'type' not in act: continue

        try:
            act_date = datetime.datetime.strptime(act['start_date_local'], "%Y-%m-%dT%H:%M:%SZ")
            day_of_month = act_date.day
            grid_idx = start_day_index + (day_of_month - 1)
            
            if grid_idx >= 35: continue 
            
            act_type = act['type']
            
            if act_type == "Run":
                run_count += 1
                if grid[grid_idx] != "3": grid[grid_idx] = "2"
                if act.get('has_heartrate'):
                    last_run['hr_avg'] = f"{int(act.get('average_heartrate',0))} bpm"
                    last_run['hr_peak'] = f"{int(act.get('max_heartrate',0))} bpm"

            elif act_type in ["WeightTraining", "CrossFit", "HIIT", "Workout"]:
                xfit_count += 1
                grid[grid_idx] = "3"
                if act.get('has_heartrate'):
                    last_xfit['hr_avg'] = f"{int(act.get('average_heartrate',0))} bpm"
                    last_xfit['hr_peak'] = f"{int(act.get('max_heartrate',0))} bpm"
        except: continue

    # --- 3.5 HIGHLIGHT TODAY ---
    # Find the grid index for today's date
    today_idx = start_day_index + (now.day - 1)
    print(f"DEBUG: Start Index: {start_day_index}, Today Index: {today_idx}")
    
    if 0 <= today_idx < 35:
        current_val = grid[today_idx]
        # Map normal states to "Bold" states
        # 1->4, 2->5, 3->6
        bold_map = {"1": "4", "2": "5", "3": "6"}
        
        if current_val in bold_map:
            grid[today_idx] = bold_map[current_val]
            print(f"✨ Highlighting Today (Idx {today_idx}) as State {grid[today_idx]}")

    # 4. PUSH PAYLOAD
    run_width = int((min(run_count, TARGET_WORKOUTS) / TARGET_WORKOUTS) * MAX_BAR_WIDTH)
    xfit_width = int((min(xfit_count, TARGET_WORKOUTS) / TARGET_WORKOUTS) * MAX_BAR_WIDTH)

    pr_data = [""] * 250
    for i, val in enumerate(grid): pr_data[100 + i] = val
        
    pr_data[139] = str(xfit_width)
    pr_data[140] = str(run_width)
    pr_data[141] = last_xfit['hr_avg']
    pr_data[142] = last_xfit['hr_peak']
    pr_data[143] = last_run['hr_avg']
    pr_data[144] = last_run['hr_peak']
    pr_data[145] = datetime.datetime.now().strftime("Last updated: %b %-d, %-I:%M %p")

    unique_task_id = str(int(time.time()))
    payload = {
        "storeCode": STORE_CODE,
        "taskId": unique_task_id,
        "product": [{
            "prCode": TAG_ID,
            "layoutId": LAYOUT_ID,
            "prInfo": pr_data,
            "nfc": ""
        }]
    }
    
    try:
        r = requests.post(f"http://{GATEWAY_IP}/api/product", json=payload)
        if r.status_code == 200:
            print("🚀 Strava Tag Updated!")
        else:
            print(f"❌ Gateway Error: {r.text}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")