import requests
import datetime
import time

def run(full_config):
    # 1. READ CONFIG
    sys = full_config['system']
    cfg = full_config['dota']
    
    STEAM_ID = cfg['steam_id']
    START_MMR = int(cfg['baseline_mmr'])
    START_MATCH_ID = int(cfg['baseline_match_id'])
    TARGET_MMR = int(cfg['target_mmr'])
    
    # Layout & Pixel Config
    MAIN_BAR_PIXEL_WIDTH = int(cfg.get('main_bar_width', 300))
    SPLIT_BAR_SIDE_WIDTH = int(cfg.get('split_bar_width', 98))
    
    GATEWAY_IP = sys['gateway_ip']
    STORE_CODE = sys['store_code']
    TAG_ID = cfg['tag_id']
    LAYOUT_ID = "4p20c_Dota"

    # 2. HELPER FUNCTIONS
    def get_hero_dict():
        try:
            r = requests.get("https://api.opendota.com/api/heroes")
            if r.status_code == 200:
                return {h['id']: h['localized_name'] for h in r.json()}
        except: return {}
        return {}

    def fetch_matches():
        print(f"⚔️ Fetching Dota 2 Matches for {STEAM_ID}...")
        url = f"https://api.opendota.com/api/players/{STEAM_ID}/matches?limit=100&lobby_type=7"
        try:
            r = requests.get(url)
            if r.status_code == 200:
                return r.json()
            print(f"❌ API Error: {r.text}")
        except Exception as e:
            print(f"❌ Connection Error: {e}")
        return []

    # 3. EXECUTION
    heroes = get_hero_dict()
    matches = fetch_matches()
    if not matches: return

    # --- CALC STATS ---
    now = datetime.datetime.now()
    mmr_delta = 0
    recent_20 = []
    last_7_days = []
    last_1_mo = []
    
    for m in matches:
        is_radiant = m['player_slot'] < 128
        radiant_win = m['radiant_win']
        is_win = (is_radiant and radiant_win) or (not is_radiant and not radiant_win)
        m['is_win'] = is_win 
        
        match_id = m['match_id']
        match_dt = datetime.datetime.fromtimestamp(m['start_time'])
        
        if match_id > START_MATCH_ID:
            mmr_delta += 25 if is_win else -25
            
        recent_20.append(m) 
        if (now - match_dt).days <= 7:
            last_7_days.append(m)
        if (now - match_dt).days <= 30:
            last_1_mo.append(m)

    recent_20 = recent_20[:20]

    current_mmr = START_MMR + mmr_delta
    mmr_needed = max(0, TARGET_MMR - current_mmr)
    wins_needed = int(mmr_needed / 25)
    wins_needed_str = f"+{wins_needed}"
    
    def get_stat_str(match_list):
        if not match_list: return "0-0", "0%", 0
        wins = sum(1 for x in match_list if x['is_win'])
        losses = len(match_list) - wins
        if len(match_list) == 0: return "0-0", "0%", 0
        win_pct = int((wins / len(match_list)) * 100)
        return f"{wins}-{losses}", f"{win_pct}%", win_pct

    w_20, p_20, pct_20 = get_stat_str(recent_20)
    w_7,  p_7,  pct_7  = get_stat_str(last_7_days)
    w_30, p_30, pct_30 = get_stat_str(last_1_mo)

    last = matches[0]
    hero_name = heroes.get(last['hero_id'], "Unknown")
    res = "WIN" if last['is_win'] else "LOSS"
    kda = f"{last['kills']}-{last['deaths']}-{last['assists']}"
    last_match_str = f"{hero_name} ({kda}) - {res}"

    # --- BARS ---
    bracket_base = 4620
    bracket_top = 5650
    bracket_range = bracket_top - bracket_base
    prog_raw = (current_mmr - bracket_base) / bracket_range
    main_bar_w = int(max(0, min(1, prog_raw)) * MAIN_BAR_PIXEL_WIDTH)
    
    def get_split_widths(pct):
        diff = pct - 50 
        ratio = abs(diff) / 50.0 
        width = int(ratio * SPLIT_BAR_SIDE_WIDTH)
        if diff < 0: return str(width), "0"
        else:        return "0", str(width)

    l_20, r_20 = get_split_widths(pct_20)
    l_7,  r_7  = get_split_widths(pct_7)
    l_30, r_30 = get_split_widths(pct_30)

    # --- PAYLOAD ---
    pr_data = [""] * 250
    pr_data[200] = "Divine IV"     
    pr_data[201] = str(current_mmr)
    pr_data[202] = wins_needed_str
    pr_data[203] = w_20
    pr_data[204] = p_20
    pr_data[205] = w_7
    pr_data[206] = p_7
    pr_data[207] = w_30
    pr_data[208] = p_30
    pr_data[209] = last_match_str
    pr_data[210] = str(main_bar_w)
    pr_data[220] = l_20 
    pr_data[221] = r_20 
    pr_data[222] = l_7  
    pr_data[223] = r_7  
    pr_data[224] = l_30 
    pr_data[225] = r_30
    pr_data[226] = datetime.datetime.now().strftime("Last updated: %b %-d, %-I:%M %p") 

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
        requests.post(f"http://{GATEWAY_IP}/api/product", json=payload)
        print(f"🚀 Dota Tag Updated! MMR: {pr_data[201]}")
    except Exception as e:
        print(f"❌ Gateway Error: {e}")