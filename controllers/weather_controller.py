import requests
import datetime
import time

# --- STATIC MAPPINGS (Keep these global as they don't change) ---
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
    56: "Freezing Drizzle", 57: "Dense Fr. Drizzle",
    61: "Rain", 63: "Mod. Rain", 65: "Heavy Rain", 
    66: "Freezing Rain", 67: "Heavy Fr. Rain",
    71: "Snow", 73: "Mod. Snow", 75: "Heavy Snow", 77: "Snow Grains",
    80: "Rain Showers", 81: "Mod. Showers", 82: "Violent Showers",
    85: "Snow Showers", 86: "Heavy Snow Showers",
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
    
    # Load Locations from Config (allows you to edit them in JSON later)
    LOCATIONS = cfg['locations']

    # 2. HELPER
    def get_weather(lat, lon):
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&hourly=temperature_2m,weather_code,precipitation_probability&daily=temperature_2m_max,temperature_2m_min&temperature_unit=celsius&forecast_days=2&timeformat=unixtime&timezone=auto"
        try:
            r = requests.get(url, timeout=10) # Added timeout to prevent hanging
            r.raise_for_status() # Raises error if status code is 400/500
            return r.json()
        except Exception as e:
            print(f"⚠️ API Fetch Failed for {lat},{lon}: {e}") # <--- THIS IS KEY
            return None

    # 3. FETCH DATA
    print(f"☁️ Fetching Weather for {list(LOCATIONS.keys())}...")
    sea = get_weather(LOCATIONS["Seattle"]["lat"], LOCATIONS["Seattle"]["lon"])
    delhi = get_weather(LOCATIONS["Delhi"]["lat"], LOCATIONS["Delhi"]["lon"])
    hyd = get_weather(LOCATIONS["Hyderabad"]["lat"], LOCATIONS["Hyderabad"]["lon"])
    
    if not sea or not delhi or not hyd:
        print("❌ Weather Fetch Failed")
        return

    data = [""] * 100 

    # --- SEATTLE ---
    curr = sea['current']
    daily = sea['daily']
    data[10] = f"{int(curr['temperature_2m'])}°"
    data[11] = DESC_MAP.get(curr['weather_code'], "")
    data[12] = f"{int(daily['temperature_2m_min'][0])}° , {int(daily['temperature_2m_max'][0])}°"
    data[13] = datetime.datetime.now().strftime("Last updated: %#I:%M %p")
    data[14] = ICON_MAP.get(curr['weather_code'], "PARTLYCLOUDY")

    # HOURLY
    hourly = sea['hourly']
    current_hour_idx = datetime.datetime.now().hour
    for i in range(5):
        target_idx = current_hour_idx + ((i + 1) * 3)
        # Boundary check for API array
        if target_idx >= len(hourly['time']): break
        
        ts = hourly['time'][target_idx]
        dt = datetime.datetime.fromtimestamp(ts)
        
        data[15 + i] = dt.strftime("%#I %p") 
        code = hourly['weather_code'][target_idx]
        data[20 + i] = ICON_MAP.get(code, "PARTLYCLOUDY")
        
        temp = int(hourly['temperature_2m'][target_idx])
        rain = hourly['precipitation_probability'][target_idx]
        data[25 + i] = f"{temp}° R: {rain}"

    # --- DELHI ---
    d_curr = delhi['current']
    d_daily = delhi['daily']
    data[30] = "Delhi, DL"
    data[31] = f"{int(d_curr['temperature_2m'])}° {DESC_MAP.get(d_curr['weather_code'], '')}"
    data[32] = f"{int(d_daily['temperature_2m_max'][0])}° , {int(d_daily['temperature_2m_min'][0])}°"
    data[33] = ICON_MAP.get(d_curr['weather_code'], "PARTLYCLOUDY")

    # --- HYDERABAD ---
    h_curr = hyd['current']
    h_daily = hyd['daily']
    data[34] = "Hyderabad, TS"
    data[35] = f"{int(h_curr['temperature_2m'])}° {DESC_MAP.get(h_curr['weather_code'], '')}"
    data[36] = f"{int(h_daily['temperature_2m_max'][0])}° , {int(h_daily['temperature_2m_min'][0])}°"
    data[37] = ICON_MAP.get(h_curr['weather_code'], "PARTLYCLOUDY")

    # --- PUSH ---
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
        response = requests.post(GATEWAY_URL, json=payload)
        if response.status_code == 200:
            print(f"✅ Weather Tag Updated! (Seattle: {data[10]})")
        else:
            print(f"❌ Gateway Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")