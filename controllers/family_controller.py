"""
PROJECT: ESL Hub (Electronic Shelf Label Dashboard)
MODULE: Family Calendar Controller
AUTHOR: Raunak Oberoi
DATE: Aug 2026

DESCRIPTION:
Pulls events from one or more Google Calendars and renders them onto the
4p20c_SharedCalendar layout: today's events at the top, then what is coming up.

Authenticates as a service account, so there is no browser consent and no
refresh token to expire. Share each calendar with the service account's email
address (Calendar settings -> Share with specific people -> "See all event
details") and it will appear in the list.

Uses only requests, PyJWT and cryptography, all of which are already on the Pi,
so nothing needs installing.

The layout is responsive. PR_154 carries a clamped state code rather than a raw
count, so the layout never has to cast or clamp:

    '1'  0-2 events today   divider up,      4 upcoming rows
    '2'  3 events today     divider default, 3 upcoming rows
    '3'  4+ events today    divider down,    2 upcoming rows

Dot colour is derived by the layout from each row's own name and time fields:
red for an all-day event, black for one with a start time, hidden when empty.

CLI helpers, run from the esl_hub directory:
    python3 controllers/family_controller.py --list-calendars
    python3 controllers/family_controller.py --dry-run
"""

import datetime
import json
import os
import sys
import time

import jwt
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from zoneinfo import ZoneInfo
except ImportError:                                   # pragma: no cover
    from backports.zoneinfo import ZoneInfo

LAYOUT_ID = "4p20c_SharedCalendar"

TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"
SCOPE = "https://www.googleapis.com/auth/calendar.readonly"

# ---- PR map, matching 4p20c_SharedCalendar --------------------------------
PR_DAY, PR_MONTH, PR_WEEKDAY, PR_UPDATED, PR_STATE = 150, 151, 152, 153, 154
TODAY_SLOTS = [(160, 161), (162, 163), (164, 165), (166, 167)]      # name, time
UPCOMING_SLOTS = [(170, 171, 172), (173, 174, 175),
                  (176, 177, 178), (179, 180, 181)]                 # date, name, time
PR_SIZE = 250

MAX_TODAY = len(TODAY_SLOTS)
MAX_UPCOMING = len(UPCOMING_SLOTS)

_token_cache = {}


# --------------------------------------------------------------------------
# plumbing
# --------------------------------------------------------------------------
def _session(retries=3, backoff_factor=2):
    session = requests.Session()
    retry = Retry(total=retries, read=retries, connect=retries,
                  backoff_factor=backoff_factor,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=["HEAD", "GET", "OPTIONS", "POST"])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _load_key(path):
    if not os.path.isabs(path):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, path)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Service account key not found at {path}. Download the JSON key from "
            f"Google Cloud and drop it there, then share each calendar with its "
            f"client_email.")
    with open(path, "r") as f:
        key = json.load(f)
    for field in ("client_email", "private_key"):
        if field not in key:
            raise ValueError(f"{path} is missing '{field}'. Is it a service account key?")
    return key


def _access_token(key):
    """Sign a JWT with the service account key and swap it for an access token."""
    email = key["client_email"]
    cached = _token_cache.get(email)
    if cached and cached["expires_at"] > time.time() + 60:
        return cached["token"]

    now = int(time.time())
    assertion = jwt.encode(
        {"iss": email, "scope": SCOPE, "aud": TOKEN_URL, "iat": now, "exp": now + 3600},
        key["private_key"], algorithm="RS256",
    )
    r = _session().post(
        TOKEN_URL, timeout=20,
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
              "assertion": assertion})
    if r.status_code != 200:
        raise RuntimeError(f"Google token request failed {r.status_code}: {r.text[:300]}")
    body = r.json()
    _token_cache[email] = {"token": body["access_token"],
                           "expires_at": now + int(body.get("expires_in", 3600))}
    return body["access_token"]


