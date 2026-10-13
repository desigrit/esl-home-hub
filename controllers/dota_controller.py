"""
PROJECT: ESL Hub
MODULE: Dota 2 Controller
AUTHOR: Raunak Oberoi
DATE: Jan 2026

DESCRIPTION:
Tracks Dota 2 MMR progress and Win Rates.
Displays a main progress bar (MMR) and 3 "Split Bars" for recent performance.

KEY FEATURES:
- Calculates MMR gain/loss relative to a 'Baseline Match ID'.
- [UPDATED] Zoomed Sensitivity: Split bars now max out at +/- 20% deviation.
  This makes small win rate changes (e.g., 52%) much more visible.
"""

import requests
import datetime
import time
import math
from gateway import publish
from http_client import retry_session, request_json
from runtime import JobSkipped, updated_label


def fetch_ranked_matches(session, steam_id, baseline, now, *, max_pages=50):
    matches = {}
    cutoff = now.timestamp() - 30 * 86400
    for page in range(max_pages):
        batch = request_json(session, 'GET', f'https://api.opendota.com/api/players/{steam_id}/matches',
                             label='OpenDota matches', params={'limit': 100, 'offset': page * 100, 'lobby_type': 7})
        if not isinstance(batch, list) or any(not isinstance(item, dict) or not {'match_id', 'start_time', 'player_slot', 'radiant_win'} <= item.keys() for item in batch):
            raise RuntimeError('OpenDota returned invalid match data.')
        if batch and all(item['match_id'] in matches for item in batch):
            raise RuntimeError('OpenDota repeated a page. Refusing to publish an incomplete MMR estimate.')
        matches.update((item['match_id'], item) for item in batch)
        if len(batch) < 100 or (min(item['match_id'] for item in batch) <= baseline and min(item['start_time'] for item in batch) <= cutoff):
            return sorted(matches.values(), key=lambda item: item['match_id'], reverse=True)
    raise RuntimeError('OpenDota history limit reached before the baseline. Increase dota.max_history_pages or choose a newer baseline.')

def run(full_config):
    # 1. READ CONFIG
    sys = full_config['system']
    cfg = full_config['dota']
    
    STEAM_ID = cfg['steam_id']
    START_MMR = int(cfg['baseline_mmr'])
    START_MATCH_ID = int(cfg['baseline_match_id'])
    TARGET_MMR = int(cfg['target_mmr'])
    if START_MATCH_ID <= 0 or START_MMR <= 0 or TARGET_MMR <= 0:
        raise ValueError('Set a valid Dota baseline match, baseline MMR, and target MMR.')
    
    # Layout & Pixel Config
    MAIN_BAR_PIXEL_WIDTH = int(cfg.get('main_bar_width', 300))
    SPLIT_BAR_SIDE_WIDTH = int(cfg.get('split_bar_width', 98))
    
    # [NEW] SENSITIVITY CONFIG
    # 20 means the bar fills up completely if winrate is +/- 20% from 50%
    # (i.e., Winrate > 70% is Full Black, Winrate < 30% is Full Red)
    SENSITIVITY = 20.0 
    
    GATEWAY_IP = sys['gateway_ip']
    STORE_CODE = sys['store_code']
    TAG_ID = cfg['tag_id']
    LAYOUT_ID = "4p20c_Dota"

    # --- NETWORK HELPER: RETRY SESSION ---
    def get_retry_session():
        return retry_session()

    # 2. HELPER FUNCTIONS
    def get_hero_dict():
        try:
            with get_retry_session() as session:
                r = session.get("https://api.opendota.com/api/heroes", timeout=20)
                if r.status_code == 200:
                    return {h['id']: h['localized_name'] for h in r.json()}
        except Exception as e:
            print(f"⚠️ Hero Fetch Warning: {e}")
        return {}

    def fetch_matches():
        print(f"⚔️ Fetching Dota 2 Matches for {STEAM_ID}...")
        with get_retry_session() as session:
            return fetch_ranked_matches(session, STEAM_ID, START_MATCH_ID, datetime.datetime.now(),
                                        max_pages=max(1, min(100, int(cfg.get('max_history_pages', 50)))))

    # 3. EXECUTION
    heroes = get_hero_dict()
    matches = fetch_matches()
    if not matches:
        raise JobSkipped('OpenDota returned no ranked matches; the previous tag data was preserved.')
    print(f'Loaded {len(matches)} ranked matches through the baseline and 30-day window.')

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
        
        # MMR Calculation: Assume +/- 25 per ranked game since baseline
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
    wins_needed = math.ceil(mmr_needed / 25)
    wins_needed_str = f"+{wins_needed}"
    
    def get_stat_str(match_list):
        # Return None for the int value if list is empty
        if not match_list: return "0-0", "0%", None 
        wins = sum(1 for x in match_list if x['is_win'])
        losses = len(match_list) - wins
        if len(match_list) == 0: return "0-0", "0%", None
        
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

    # --- VISUAL BAR CALCULATIONS ---
    # 1. Main MMR Bar (Progress to Immortal)
    bracket_base = int(cfg.get('bracket_base', 5622))
    bracket_top = TARGET_MMR
    if bracket_top <= bracket_base:
        raise ValueError('Dota target MMR must exceed the progress bar baseline.')
    bracket_range = bracket_top - bracket_base
    prog_raw = (current_mmr - bracket_base) / bracket_range
    main_bar_w = int(max(0, min(1, prog_raw)) * MAIN_BAR_PIXEL_WIDTH)
    
    # 2. Split Bars (Win Rate) - ZOOMED LOGIC
    def get_split_widths(pct):
        if pct is None: return "0", "0"
        
        diff = pct - 50 
        
        # Logic: Calculate ratio against SENSITIVITY instead of 50
        # Example: 55% Winrate -> Diff 5. Ratio = 5/20 = 0.25 (25% bar width)
        ratio = abs(diff) / SENSITIVITY
        
        # Clamp ratio to 1.0 (100%) so we don't overflow pixels
        ratio = min(1.0, ratio)
        
        width = int(ratio * SPLIT_BAR_SIDE_WIDTH)
        
        if diff < 0: return str(width), "0"  # Left (Red) Active
        else:        return "0", str(width)  # Right (Black) Active

    l_20, r_20 = get_split_widths(pct_20)
    l_7,  r_7  = get_split_widths(pct_7)
    l_30, r_30 = get_split_widths(pct_30)

    # --- DATA MAPPING (LAYOUT DESIGNER) ---
    pr_data = [""] * 250
    pr_data[200] = "Immortal"     
    pr_data[201] = str(current_mmr)
    pr_data[202] = wins_needed_str
    
    # Stats Text (Wins-Losses, Pct)
    pr_data[203] = w_20
    pr_data[204] = p_20
    pr_data[205] = w_7
    pr_data[206] = p_7
    pr_data[207] = w_30
    pr_data[208] = p_30
    pr_data[209] = last_match_str
    pr_data[210] = str(main_bar_w) # Main Bar Width
    
    # SPLIT BAR WIDTHS
    pr_data[220] = l_20 
    pr_data[221] = r_20 
    pr_data[222] = l_7  
    pr_data[223] = r_7  
    pr_data[224] = l_30 
    pr_data[225] = r_30
    
    # Timestamp
    pr_data[226] = updated_label(now)

    payload = {
        "storeCode": STORE_CODE,
        "product": [{
            "prCode": TAG_ID,
            "layoutId": LAYOUT_ID,
            "prInfo": pr_data,
            "nfc": ""
        }]
    }
    
    publish(sys, payload)
    print(f"Dota tag updated. Estimated MMR: {pr_data[201]}")
