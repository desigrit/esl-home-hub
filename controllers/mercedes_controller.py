"""
PROJECT: ESL Hub
MODULE: Mercedes Controller (WebScraper)
AUTHOR: Raunak Oberoi
DATE: Jan 2026

DESCRIPTION:
Pulls scraper data from Azure VM via SCP using 'WebScraper' config.
Updates ESL tag with "Jackpot" findings and sets Red/White header status.
"""

import json
import os
import subprocess
import datetime
import time
import requests
from dateutil import parser 
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Get the directory where this script is located (e.g., /home/ronhub/esl_hub/controllers)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Define the data subfolder
DATA_DIR = os.path.join(BASE_DIR, "data")

# Create the directory if it doesn't exist (Self-healing)
os.makedirs(DATA_DIR, exist_ok=True)

# Update paths to point to the new 'data' subfolder
LOCAL_JSON_PATH = os.path.join(DATA_DIR, "mercedes_data.json")
STATE_FILE = os.path.join(DATA_DIR, "mercedes_state.json")

def run(full_config):
    # 1. LOAD CONFIG
    sys = full_config['system']
    
    if 'WebScraper' not in full_config:
        print("⚠️ Config missing 'WebScraper' block. Skipping.")
        return

    cfg = full_config['WebScraper'] 
    
    if not cfg['enabled']:
        return

    GATEWAY_URL = f"http://{sys['gateway_ip']}/api/product"
    STORE_CODE = sys['store_code']
    TAG_ID = cfg['tag_id']
    LAYOUT_ID = "4p20c_WebScraper" 
    
    AZURE_USER = cfg['azure_user']
    AZURE_IP = cfg['azure_ip']
    SSH_KEY_PATH = cfg['ssh_key_path']
    REMOTE_PATH = cfg['remote_path']

    # --- HELPER: RETRY SESSION ---
    def get_retry_session(retries=3, backoff_factor=1):
        session = requests.Session()
        retry = Retry(total=retries, backoff_factor=backoff_factor, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        return session

    # --- HELPER: STATE MANAGEMENT ---
    def load_state():
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f: return json.load(f)
            except: pass
        return {"seen_ids": [], "alert_expiry": None}

    def save_state(state):
        with open(STATE_FILE, "w") as f: json.dump(state, f, indent=2)

    # 2. DOWNLOAD DATA (SCP)
    print(f"🏎️  Fetching WebScraper Data from Azure...")
    cmd = [
        "scp", "-i", SSH_KEY_PATH, "-o", "StrictHostKeyChecking=no",
        f"{AZURE_USER}@{AZURE_IP}:{REMOTE_PATH}", LOCAL_JSON_PATH
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print("❌ SCP Download Failed. Check keys, IP, or file path.")
        return

    # 3. PROCESS DATA
    try:
        with open(LOCAL_JSON_PATH, "r") as f:
            new_data = json.load(f)
    except Exception as e:
        print(f"❌ JSON Load Failed: {e}")
        return

    state = load_state()
    
    current_ids = set(c['id'] for c in new_data.get("jackpots", []) + new_data.get("matches", []))
    new_finds = [uid for uid in current_ids if uid not in state['seen_ids']]
    
    if new_finds:
        print(f"🚨 NEW CARS DETECTED: {new_finds}")
        state['alert_expiry'] = (datetime.datetime.now() + datetime.timedelta(hours=24)).isoformat()
        state['seen_ids'] = list(set(state['seen_ids']) | current_ids)
        save_state(state)

    is_red = False
    if state['alert_expiry']:
        if datetime.datetime.now() < parser.parse(state['alert_expiry']):
            is_red = True
        else:
            state['alert_expiry'] = None 
            save_state(state)

    # 4. PREPARE DISPLAY DATA
    data = [""] * 300 

    # --- FORMAT HELPERS ---
    def format_list(prefix, cars):
        count = len(cars)
        if count == 0: return f"{prefix}: 0 found"
        models = sorted(list(set(c['model'] for c in cars)))
        return f"{prefix}: {count} found: {', '.join(models)}"

    def format_smart_time(time_str):
        """Converts '2026-01-21 18:00:00' to 'Jan 21, 6 PM' or 'Jan 21, 6:15 PM'"""
        try:
            # Parse the string (e.g. from JSON) into a datetime object
            dt = parser.parse(time_str)
            if dt.minute == 0:
                return dt.strftime("%b %-d, %-I %p")      
            else:
                return dt.strftime("%b %-d, %-I:%M %p")   
        except:
            return time_str # Fallback if parsing fails

    # [PR_250] : Last Run (Smart Formatted)
    raw_time = new_data.get('last_run', 'Unknown')
    data[250] = f"Last run: {format_smart_time(raw_time)}"

    # [PR_251] : Jackpots
    data[251] = format_list("• Jackpot", new_data.get("jackpots", []))

    # [PR_252] : Still Awesome
    data[252] = format_list("• Still awesome", new_data.get("matches", []))

    # [PR_256] : STATUS COLOR TRIGGER
    data[256] = "1" if is_red else "2"

    # 5. PUSH TO GATEWAY
    task_id = str(int(time.time() * 1000))
    payload = {
        "storeCode": STORE_CODE,
        "taskId": task_id,
        "product": [{
            "prCode": TAG_ID,
            "layoutId": LAYOUT_ID,
            "prInfo": data, 
            "nfc": ""
        }]
    }
    
    try:
        response = get_retry_session().post(GATEWAY_URL, json=payload, timeout=20)
        if response.status_code == 200:
            print(f"✅ WebScraper Tag Updated! ({'RED' if is_red else 'WHITE'} Alert)")
        else:
            print(f"❌ Gateway Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")

# ==========================================
# STANDALONE TESTING BLOCK
# ==========================================
if __name__ == "__main__":
    print("🔧 Running in Standalone Mode...")
    
    # 1. Get the directory where this script lives (.../esl_hub/controllers)
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    
    # 2. Define path to config.json (one folder up: .../esl_hub/config.json)
    CONFIG_PATH = os.path.join(SCRIPT_DIR, "..", "config.json")
    
    config = None
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                config = json.load(f)
            print(f"✅ Loaded config from {CONFIG_PATH}")
        except Exception as e:
            print(f"❌ Error loading {CONFIG_PATH}: {e}")
    
    if config:
        run(config)
    else:
        print(f"❌ Could not find config.json at {CONFIG_PATH}!")