def _get(token, path, params=None):
    r = _session().get(f"{CALENDAR_API}{path}", timeout=20, params=params or {},
                       headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        raise RuntimeError(f"Calendar API {path} failed {r.status_code}: {r.text[:300]}")
    return r.json()


def list_calendars(token):
    """Note: sharing a calendar with a service account grants access but does NOT
    create an entry in the service account's own calendarList, so this usually
    comes back empty. Use check_calendar() with an explicit ID instead."""
    out, page = [], None
    while True:
        params = {"maxResults": 250}
        if page:
            params["pageToken"] = page
        body = _get(token, "/users/me/calendarList", params)
        out.extend(body.get("items", []))
        page = body.get("nextPageToken")
        if not page:
            break
    return out


def check_calendar(token, calendar_id):
    """Confirm the service account can actually read a calendar, by ID."""
    meta = _get(token, f"/calendars/{requests.utils.quote(calendar_id, safe='')}")
    now = datetime.datetime.now(datetime.timezone.utc)
    body = _get(token, f"/calendars/{requests.utils.quote(calendar_id, safe='')}/events",
                {"timeMin": now.isoformat(), "singleEvents": "true",
                 "orderBy": "startTime", "maxResults": 5})
    return meta, body.get("items", [])


def fetch_events(token, calendar_id, time_min, time_max):
    """singleEvents expands recurrences server-side, which is what makes yearly
    birthdays and anniversaries land on the right date without any RRULE work."""
    out, page = [], None
    while True:
        params = {"timeMin": time_min.isoformat(), "timeMax": time_max.isoformat(),
                  "singleEvents": "true", "orderBy": "startTime", "maxResults": 250}
        if page:
            params["pageToken"] = page
        body = _get(token, f"/calendars/{requests.utils.quote(calendar_id, safe='')}/events",
                    params)
        out.extend(body.get("items", []))
        page = body.get("nextPageToken")
        if not page:
            break
    return out


# --------------------------------------------------------------------------
# pure logic, unit testable without a network
# --------------------------------------------------------------------------
def normalise(event, tz):
    """Flatten a Google event into {name, start, all_day} in local time."""
    if event.get("status") == "cancelled":
        return None
    name = (event.get("summary") or "").strip()
    if not name:
        return None

    start = event.get("start") or {}
    if "date" in start:
        d = datetime.date.fromisoformat(start["date"])
        return {"name": name, "date": d, "start": None, "all_day": True}
    if "dateTime" in start:
        dt = datetime.datetime.fromisoformat(start["dateTime"]).astimezone(tz)
        return {"name": name, "date": dt.date(), "start": dt, "all_day": False}
    return None


def fmt_time(dt):
    """9:30p / 7:00a, matching the layout's sample text."""
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.minute:02d}{'a' if dt.hour < 12 else 'p'}"


def fmt_date(d):
    """Wed 31 Sep."""
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


def fmt_updated(now):
    """House format, matching the other five controllers: "Aug 3, 2:43 AM",
    dropping the minutes when it lands on the hour. Written out rather than
    using %-d/%-I so it does not depend on a glibc strftime."""
    hour = now.hour % 12 or 12
    meridiem = "AM" if now.hour < 12 else "PM"
    clock = f"{hour} {meridiem}" if now.minute == 0 else f"{hour}:{now.minute:02d} {meridiem}"
    return f"Last updated: {now.strftime('%b')} {now.day}, {clock}"


def sort_key(ev):
    """All-day events lead the day, then timed events in chronological order."""
    return (0, 0, 0) if ev["all_day"] else (1, ev["start"].hour, ev["start"].minute)


def split_events(events, today):
    todays = sorted([e for e in events if e["date"] == today], key=sort_key)
    upcoming = sorted([e for e in events if e["date"] > today],
                      key=lambda e: (e["date"], sort_key(e)))
    return todays, upcoming


