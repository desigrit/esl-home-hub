"""Pure health decisions. A reachable endpoint alone never means a job is healthy."""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

UTC = timezone.utc
PACIFIC = ZoneInfo('America/Los_Angeles')


def now_iso():
    return datetime.now(UTC).isoformat()


def timestamp(value):
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt if dt.tzinfo else dt.replace(tzinfo=PACIFIC)
    except (ValueError, TypeError):
        return None


def age(value, now=None):
    dt = timestamp(value)
    return ((now or datetime.now(UTC)) - dt).total_seconds() if dt else None


def display_health(job, now=None):
    if job.get('running'):
        return 'running', 'Update in progress'
    if not job.get('enabled'):
        return 'paused', 'Scheduled updates are off'
    if not job.get('next_run'):
        return 'error', 'No next update is scheduled'
    if (age(job['next_run'], now) or 0) > 300:
        return 'error', 'A scheduled update is overdue'
    logs = job.get('logs') or []
    if not logs:
        return 'unknown', 'Waiting for the first recorded update'
    latest = logs[0]
    if latest.get('status') == 'Failed':
        return 'error', 'The latest update failed'
    if latest.get('status') in ('Pending', 'Unverified', 'Legacy', 'Skipped'):
        return 'warning', 'The latest delivery is not confirmed'
    if latest.get('status') != 'Success' or not timestamp(latest.get('finished_at')):
        return 'unknown', 'The latest update has no verified result'
    return 'healthy', 'Latest update completed'


def calendar_health(data, now=None):
    now = now or datetime.now(UTC)
    if data.get('error') or data.get('device_error'):
        return 'error', data.get('error') or data['device_error']
    if not data.get('google_connected'):
        return 'warning', 'Connect Google Calendar in Settings'
    if data.get('holiday_error'):
        return 'warning', data['holiday_error']
    fetched = age(data.get('fetched_at'), now)
    if fetched is None or fetched > 26 * 3600:
        return 'warning', 'Calendar data is overdue for a refresh'
    seen = data.get('device_seen') or {}
    acknowledged = age(seen.get('seen_at'), now)
    if acknowledged is None:
        return 'unknown', 'The Note has not confirmed a display update'
    if acknowledged > 26 * 3600:
        return 'warning', 'The Note has not checked in for over 26 hours'
    return 'healthy', 'Calendar ready; Note sleeps between updates'


def insignia_health(data, now=None):
    now = now or datetime.now(UTC)
    if data.get('paused'):
        return 'error', data.get('paused')
    if data.get('delivery_paused') or data.get('blocked'):
        return 'error', 'Notification delivery needs attention'
    if data.get('health_state') == 'down' or data.get('scan_failures', 0) >= 3:
        return 'error', data.get('last_failure_reason') or 'Repeated Facebook checks have failed'
    if data.get('timer_active') is False:
        return 'paused', 'Scheduled Facebook checks are paused'
    if data.get('scan_failures', 0) or data.get('health_state') == 'recovering':
        return 'warning', data.get('last_failure_reason') or 'Monitoring is recovering'
    checkpoint_age = age(data.get('checkpoint'), now)
    if data.get('active_now') is False:
        return 'sleeping', 'Outside the 6 a.m. to 10 p.m. monitoring window'
    if checkpoint_age is None or checkpoint_age > 20 * 60:
        return 'warning', 'No completed Facebook scan in the last 20 minutes'
    return 'healthy', 'Checking the group every five minutes'


def reddit_health(data, now=None):
    if data.get('resolved'):
        return 'healthy', 'Account reinstatement recorded'
    state = data.get('workflow_state') or {}
    if state.get('blocked'):
        return 'error', 'Appeal receipt unconfirmed. Review before another attempt.'
    if data.get('automation_status') == 'PAUSED':
        return 'paused', 'The appeal workflow is paused'
    if state.get('validation_pending'):
        return 'warning', 'One validation attempt is awaiting its scheduled time'
    if data.get('automation_status') != 'ACTIVE':
        return 'unknown', 'The scheduled workflow state is unavailable'
    target = data.get('next_scheduled_local')
    if not target or (age(target, now) or 0) > 3600:
        return 'warning', 'Check the next scheduled appeal time'
    return 'healthy', 'Waiting for the next eligible appeal window'


def aggregate(states):
    for state in ('offline', 'error', 'warning', 'unknown', 'running'):
        if state in states:
            return state
    return 'healthy'
