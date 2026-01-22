"""
PROJECT: ESL Hub
MODULE: Weather Controller
AUTHOR: Raunak Oberoi
DATE: Jan 2026

DESCRIPTION:
Fetches 2-day forecast for 3 cities (Seattle, Delhi, Hyderabad) via Open-Meteo.
Displays current temps, highs/lows, and a 5-step hourly forecast for Seattle.

KEY FEATURES:
- Uses Open-Meteo (No API Key required).
- Maps Weather Codes (WMO) to string IDs (e.g., 'PARTLYCLOUDY') that match
  image filenames in the Rainus Layout Designer.
"""

import requests
import datetime
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- ASSET MAPPING ---
# These strings (e.g., "RAIN") must match the Image Mapping keys in Layout Designer.
ICON_MAP = {
    0: "CLEAR", 1: "MAINLYCLEAR", 2: "PARTLYCLOUDY", 3: "OVERCAST",
    45: "FOG", 48: "FOG", 
    51: "RAIN", 53: "RAIN", 55: "RAIN", 56: "RAIN", 57: "RAIN",
    61: "RAIN", 63: "RAIN", 65: "RAIN", 66: "RAIN", 67: "RAIN",
    71: "SNOW", 73: "SNOW", 75: "SNOW", 77: "SNOW",
    80: "RAIN", 81: "RAIN", 82: "RAIN", 
    85: "SNOWSHOWERS", 86: "SNOWSHOWERS",
    95: "STORM", 96: "STORMHEAVY", 99: "STORMHEAVY"
}

DESC_MAP = {
    0: "Sunny", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog", 
    51: "Drizzle", 53: "Mod. Drizzle", 55: "Dense Drizzle",
    # ... (Truncated for brevity, full map in standard WMO codes) ...
    95: "Thunderstorm", 96: "Thunderstorm/Hail", 99: "Heavy Hail"
}

def run(full_config):
    # 1. LOAD CONFIG
    sys = full_config['system']
    cfg = full_config['weather']
    
    GATEWAY_URL = f"http://{sys['gateway_ip']}/api/product"
    STORE_CODE = sys['store_code']
    TAG_ID = cfg['tag_id']
    LAYOUT_ID = "4p20c_Weather"
    
    LOCATIONS = cfg['locations']

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

    # 2. HELPER: FETCH WEATHER
    def get_weather(lat, lon):
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&hourly=temperature_2m,weather_code,precipitation_probability&daily=temperature_2m_max,temperature_2m_min&temperature_unit=celsius&forecast_days=2&timeformat=unixtime&timezone=auto"
        try:
            r = get_retry_session().get(url, timeout=70) 
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"⚠️ API Fetch Failed for {lat},{lon}: {e}")
            return None

    # 3. FETCH DATA
    print(f"☁️ Fetching Weather for {list(LOCATIONS.keys())}...")
    sea = get_weather(LOCATIONS["Seattle"]["lat"], LOCATIONS["Seattle"]["lon"])
    delhi = get_weather(LOCATIONS["Delhi"]["lat"], LOCATIONS["Delhi"]["lon"])
    hyd = get_weather(LOCATIONS["Hyderabad"]["lat"], LOCATIONS["Hyderabad"]["lon"])
    
    if not sea or not delhi or not hyd:
        print("❌ Weather Fetch Failed")
        return

    # --- DATA MAPPING (LAYOUT DESIGNER) ---
    data = [""] * 100 

    # [PR_10 - PR_14] : Seattle Summary
    curr = sea['current']
    daily = sea['daily']
    data[10] = f"{int(curr['temperature_2m'])}°"
    data[11] = DESC_MAP.get(curr['weather_code'], "")
    data[12] = f"{int(daily['temperature_2m_min'][0])}° , {int(daily['temperature_2m_max'][0])}°"
    
    # Smart Timestamp
    now = datetime.datetime.now()
    if now.minute == 0:
        time_str = now.strftime("%b %-d, %-I %p")      
    else:
        time_str = now.strftime("%b %-d, %-I:%M %p")   
    data[13] = f"Last updated: {time_str}"
    data[14] = ICON_MAP.get(curr['weather_code'], "PARTLYCLOUDY")

    # [PR_15 - PR_29] : Hourly Forecast (Next 15 hours in 3-hour steps)
    hourly = sea['hourly']
    current_hour_idx = datetime.datetime.now().hour
    for i in range(5):
        # We skip ahead 3 hours per step (i.e., +3, +6, +9...)
        target_idx = current_hour_idx + ((i + 1) * 3)
        if target_idx >= len(hourly['time']): break
        
        ts = hourly['time'][target_idx]
        dt = datetime.datetime.fromtimestamp(ts)
        
        data[15 + i] = dt.strftime("%-I %p") # Time (e.g. "2 PM")
        
        code = hourly['weather_code'][target_idx]
        data[20 + i] = ICON_MAP.get(code, "PARTLYCLOUDY") # Icon
        
        temp = int(hourly['temperature_2m'][target_idx])
        rain = hourly['precipitation_probability'][target_idx]
        data[25 + i] = f"{temp}° R: {rain}" # Temp & Rain Prob

    # [PR_30 - PR_33] : Delhi Summary
    d_curr = delhi['current']
    d_daily = delhi['daily']
    data[30] = "Delhi, DL"
    data[31] = f"{int(d_curr['temperature_2m'])}° {DESC_MAP.get(d_curr['weather_code'], '')}"
    data[32] = f"{int(d_daily['temperature_2m_max'][0])}° , {int(d_daily['temperature_2m_min'][0])}°"
    data[33] = ICON_MAP.get(d_curr['weather_code'], "PARTLYCLOUDY")

    # [PR_34 - PR_37] : Hyderabad Summary
    h_curr = hyd['current']
    h_daily = hyd['daily']
    data[34] = "Hyderabad, TS"
    data[35] = f"{int(h_curr['temperature_2m'])}° {DESC_MAP.get(h_curr['weather_code'], '')}"
    data[36] = f"{int(h_daily['temperature_2m_max'][0])}° , {int(h_daily['temperature_2m_min'][0])}°"
    data[37] = ICON_MAP.get(h_curr['weather_code'], "PARTLYCLOUDY")

    # 4. PUSH TO GATEWAY
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
            print(f"✅ Weather Tag Updated! (Seattle: {data[10]})")
        else:
            print(f"❌ Gateway Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")