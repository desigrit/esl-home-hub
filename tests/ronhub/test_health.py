from datetime import datetime, timezone, timedelta
import pytest
from ronhub.health import aggregate, calendar_health, display_health, insignia_health, reddit_health

NOW = datetime(2026, 10, 30, 4, 0, tzinfo=timezone.utc)
def iso(delta=0): return (NOW + timedelta(seconds=delta)).isoformat()

def test_paused_display_does_not_alarm_for_old_error():
    assert display_health({'enabled':False,'logs':[{'status':'Failed'}]},NOW)[0] == 'paused'

@pytest.mark.parametrize('job,expected', [
    ({'enabled':True,'running':True}, 'running'),
    ({'enabled':True,'next_run':None}, 'error'),
    ({'enabled':True,'next_run':iso(-600)}, 'error'),
    ({'enabled':True,'next_run':iso(500),'logs':[]}, 'unknown'),
    ({'enabled':True,'next_run':iso(500),'logs':[{'status':'Success'}]}, 'unknown'),
    ({'enabled':True,'next_run':iso(500),'logs':[{'status':'Pending','finished_at':iso(-10)}]}, 'warning'),
    ({'enabled':True,'next_run':iso(500),'logs':[{'status':'Success','finished_at':iso(-10)}]}, 'healthy'),
])
def test_display_health_requires_current_evidence(job, expected):
    assert display_health(job,NOW)[0] == expected

def test_calendar_sleep_is_not_offline_but_missing_ack_is_not_healthy():
    data={'google_connected':True,'fetched_at':iso(-3600),'device_seen':{'seen_at':iso(-7200)}}
    assert calendar_health(data,NOW)[0]=='healthy'
    data['device_seen']={}
    assert calendar_health(data,NOW)[0]=='unknown'
    data['device_seen']={'seen_at':iso(-100000)}
    assert calendar_health(data,NOW)[0]=='warning'

def test_facebook_failures_survive_quiet_hours():
    data={'active_now':False,'health_state':'down','last_failure_reason':'Incomplete scan'}
    assert insignia_health(data,NOW)==('error','Incomplete scan')
    assert insignia_health({'active_now':False},NOW)[0]=='sleeping'
    assert insignia_health({'active_now':True,'checkpoint':iso(-3600)},NOW)[0]=='warning'

def test_reddit_block_is_not_a_success_or_just_a_scheduled_wait():
    assert reddit_health({'workflow_state':{'blocked':True},'automation_status':'PAUSED'},NOW)[0]=='error'
    assert reddit_health({'workflow_state':{},'automation_status':'PAUSED'},NOW)[0]=='paused'
    assert reddit_health({'workflow_state':{},'automation_status':'ACTIVE','next_scheduled_local':iso(-7200)},NOW)[0]=='warning'
    assert aggregate(['healthy','paused','sleeping'])=='healthy'
    assert aggregate(['healthy','unknown'])=='unknown'
