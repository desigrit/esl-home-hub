"""Microsoft To Do controller for the 4.2-inch Rainus shelf label.

The Rainus layout is intentionally kept separate from the data contract. This
controller publishes enough information for an all-lists overview, a global
task queue, or a focused single-list layout without fetching Microsoft Graph a
second time.

PR register contract for ``4p20c_Todo``:

    150-159  date, update stamp, totals, and layout density state
    160-191  eight list rows, four registers per row
    192-199  focused-list and overflow metadata
    200-223  six prioritized cross-list task rows
    224-247  six task rows from the focused list
    248-249  contract version and display mode

Task titles and list names are never written to stdout because controller
output is retained in ``logs.json`` and rendered by the management dashboard.
"""

import datetime
import re
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from todo_service import MicrosoftTodoService, build_todo_view


LAYOUT_ID = "4p20c_Todo"
PR_SIZE = 250

PR_DAY = 150
PR_MONTH = 151
PR_WEEKDAY = 152
PR_UPDATED = 153
PR_STATE = 154
PR_ACTIVE_TOTAL = 155
PR_LIST_TOTAL = 156
PR_ACTIVE_LISTS = 157
PR_EMPTY_LISTS = 158
PR_LIST_OVERFLOW = 159

LIST_START = 160
LIST_STRIDE = 4
LIST_SLOTS = 8

PR_FOCUS_NAME = 192
PR_FOCUS_POSITION = 193
PR_FOCUS_COUNT = 194
PR_FOCUS_OVERFLOW = 195
PR_GLOBAL_OVERFLOW = 196
PR_DUE_TODAY = 197
PR_OVERDUE = 198
PR_EMPTY_MESSAGE = 199

GLOBAL_TASK_START = 200
FOCUS_TASK_START = 224
TASK_STRIDE = 4
TASK_SLOTS = 6

PR_CONTRACT_VERSION = 248
PR_DISPLAY_MODE = 249

_SPACE = re.compile(r"\s+")


def _session(retries=3, backoff_factor=2):
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _limit(value, maximum):
    text = _SPACE.sub(" ", str(value or "")).strip()
    if len(text) <= maximum:
        return text
    return text[: max(0, maximum - 3)].rstrip() + "..."


def _updated_label(now):
    hour = now.hour % 12 or 12
    meridiem = "AM" if now.hour < 12 else "PM"
    clock = (
        f"{hour} {meridiem}"
        if now.minute == 0
        else f"{hour}:{now.minute:02d} {meridiem}"
    )
    return f"Last updated: {now.strftime('%b')} {now.day}, {clock}"


def _tone(task):
    if task.get("due_tone") == "overdue":
        return "3"
    if task.get("due_tone") == "today":
        return "2"
    if task.get("importance") == "high":
        return "1"
    return "0"


def _task_meta(task):
    parts = []
    if task.get("due_label"):
        parts.append(task["due_label"])
    if task.get("importance") == "high":
        parts.append("High priority")
    if task.get("has_recurrence"):
        parts.append("Repeats")
    return " | ".join(parts)


def _task_sort_key(item):
    task = item["task"]
    tone_order = {"3": 0, "2": 1, "1": 2, "0": 3}
    due_date = task.get("due_date") or datetime.date.max
    return (
        tone_order[_tone(task)],
        due_date,
        item["list_index"],
        task.get("title", "").casefold(),
    )


def _list_tone(task_list):
    tones = {_tone(task) for task in task_list.get("active_tasks", [])}
    for tone in ("3", "2", "1"):
        if tone in tones:
            return tone
    return "0"


def _clamped_setting(config, key, default, maximum):
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(1, min(maximum, value))


