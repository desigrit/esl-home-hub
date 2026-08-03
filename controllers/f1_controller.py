"""
PROJECT: ESL Hub (Electronic Shelf Label Dashboard)
MODULE: F1 Controller
AUTHOR: Raunak Oberoi
DATE: Jan 2026

DESCRIPTION:
Fetches the upcoming Formula 1 race weekend schedule and current championship standings.
Filters out Practice sessions and dynamically lists 2 or 4 main events (sorted chronologically).
Pulls the Top 3 WDC and WCC standings as multi-line strings.
Converts UTC session times to local Pacific Time.
Triggers track map visibility using the circuitId string in PR_273.
"""

import requests
import datetime
import time
from zoneinfo import ZoneInfo
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def run(full_config):
    # 1. LOAD CONFIGURATION
    sys = full_config['system']
    cfg = full_config.get('f1', {}) 
    
    GATEWAY_IP = sys['gateway_ip']
    STORE_CODE = sys['store_code']
    TAG_ID = cfg['tag_id']
    LAYOUT_ID = "4p20c_Formula1"

    # --- NETWORK HELPER: RETRY SESSION ---
    def get_retry_session(retries=3, backoff_factor=60):
        session = requests.Session()
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=(500, 502, 503, 504, 429),
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    # 2. DATA FETCHING HELPER
    def fetch_jolpica_data(endpoint):
        # If endpoint is empty, it fetches the root current calendar
        url = f"https://api.jolpi.ca/ergast/f1/current/{endpoint}.json" if endpoint else "https://api.jolpi.ca/ergast/f1/current.json"
        try:
            r = get_retry_session().get(url, timeout=20)
            if r.status_code == 200:
                return r.json()
            print(f"❌ API Error: {r.text}")
        except Exception as e:
            print(f"❌ Fetch Error ({endpoint}): {e}")
        return None

    print("🏎️ Fetching F1 Data...")
    
    # 3. EXECUTE API CALLS
    schedule_data = fetch_jolpica_data("")          # Full season schedule (to get total rounds)
    next_race_data = fetch_jolpica_data("next")     # Next upcoming race details
    driver_data = fetch_jolpica_data("driverStandings")
    constructor_data = fetch_jolpica_data("constructorStandings")

    if not next_race_data:
        print("❌ Could not fetch next race data.")
        return

    # --- PROCESS RACE DATA ---
    try:
        race = next_race_data['MRData']['RaceTable']['Races'][0]
        
        # Determine total rounds in the season
        total_rounds = "?"
        if schedule_data:
            total_rounds = schedule_data['MRData']['total']
            
    except (KeyError, IndexError):
        print("⚠️ No upcoming races found in the calendar.")
        return

    season = race.get('season', '2026')
    round_num = race.get('round', '?')
    race_name = race.get('raceName', 'Unknown Grand Prix').upper()
    
    # USE CIRCUIT ID FOR ACCURATE TRACK MAPS (e.g. "MIAMI", "AMERICAS", "MONZA")
    track_id = race['Circuit']['circuitId']
    
    # --- PROCESS EVENTS (Filter, Convert TZ, and Sort) ---
    raw_events = []
    
    # Collect all possible main events
    if 'date' in race and 'time' in race:
        raw_events.append(("Race", race['date'], race['time']))
        
    if 'Qualifying' in race:
        raw_events.append(("Qualifying", race['Qualifying'].get('date'), race['Qualifying'].get('time')))
        
    if 'Sprint' in race:
        raw_events.append(("Sprint", race['Sprint'].get('date'), race['Sprint'].get('time')))
        
    # Jolpica/Ergast API names Sprint Qualifying as either 'SprintShootout' or 'SprintQualifying'
    if 'SprintQualifying' in race:
        raw_events.append(("Sprint Qualifying", race['SprintQualifying'].get('date'), race['SprintQualifying'].get('time')))
    elif 'SprintShootout' in race:
        raw_events.append(("Sprint Qualifying", race['SprintShootout'].get('date'), race['SprintShootout'].get('time')))

    processed_events = []
    for name, date_str, time_str in raw_events:
        if date_str and time_str:
            # Parse UTC Time
            utc_dt = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%SZ")
            utc_dt = utc_dt.replace(tzinfo=datetime.timezone.utc)
            
            # Convert to Pacific Time (Seattle)
            local_dt = utc_dt.astimezone(ZoneInfo("America/Los_Angeles"))
            processed_events.append((name, local_dt))

    # Sort chronologically
    processed_events.sort(key=lambda x: x[1])

    # --- PROCESS STANDINGS (TOP 3) ---
    # WDC Top 3
    wdc_lines = []
    try:
        standings = driver_data['MRData']['StandingsTable']['StandingsLists'][0]['DriverStandings']
        for i in range(min(3, len(standings))):
            first_name = standings[i]['Driver']['givenName']
            last_name = standings[i]['Driver']['familyName']
            points = standings[i]['points']
            wdc_lines.append(f"{i+1}. {first_name} {last_name} - {points}")
        wdc_string = "\n".join(wdc_lines)
    except Exception: 
        wdc_string = "1. TBD - 0\n2. TBD - 0\n3. TBD - 0"

    # WCC Top 3
    wcc_lines = []
    try:
        c_standings = constructor_data['MRData']['StandingsTable']['StandingsLists'][0]['ConstructorStandings']
        for i in range(min(3, len(c_standings))):
            team_name = c_standings[i]['Constructor']['name']
            team_points = c_standings[i]['points']
            wcc_lines.append(f"{i+1}. {team_name} - {team_points}")
        wcc_string = "\n".join(wcc_lines)
    except Exception: 
        wcc_string = "1. TBD - 0\n2. TBD - 0\n3. TBD - 0"

    # 4. DATA MAPPING (LAYOUT DESIGNER)
    pr_data = [""] * 280
    
    # [PR_261] Championship Year
    pr_data[261] = str(season)
    
    # [PR_262] Next Race String
    pr_data[262] = f"{race_name} (Round {round_num} of {total_rounds})"
    
    # [PR_263 to PR_270] Main Events
    # Dynamically loops through the 2 or 4 chronologically sorted main events
    idx = 263
    for event_name, event_dt in processed_events[:4]: # Cap at 4 just in case
        pr_data[idx] = event_name
        # Format: "Fri, 6:00 am". Use %-d and %-I to remove leading zeros
        pr_data[idx+1] = event_dt.strftime("%a, %-I:%M %p").replace("AM", "am").replace("PM", "pm")
        idx += 2
    
    # [PR_271 - PR_272] Standings (Multi-line)
    pr_data[271] = wdc_string
    pr_data[272] = wcc_string
        
    # [PR_273] Layout Visibility Trigger (e.g. "ALBERT_PARK", "MONZA")
    pr_data[273] = track_id
    
    # [PR_274] Timestamp
    now = datetime.datetime.now()
    time_str = now.strftime("%b %-d, %-I:%M %p") if now.minute != 0 else now.strftime("%b %-d, %-I %p")
    pr_data[274] = f"Last updated: {time_str}"

    # 5. PUSH TO GATEWAY
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
            print(f"✅ F1 Tag Updated! (Next Track: {track_id})")
        else:
            print(f"❌ Gateway Error {r.status_code}: {r.text}")
    except Exception as e:
        print(f"❌ Connection Error (Gateway): {e}")