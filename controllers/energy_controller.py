import requests
import datetime
import time

# --- CONFIG FROM PC VERSION ---
PIXELS_PER_KWH = 10 
MAX_BAR_HEIGHT = 65 

def run(full_config):
    # 1. LOAD CONFIG (Hub Structure)
    sys = full_config['system']
    cfg = full_config['energy']
    
    # Use default URL if not in config, otherwise use what's in config
    SHELLY_BASE_URL = cfg.get('shelly_url', "https://shelly-113-eu.shelly.cloud/v2/statistics/power-consumption/overall")
    AUTH_KEY = cfg['auth_key']
    DEVICE_ID = cfg['device_id']
    
    GATEWAY_IP = sys['gateway_ip']
    STORE_CODE = sys['store_code']
    TAG_ID = cfg.get('tag_id', 'MY_STATS_02') # Default if missing
    LAYOUT_ID = "4p20c_Energy"

    # 2. FETCH DATA (Restored Logic)
    print("🔌 Fetching Shelly Data...")
    
    # Define "Today" to filter out partial data
    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    # Fetch 33 days to ensure we have 30 FULL days after filtering
    start_date = now - datetime.timedelta(days=33)
    
    params = {
        "auth_key": AUTH_KEY, "id": DEVICE_ID, "channel": 0,
        "date_range": "custom",
        "date_from": start_date.strftime("%Y-%m-%d 00:00:00"),
        "date_to": now.strftime("%Y-%m-%d 23:59:59")
    }
    
    history = []
    try:
        r = requests.get(SHELLY_BASE_URL, params=params)
        if r.status_code != 200:
            print(f"❌ API Error: {r.text}")
            return

        data = r.json()
        raw_history = data.get('history', [])
        
        for entry in raw_history:
            # STRICT FILTER: Tariff 1 AND Date < Today
            entry_date_str = entry['datetime'].split(" ")[0]
            if entry.get('tariff_id') == "1" and entry_date_str < today_str:
                history.append({
                    'date': entry['datetime'],
                    'kwh': entry['consumption'] / 1000.0,
                    'cost': entry.get('cost', 0)
                })
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return

    if not history: 
        print("⚠️ No valid history found (check dates).")
        return

    # 3. CALCULATE STATS (Restored PC Logic)
    yesterday = history[-1]
    dt_obj = datetime.datetime.strptime(yesterday['date'], "%Y-%m-%d %H:%M:%S")
    yesterday_str = dt_obj.strftime("%b %d")

    last_30 = history[-30:]
    month_kwh = sum(d['kwh'] for d in last_30)
    month_cost = sum(d['cost'] for d in last_30)
    month_days = len(last_30)
    month_avg_watts = int(((month_kwh / month_days) * 1000) / 24) if month_days else 0

    curr_year = str(now.year)
    ytd = [d for d in history if d['date'].startswith(curr_year)]
    ytd_kwh = sum(d['kwh'] for d in ytd)
    ytd_cost = sum(d['cost'] for d in ytd)
    ytd_days = len(ytd)
    ytd_avg_watts = int(((ytd_kwh / ytd_days) * 1000) / 24) if ytd_days else 0

    # Markers
    graph_slice = history[-29:]
    def fmt_date(entry):
        d = datetime.datetime.strptime(entry['date'], "%Y-%m-%d %H:%M:%S")
        return d.strftime("%b %d")

    marker_right = fmt_date(graph_slice[-1]) if graph_slice else "-"
    marker_mid   = fmt_date(graph_slice[len(graph_slice)//2]) if graph_slice else "-"
    marker_left  = fmt_date(graph_slice[0]) if graph_slice else "-"

    # 4. PREPARE PAYLOAD
    pr_data = [""] * 101 # Size 101 covers indexes up to 100
    
    # Header
    pr_data[51] = f"{yesterday['kwh']:.1f} kWh"
    pr_data[52] = f"Power - {yesterday_str}"
    
    # Month
    pr_data[53] = f"{int(month_kwh)} kWh"
    pr_data[54] = f"{month_avg_watts} W"
    pr_data[55] = f"${month_cost:.2f}"
    
    # YTD
    pr_data[56] = f"{int(ytd_kwh)} kWh"
    pr_data[57] = f"{ytd_avg_watts} W"
    pr_data[58] = f"${ytd_cost:.2f}"
    
    # Markers (Restored)
    pr_data[90] = marker_left
    pr_data[91] = marker_mid
    pr_data[92] = marker_right

    # Timestamp (New feature we want to keep)
    pr_data[93] = now.strftime("Last updated: %I:%M %p")

    # Graph Bars (Restored Fixed Scaling)
    for i, entry in enumerate(graph_slice):
        pixel_h = int(entry['kwh'] * PIXELS_PER_KWH)
        if pixel_h > MAX_BAR_HEIGHT: pixel_h = MAX_BAR_HEIGHT
        if pixel_h < 2 and entry['kwh'] > 0: pixel_h = 2
        pr_data[60 + i] = str(pixel_h)

    # 5. PUSH TO GATEWAY
    payload = {
        "storeCode": STORE_CODE,
        "taskId": str(int(time.time())), # Unique ID
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
            print(f"🚀 Energy Tag Updated! (Latest Data: {marker_right})")
        else:
            print(f"❌ Gateway Error: {r.text}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")