def build_pr_data(todo, *, now=None, config=None):
    """Build the stable Rainus register array from ``build_todo_view`` output."""
    now = now or datetime.datetime.now().astimezone()
    config = config or {}
    max_lists = _clamped_setting(config, "max_lists", LIST_SLOTS, LIST_SLOTS)
    max_tasks = _clamped_setting(config, "max_tasks", TASK_SLOTS, TASK_SLOTS)

    all_lists = todo.get("lists", [])
    active_lists = [task_list for task_list in all_lists if task_list["active_tasks"]]
    empty_list_count = len(all_lists) - len(active_lists)

    pr = [""] * PR_SIZE
    pr[PR_DAY] = str(now.day)
    pr[PR_MONTH] = now.strftime("%B").lower()
    pr[PR_WEEKDAY] = now.strftime("%A").lower()
    pr[PR_UPDATED] = _updated_label(now)
    pr[PR_STATE] = (
        "0"
        if not active_lists
        else "1"
        if len(active_lists) <= 4
        else "2"
        if len(active_lists) <= max_lists
        else "3"
    )
    pr[PR_ACTIVE_TOTAL] = str(todo.get("active_count", 0))
    pr[PR_LIST_TOTAL] = str(len(all_lists))
    pr[PR_ACTIVE_LISTS] = str(len(active_lists))
    pr[PR_EMPTY_LISTS] = str(empty_list_count)
    pr[PR_LIST_OVERFLOW] = str(max(0, len(active_lists) - max_lists))

    flattened = []
    for list_index, task_list in enumerate(active_lists):
        for task in task_list["active_tasks"]:
            flattened.append({
                "list_index": list_index,
                "list_name": task_list["name"],
                "task": task,
            })

    for slot, task_list in enumerate(active_lists[:max_lists]):
        base = LIST_START + slot * LIST_STRIDE
        tasks = task_list["active_tasks"]
        pr[base] = _limit(task_list["name"], 26)
        pr[base + 1] = str(len(tasks))
        pr[base + 2] = _limit(tasks[0]["title"], 38)
        pr[base + 3] = _list_tone(task_list)

    focus_index = 0
    if active_lists:
        try:
            requested_index = int(config.get("focus_list_index", 0))
        except (TypeError, ValueError):
            requested_index = 0
        focus_index = requested_index % len(active_lists)
        focus = active_lists[focus_index]
        focus_tasks = focus["active_tasks"]
        pr[PR_FOCUS_NAME] = _limit(focus["name"], 32)
        pr[PR_FOCUS_POSITION] = f"{focus_index + 1} of {len(active_lists)}"
        pr[PR_FOCUS_COUNT] = str(len(focus_tasks))
        pr[PR_FOCUS_OVERFLOW] = str(max(0, len(focus_tasks) - max_tasks))
    else:
        focus_tasks = []
        pr[PR_EMPTY_MESSAGE] = "All lists are clear"

    flattened.sort(key=_task_sort_key)
    pr[PR_GLOBAL_OVERFLOW] = str(max(0, len(flattened) - max_tasks))
    pr[PR_DUE_TODAY] = str(todo.get("due_today_count", 0))
    pr[PR_OVERDUE] = str(todo.get("overdue_count", 0))

    for slot, item in enumerate(flattened[:max_tasks]):
        base = GLOBAL_TASK_START + slot * TASK_STRIDE
        task = item["task"]
        pr[base] = _limit(task["title"], 42)
        pr[base + 1] = _limit(item["list_name"], 22)
        pr[base + 2] = _limit(_task_meta(task), 24)
        pr[base + 3] = _tone(task)

    for slot, task in enumerate(focus_tasks[:max_tasks]):
        base = FOCUS_TASK_START + slot * TASK_STRIDE
        pr[base] = _limit(task["title"], 46)
        pr[base + 1] = _limit(_task_meta(task), 28)
        pr[base + 2] = _tone(task)
        pr[base + 3] = "R" if task.get("has_recurrence") else ""

    pr[PR_CONTRACT_VERSION] = "1"
    pr[PR_DISPLAY_MODE] = str(config.get("display_mode", "overview"))
    return pr


def run(full_config, *, service=None, session=None, now=None):
    system = full_config["system"]
    config = full_config.get("todo", {})

    tag_id = str(config.get("tag_id", "")).strip()
    if not tag_id:
        raise ValueError("Set todo.tag_id before running the Microsoft To Do display.")

    layout_id = str(config.get("layout_id", LAYOUT_ID)).strip() or LAYOUT_ID
    now = now or datetime.datetime.now().astimezone()

    print("Fetching Microsoft To Do lists and tasks...")
    todo_service = service or MicrosoftTodoService(config)
    snapshot = todo_service.get_snapshot(force=True)
    todo = build_todo_view(snapshot, today=now.date())
    pr_data = build_pr_data(todo, now=now, config=config)

    print(
        f"Prepared {todo['active_count']} active task(s) across "
        f"{sum(1 for item in todo['lists'] if item['active_tasks'])} active list(s)."
    )

    payload = {
        "storeCode": system["store_code"],
        "taskId": str(int(time.time())),
        "product": [{
            "prCode": tag_id,
            "layoutId": layout_id,
            "prInfo": pr_data,
            "nfc": "",
        }],
    }

    request_session = session or _session()
    response = request_session.post(
        f"http://{system['gateway_ip']}/api/product",
        json=payload,
        timeout=int(config.get("gateway_timeout_seconds", 20)),
    )
    if response.status_code != 200:
        raise RuntimeError(f"Gateway returned HTTP {response.status_code}.")

    print("Microsoft To Do tag updated.")
    return pr_data
