import copy
from contextlib import nullcontext
from datetime import datetime, timezone, timedelta
import json
from types import SimpleNamespace
from unittest.mock import Mock
from flask import Flask
import pytest
from ronhub import create_app
from ronhub.backend import Conflict, NativeBackend, public_settings, validate_values
from ronhub.service import HubService

def backend_fixture():
    config={'energy':{'enabled':True,'mode':'schedule','interval':30,'days':1,'times':['08:00'],'auth_key':'private-key','device_id':'d1','cost_per_kwh':.12},'fitness':{'refresh_token':'rotated-token'},'system':{'gateway_ip':'192.168.220.206','store_code':'2000'}}
    saved=[]
    def save(c):
        saved.append(copy.deepcopy(c));config.clear();config.update(c)
    rt={'load_config':lambda:copy.deepcopy(config),'file_lock':lambda _:nullcontext(),'CONFIG_FILE':'test.json','validate_config':Mock(),'save_config':save,'reschedule_all':Mock()}
    return NativeBackend(Flask(__name__),rt),config,saved

def test_scoped_save_preserves_other_settings_and_credentials():
    b,c,s=backend_fixture();before=b.settings('energy');assert before['values']['auth_key'] is True
    assert 'private-key' not in json.dumps(before)
    b.save('energy',{'device_id':'d2','auth_key':''},before['revision'])
    assert c['fitness']['refresh_token']=='rotated-token'
    assert c['energy']['auth_key']=='private-key'
    assert c['energy']['times']==['08:00']
    assert c['energy']['enabled'] is True

def test_conflicting_save_does_not_overwrite_newer_settings():
    b,c,s=backend_fixture();before=b.settings('energy');c['energy']['device_id']='changed'
    with pytest.raises(Conflict): b.save('energy',{'device_id':'old'},before['revision'])
    assert not s

@pytest.mark.parametrize('values',[{'interval':0},{'times':['25:99']},{'enabled':'true'},{'mode':'other'},{'auth_key':False},{'unexpected':'x'},{'cost_per_kwh':'NaN'}])
def test_invalid_changes_are_rejected(values):
    with pytest.raises(ValueError): validate_values('energy',values)

@pytest.fixture
def app(tmp_path,monkeypatch):
    monkeypatch.setenv('RONHUB_STATE_DIR',str(tmp_path))
    app=create_app({'report_key':'test-key','esl_url':'http://127.0.0.1:9999','note_url':'http://127.0.0.1:9999'})
    app.config['TESTING']=True
    return app

