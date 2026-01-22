"""
PROJECT: ESL Hub
MODULE: Energy Controller (Shelly EM)
AUTHOR: Raunak Oberoi
DATE: Jan 2026

DESCRIPTION:
Fetches electricity usage from a Shelly EM cloud API.
Displays 30-day consumption history as a bar graph and calculates costs.

KEY FEATURES:
- Fetches 33 days of history to ensure a full 30-day visual despite timezones.
- STRICT FILTERING: Only counts Tariff 1 (Peak) and excludes 'Today' (incomplete data).
- Maps kWh to pixel height for drawing bars in the Layout Designer.
"""

import requests
import datetime
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- VISUAL CONFIGURATION ---
PIXELS_PER_KWH = 10     # Scaling factor: 2.5 kWh = 25 pixels high
MAX_BAR_HEIGHT = 65     # Max height of the graph area in Layout Designer

def run(full_config):
    # 1. LOAD CONFIG
    sys = full_config['system']
    cfg = full_config['energy']
    
    # Default URL serves Shelly Cloud EU
    SHELLY_BASE_URL = cfg.get('shelly_url', "https://shelly-113-eu.shelly.cloud/v2/statistics/power-consumption/overall")
    AUTH_KEY = cfg['auth_key']
    DEVICE_ID = cfg['device_id']
    
    GATEWAY_IP = sys['gateway_ip']
    STORE_CODE = sys['store_code']
    TAG_ID = cfg.get('tag_id', 'MY_STATS_02')
    LAYOUT_ID = "4p20c_Energy"

    # --- NETWORK HELPER: RETRY SESSION ---
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

    # 2. FETCH DATA FROM SHELLY CLOUD
    print("🔌 Fetching Shelly Data...")
    
    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    # We request 33 days to be safe, then slice the last 30 valid days.
    start_date = now - datetime.timedelta(days=33)
    
    params = {
        "auth_key": AUTH_KEY, "id": DEVICE_ID, "channel": 0,
        "date_range": "custom",
        "date_from": start_date.strftime("%Y-%m-%d 00:00:00"),
        "date_to": now.strftime("%Y-%m-%d 23:59:59")
    }
    
    history = []
    try:
        r = get_retry_session().get(SHELLY_BASE_URL, params=params, timeout=30)
        
        if r.status_code != 200:
            print(f"❌ API Error: {r.text}")
            return

        data = r.json()
        raw_history = data.get('history', [])
        
        for entry in raw_history:
            # --- DATA FILTERING LOGIC ---
            # 1. Tariff ID '1': We only care about standard consumption (ignore returned/solar).
            # 2. Date < Today: We only show completed days.
            entry_date_str = entry['datetime'].split(" ")[0]
            if entry.get('tariff_id') == "1" and entry_date_str < today_str:
                history.append({
                    'date': entry['datetime'],
                    'kwh': entry['consumption'] / 1000.0,
                    'cost': entry.get('cost', 0)
                })
    except Exception as e:
        print(f"❌ Connection Error (Shelly): {e}")
        return

    if not history: 
        print("⚠️ No valid history found (check dates).")
        return

    # 3. STAT CALCULATIONS
    yesterday = history[-1]
    dt_obj = datetime.datetime.strptime(yesterday['date'], "%Y-%m-%d %H:%M:%S")
    yesterday_str = dt_obj.strftime("%b %d")

    # Last 30 Days Stats
    last_30 = history[-30:]
    month_kwh = sum(d['kwh'] for d in last_30)
    month_cost = sum(d['cost'] for d in last_30)
    month_days = len(last_30)
    # Average Watts = (Total kWh / Days) -> Daily kWh -> *1000 / 24hrs -> Watts
    month_avg_watts = int(((month_kwh / month_days) * 1000) / 24) if month_days else 0

    # Year-To-Date Stats
    curr_year = str(now.year)
    ytd = [d for d in history if d['date'].startswith(curr_year)]
    ytd_kwh = sum(d['kwh'] for d in ytd)
    ytd_cost = sum(d['cost'] for d in ytd)
    ytd_days = len(ytd)
    ytd_avg_watts = int(((ytd_kwh / ytd_days) * 1000) / 24) if ytd_days else 0

    # Date Markers for the X-Axis
    graph_slice = history[-29:] # The slice we actually draw
    def fmt_date(entry):
        d = datetime.datetime.strptime(entry['date'], "%Y-%m-%d %H:%M:%S")
        return d.strftime("%b %d")

    marker_right = fmt_date(graph_slice[-1]) if graph_slice else "-"
    marker_mid   = fmt_date(graph_slice[len(graph_slice)//2]) if graph_slice else "-"
    marker_left  = fmt_date(graph_slice[0]) if graph_slice else "-"

    # 4. DATA MAPPING (LAYOUT DESIGNER)
    pr_data = [""] * 101 
    
    # [PR_51 - PR_52] : Header (Yesterday's Usage)
    pr_data[51] = f"{yesterday['kwh']:.1f} kWh"
    pr_data[52] = f"Power - {yesterday_str}"
    
    # [PR_53 - PR_55] : Month Stats
    pr_data[53] = f"{int(month_kwh)} kWh"
    pr_data[54] = f"{month_avg_watts} W"
    pr_data[55] = f"${month_cost:.2f}"
    
    # [PR_56 - PR_58] : YTD Stats
    pr_data[56] = f"{int(ytd_kwh)} kWh"
    pr_data[57] = f"{ytd_avg_watts} W"
    pr_data[58] = f"${ytd_cost:.2f}"
    
    # [PR_90 - PR_92] : X-Axis Date Labels (Left, Center, Right)
    pr_data[90] = marker_left
    pr_data[91] = marker_mid
    pr_data[92] = marker_right

    # [PR_93] : Timestamp
    if now.minute == 0:
        time_str = now.strftime("%b %-d, %-I %p")      
    else:
        time_str = now.strftime("%b %-d, %-I:%M %p")   
    pr_data[93] = f"Last updated: {time_str}"

    # [PR_60 - PR_89] : Graph Bars
    # Layout Designer: These fields control the HEIGHT of 30 distinct rectangles.
    # Logic: Convert kWh to pixels. Min height = 2px (so 0 usage is still visible as a dot).
    for i, entry in enumerate(graph_slice):
        pixel_h = int(entry['kwh'] * PIXELS_PER_KWH)
        if pixel_h > MAX_BAR_HEIGHT: pixel_h = MAX_BAR_HEIGHT
        if pixel_h < 2 and entry['kwh'] > 0: pixel_h = 2
        pr_data[60 + i] = str(pixel_h)

    # 5. PUSH TO GATEWAY
    payload = {
        "storeCode": STORE_CODE,
        "taskId": str(int(time.time())), 
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
            print(f"🚀 Energy Tag Updated! (Latest Data: {marker_right})")
        else:
            print(f"❌ Gateway Error: {r.text}")
    except Exception as e:
        print(f"❌ Connection Error (Gateway): {e}")