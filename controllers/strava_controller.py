"""
PROJECT: ESL Hub (Electronic Shelf Label Dashboard)
MODULE: Fitness Controller (Strava)
AUTHOR: Raunak Oberoi
DATE: Jan 2026

DESCRIPTION:
This script fetches workout data from Strava, calculates monthly stats, and formats
data for a 4.2-inch Rainus ESL Tag. It visualizes activity history as a 
calendar grid and displays heart rate stats.

KEY FEATURES:
- Auto-refreshes Strava OAuth tokens and saves them back to config.json.
- Generates a 35-day calendar grid (Indices 100-134).
- logic to "Bold" the current day's cell in the grid.
- Robust Network Retry: Waits 60s between failures to survive WiFi dropouts.
"""

import requests
import json
import datetime
import time
import calendar
import os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- CONFIGURATION ---
# These control the visual scaling of the progress bars.
CONFIG_FILE = 'config.json'
TARGET_WORKOUTS = 14     # Goal: 14 workouts/month = 100% bar width
MAX_BAR_WIDTH = 100      # Pixel width of the progress bar on the layout

def run(full_config):
    # 1. LOAD CONFIGURATION
    # The 'system' block contains Hub-wide settings (Gateway IP, Store Code).
    # The 'fitness' block contains Strava specific credentials.
    sys = full_config['system']
    cfg = full_config['fitness']
    
    CLIENT_ID = cfg['client_id']
    CLIENT_SECRET = cfg['client_secret']
    REFRESH_TOKEN = cfg['refresh_token']
    
    GATEWAY_IP = sys['gateway_ip']
    STORE_CODE = sys['store_code']
    TAG_ID = cfg['tag_id']
    LAYOUT_ID = "4p20c_NORMAL"  # Must match the Layout ID in Rainus Web UI

    # --- NETWORK HELPER: RETRY SESSION ---
    # Creates a request session that automatically retries failed connections.
    # Critical for Raspberry Pi setups where WiFi might sleep or be spotty.
    # Backoff: 60s -> 120s -> 240s
    def get_retry_session(retries=3, backoff_factor=60, status_forcelist=(500, 502, 503, 504, 429)):
        session = requests.Session()
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    # 2. STRAVA AUTHENTICATION
    # Strava tokens expire short-term. We use the Refresh Token to get a new Access Token.
    # If the Refresh Token itself rotates, we save the new one to 'config.json'.
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
            r = get_retry_session().post("https://www.strava.com/oauth/token", data=payload, timeout=20)
            
            if r.status_code == 200:
                data = r.json()
                
                # SELF-HEALING CONFIG: Update file if token changes
                new_refresh = data.get('refresh_token')
                if new_refresh and new_refresh != REFRESH_TOKEN:
                    print("⚠️ Token Rotated! Updating config.json...")
                    update_config_token(new_refresh)
                
                return data['access_token']
            print(f"❌ Auth Failed: {r.text}")
        except Exception as e:
            print(f"❌ Connection Error (Auth): {e}")
        return None

    def update_config_token(new_token):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
            data['fitness']['refresh_token'] = new_token
            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f, indent=2)

    # 3. DATA FETCHING
    def fetch_activities(access_token):
        print("🏃 Fetching Activities...")
        # We only care about the current month's data
        now = datetime.datetime.now()
        start_of_month = datetime.datetime(now.year, now.month, 1)
        epoch_time = int(start_of_month.timestamp())
        
        headers = {'Authorization': f"Bearer {access_token}"}
        params = {'after': epoch_time, 'per_page': 50}
        
        try:
            r = get_retry_session().get("https://www.strava.com/api/v3/athlete/activities", headers=headers, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
            print(f"❌ API Error: {r.text}")
        except Exception as e:
            print(f"❌ Fetch Error: {e}")
        return []

    # 4. DATA PROCESSING
    token = get_access_token()
    if not token: return
    
    activities = fetch_activities(token)
    if isinstance(activities, dict): return 

    now = datetime.datetime.now()
    
    # --- CALENDAR GRID LOGIC ---
    # The layout expects a 35-cell grid (5 rows x 7 cols).
    # We map the days of the month to these cells based on the weekday the month starts.
    grid = ["0"] * 35 
    start_day_index, days_in_month = calendar.monthrange(now.year, now.month)
    
    # Mark valid days with '1' (Empty Box)
    for day in range(1, days_in_month + 1):
        grid_idx = start_day_index + (day - 1)
        if grid_idx < 35: grid[grid_idx] = "1" 

    run_count = 0
    xfit_count = 0
    last_run = {"hr_avg": "-", "hr_peak": "-"}
    last_xfit = {"hr_avg": "-", "hr_peak": "-"}
    
    # Process each activity and update grid
    for act in activities:
        if not isinstance(act, dict): continue
        if 'start_date_local' not in act or 'type' not in act: continue

        try:
            act_date = datetime.datetime.strptime(act['start_date_local'], "%Y-%m-%dT%H:%M:%SZ")
            day_of_month = act_date.day
            grid_idx = start_day_index + (day_of_month - 1)
            
            if grid_idx >= 35: continue 
            
            act_type = act['type']
            
            # STATE MAPPING (Layout Designer Conditions):
            # '0' = Hidden/Blank
            # '1' = Empty Box (Valid Date)
            # '2' = Run Icon
            # '3' = Weight/CrossFit Icon
            
            if act_type == "Run":
                run_count += 1
                if grid[grid_idx] != "3": grid[grid_idx] = "2" # Don't overwrite weights with run
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

    # --- TODAY HIGHLIGHT LOGIC ---
    # To show "Today" distinctly, we shift the state ID by +3.
    # Layout Designer needs conditions for 4, 5, and 6 to draw a Bold Box.
    # 1 -> 4 (Bold Empty)
    # 2 -> 5 (Bold Run)
    # 3 -> 6 (Bold Weights)
    today_idx = start_day_index + (now.day - 1)
    if 0 <= today_idx < 35:
        current_val = grid[today_idx]
        bold_map = {"1": "4", "2": "5", "3": "6"}
        if current_val in bold_map:
            grid[today_idx] = bold_map[current_val]

    # 5. DATA PACKING (ESL GATEWAY FORMAT)
    # pr_data list maps directly to 'Product Code' fields in Layout Designer.
    
    run_width = int((min(run_count, TARGET_WORKOUTS) / TARGET_WORKOUTS) * MAX_BAR_WIDTH)
    xfit_width = int((min(xfit_count, TARGET_WORKOUTS) / TARGET_WORKOUTS) * MAX_BAR_WIDTH)

    pr_data = [""] * 250
    
    # [PR_100 - PR_134] : The 35 Calendar Grid Cells
    for i, val in enumerate(grid): pr_data[100 + i] = val
        
    # [PR_139 - PR_140] : Progress Bar Widths (Layout Condition: Object Width)
    pr_data[139] = str(xfit_width)
    pr_data[140] = str(run_width)
    
    # [PR_141 - PR_144] : Heart Rate Stats
    pr_data[141] = last_xfit['hr_avg']
    pr_data[142] = last_xfit['hr_peak']
    pr_data[143] = last_run['hr_avg']
    pr_data[144] = last_run['hr_peak']
    
    # [PR_145] : Last Updated Timestamp
    # Logic: If 9:00 PM, show "9 PM". If 9:23 PM, show "9:23 PM"
    if now.minute == 0:
        time_str = now.strftime("%b %-d, %-I %p")      
    else:
        time_str = now.strftime("%b %-d, %-I:%M %p")   
    pr_data[145] = f"Last updated: {time_str}"

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
        r = get_retry_session().post(f"http://{GATEWAY_IP}/api/product", json=payload, timeout=20)
        if r.status_code == 200:
            print("🚀 Strava Tag Updated!")
        else:
            print(f"❌ Gateway Error: {r.text}")
    except Exception as e:
        print(f"❌ Connection Error (Gateway): {e}")