def collapse_repeats(events):
    """Keep only the next occurrence of each distinct event name.

    Off by default. Turn on with "collapse_repeats": true if a weekly recurrence
    starts swamping the upcoming list. Assumes the list is already sorted, so the
    first occurrence seen is the soonest."""
    out, seen = [], set()
    for ev in events:
        key = ev["name"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
    return out


def layout_state(today_count):
    if today_count <= 2:
        return "1"
    return "2" if today_count == 3 else "3"


def build_pr_data(todays, upcoming, now):
    pr = [""] * PR_SIZE

    pr[PR_DAY] = str(now.day)
    pr[PR_MONTH] = now.strftime("%B").lower()
    pr[PR_WEEKDAY] = now.strftime("%A").lower()
    pr[PR_UPDATED] = fmt_updated(now)
    pr[PR_STATE] = layout_state(len(todays))

    for ev, (pr_name, pr_time) in zip(todays[:MAX_TODAY], TODAY_SLOTS):
        pr[pr_name] = ev["name"]
        pr[pr_time] = "" if ev["all_day"] else fmt_time(ev["start"])

    for ev, (pr_date, pr_name, pr_time) in zip(upcoming[:MAX_UPCOMING], UPCOMING_SLOTS):
        pr[pr_date] = fmt_date(ev["date"])
        pr[pr_name] = ev["name"]
        pr[pr_time] = "" if ev["all_day"] else fmt_time(ev["start"])

    return pr


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def collect(cfg):
    """Fetch and split events. Returns (todays, upcoming, now)."""
    tz = ZoneInfo(cfg.get("timezone", "America/Los_Angeles"))
    now = datetime.datetime.now(tz)
    today = now.date()

    key = _load_key(cfg.get("service_account_file",
                            "controllers/data/google_service_account.json"))
    token = _access_token(key)

    calendar_ids = cfg.get("calendar_ids") or []
    if not calendar_ids:
        raise ValueError(
            "No calendar_ids configured. Run "
            "'python3 controllers/family_controller.py --list-calendars' to see what the "
            "service account can read.")

    time_min = datetime.datetime.combine(today, datetime.time.min, tzinfo=tz)
    time_max = time_min + datetime.timedelta(days=int(cfg.get("upcoming_days", 120)))

    events, seen = [], set()
    for cal_id in calendar_ids:
        raw = fetch_events(token, cal_id, time_min, time_max)
        kept = 0
        for item in raw:
            ev = normalise(item, tz)
            if not ev:
                continue
            fingerprint = (ev["name"], ev["date"], ev["all_day"],
                           ev["start"].isoformat() if ev["start"] else "")
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            events.append(ev)
            kept += 1
        print(f"   {cal_id}: {kept} events")

    todays, upcoming = split_events(events, today)
    if cfg.get("collapse_repeats", False):
        before = len(upcoming)
        upcoming = collapse_repeats(upcoming)
        if before != len(upcoming):
            print(f"   collapsed {before - len(upcoming)} repeat occurrence(s) in upcoming")
    return todays, upcoming, now


def run(full_config):
    sys_cfg = full_config["system"]
    cfg = full_config.get("family", {})

    gateway_ip = sys_cfg["gateway_ip"]
    store_code = sys_cfg["store_code"]
    tag_id = cfg["tag_id"]

    print("📅 Fetching Google Calendar events...")
    todays, upcoming, now = collect(cfg)

    state = layout_state(len(todays))
    print(f"   today: {len(todays)} event(s) -> layout state {state}")
    if len(todays) > MAX_TODAY:
        print(f"   ⚠️  {len(todays) - MAX_TODAY} of today's events will not fit and are dropped")

    pr_data = build_pr_data(todays, upcoming, now)

    payload = {
        "storeCode": store_code,
        "taskId": str(int(time.time())),
        "product": [{
            "prCode": tag_id,
            "layoutId": LAYOUT_ID,
            "prInfo": pr_data,
            "nfc": "",
        }],
    }

    r = _session().post(f"http://{gateway_ip}/api/product", json=payload, timeout=20)
    if r.status_code == 200:
        headline = todays[0]["name"] if todays else "nothing on today"
        print(f"✅ Family Calendar Tag Updated! ({headline})")
    else:
        raise RuntimeError(f"Gateway Error {r.status_code}: {r.text[:300]}")


def _cli():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "config.json")) as f:
        full_config = json.load(f)
    cfg = full_config.get("family", {})

    if "--list-calendars" in sys.argv:
        token = _access_token(_load_key(cfg.get(
            "service_account_file", "controllers/data/google_service_account.json")))
        cals = list_calendars(token)
        if not cals:
            print("No calendars in the service account's own list.\n"
                  "That is normal and expected: sharing a calendar with a service\n"
                  "account grants access but never adds it to the account's list,\n"
                  "because nothing on that side ever accepts the share.\n\n"
                  "Get the ID from the browser instead:\n"
                  "  Google Calendar -> the calendar -> Settings and sharing\n"
                  "  -> Integrate calendar -> Calendar ID\n\n"
                  "Then verify it with:\n"
                  "  python3 controllers/family_controller.py --check <calendar_id>")
            return
        print(f"{len(cals)} calendar(s) in the service account's list:\n")
        for c in cals:
            print(f"  {c.get('summary')}")
            print(f"    id: {c['id']}")
        return

    if "--check" in sys.argv:
        cal_id = sys.argv[sys.argv.index("--check") + 1]
        token = _access_token(_load_key(cfg.get(
            "service_account_file", "controllers/data/google_service_account.json")))
        meta, items = check_calendar(token, cal_id)
        print(f"✅ readable: {meta.get('summary')!r}  ({meta.get('timeZone')})")
        print(f"   next {len(items)} event(s):")
        for it in items:
            start = it.get("start", {})
            when = start.get("date") or start.get("dateTime", "")
            print(f"     {when}  {it.get('summary')}")
        return

    if "--dry-run" in sys.argv:
        todays, upcoming, now = collect(cfg)
        pr = build_pr_data(todays, upcoming, now)
        print(f"\nlayout state: {pr[PR_STATE]}   today: {len(todays)}   upcoming: {len(upcoming)}")
        for i, v in enumerate(pr):
            if v != "":
                print(f"  PR_{i} = {v!r}")
        return

    run(full_config)


if __name__ == "__main__":
    _cli()