def test_report_authentication_and_freshness(app):
    c=app.test_client();path='/hub/api/reports/reddit'
    assert c.post(path,json={}).status_code==401
    headers={'Authorization':'Bearer test-key'}
    old=(datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat()
    data={'sampled_at':old,'workflow_state':{},'history':[]}
    assert c.post(path,json=data,headers=headers).status_code==400
    data['sampled_at']=datetime.now(timezone.utc).isoformat()
    data['workflow_state']={'blocked':True}
    assert c.post(path,json=data,headers=headers).status_code==200
    assert app.extensions['ronhub'].reddit()['status']=='error'

def test_csrf_rejects_untrusted_changes(app):
    c=app.test_client()
    assert c.post('/hub/api/run/weather').status_code==403
    import re
    token=re.search(r'name="hub-csrf" content="([^"]+)"',c.get('/').text).group(1)
    assert c.post('/hub/api/run/weather',headers={'X-Hub-CSRF':token,'Origin':'https://evil.example'}).status_code==403

def test_stale_bridge_does_not_claim_healthy(app):
    svc=app.extensions['ronhub']
    old=(datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat()
    (svc.state_dir/'reddit.json').write_text(json.dumps({'received_at':old,'data':{'sampled_at':old,'workflow_state':{},'automation_status':'ACTIVE'}}))
    assert svc.reddit()['status']=='unknown'
    assert not svc.reddit()['connected']

def test_unknown_display_cannot_run(app):
    import re
    c=app.test_client();token=re.search(r'name="hub-csrf" content="([^"]+)"',c.get('/').text).group(1)
    assert c.post('/hub/api/run/not-a-job',headers={'X-Hub-CSRF':token}).status_code==404

def test_shell_routes_and_assets(app):
    c=app.test_client()
    for url in ['/','/systems/esl/weather','/systems/calendar','/systems/insignia','/systems/reddit','/settings','/hub/integration-guide','/hub/assets/hub.js','/hub/assets/hub.css']:
        assert c.get(url).status_code==200,url

def test_gpu_report_rejects_incomplete_and_stale_companion_data(app):
    svc=app.extensions['ronhub']
    data={'sampled_at':datetime.now(timezone.utc).isoformat(),'sampleAgeMs':0,'protocolVersion':1,'snapshot':{'mode':'host','checks':[]}}
    with pytest.raises(ValueError): svc.receive_gpu(data)
    data['snapshot']['checks']=[{'id':x,'state':'ok'} for x in ('ollama','tailscale','forwarding','gpu','models')]
    data['snapshot']['gpuMetrics']={'sampleAgeMs':16000,'devices':[{'index':0,'loadPercent':99}]}
    svc.receive_gpu(data)
    assert svc.gpu()['status']=='healthy'
    assert svc.gpu()['data']['gpuMetrics'] is None
    data['sampleAgeMs']=66000
    with pytest.raises(ValueError): svc.receive_gpu(data)

def test_live_gpu_zero_is_preserved(app):
    svc=app.extensions['ronhub']
    data={'sampled_at':datetime.now(timezone.utc).isoformat(),'sampleAgeMs':0,'protocolVersion':1,'snapshot':{'mode':'host','checks':[{'id':x,'state':'ok'} for x in ('ollama','tailscale','forwarding','gpu','models')],'gpuMetrics':{'sampleAgeMs':0,'devices':[{'index':0,'loadPercent':0}]}}}
    svc.receive_gpu(data)
    assert svc.gpu()['data']['gpuMetrics']['devices'][0]['loadPercent']==0


@pytest.mark.parametrize('host_state', ['warning', 'unknown'])
def test_host_issue_is_visible_with_all_systems_healthy(app, monkeypatch, host_state):
    svc = app.extensions['ronhub']
    for name in ('esl', 'calendar', 'insignia', 'reddit', 'gpu'):
        monkeypatch.setattr(svc, name, lambda: {'status': 'healthy', 'summary': 'Ready'})
    monkeypatch.setattr('ronhub.service.host_status', lambda: {'status': host_state, 'summary': 'Check host telemetry'})
    snapshot = svc.snapshot()
    assert snapshot['status'] == host_state
    assert snapshot['issues'][0]['id'] == 'host'


def test_unreachable_azure_retains_observation_without_an_expired_next_run(app, monkeypatch):
    svc = app.extensions['ronhub']
    svc.config['insignia'] = {'key_path': 'key', 'known_hosts': 'hosts', 'host': 'example'}
    previous = {'status': 'error', 'summary': 'The last scan failed', 'checked_at': '2026-10-29T21:53:00-07:00', 'next_run': '2026-10-29T21:57:00-07:00', 'data': {'scan_failures': 4}}
    (svc.state_dir / 'insignia-last.json').write_text(json.dumps(previous))
    monkeypatch.setattr('ronhub.service.subprocess.run', lambda *a, **k: SimpleNamespace(returncode=255))
    result = svc.insignia()
    assert result['next_run'] is None
    assert result['last_observed_at'] == previous['checked_at']
    assert result['data']['scan_failures'] == 4
    assert not result['connected']


def test_azure_management_link_comes_from_runtime_configuration(app, monkeypatch):
    svc = app.extensions['ronhub']
    svc.config['insignia'] = {'portal_url': 'https://portal.azure.com/#example-resource', 'key_path': 'private-key-path'}
    for name in ('esl', 'calendar', 'insignia', 'reddit', 'gpu'):
        monkeypatch.setattr(svc, name, lambda: {'status': 'healthy', 'summary': 'Ready'})
    monkeypatch.setattr('ronhub.service.host_status', lambda: {'status': 'healthy', 'summary': 'Ready'})
    snapshot = svc.snapshot()
    item = next(x for x in snapshot['systems'] if x['id'] == 'insignia')
    assert item['manage_url'] == svc.config['insignia']['portal_url']
    assert 'private-key-path' not in json.dumps(snapshot)
