from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from ronhub import create_app
from ronhub.zebby_status import azure_check, cloud_report, status, validate_report
from tools.zebby_reader import check_stripe, check_supabase, purchase_counts, rows

NOW = datetime(2026, 11, 1, 1, 0, tzinfo=timezone.utc)


def test_purchases_use_settlement_pacific_date_and_deduplicate():
    purchases = [{'id': 'paid-1'}, {'id': 'paid-2'}]
    entries = [
        {'reference': 'paid-1', 'created_at': '2026-10-31T06:59:59Z'},
        {'reference': 'paid-1', 'created_at': '2026-10-31T06:59:59Z'},
        {'reference': 'paid-2', 'created_at': '2026-10-31T07:00:00Z'},
        {'reference': 'test-or-abandoned', 'created_at': '2026-10-31T07:00:00Z'},
    ]
    result = purchase_counts(purchases, entries, NOW)
    assert result['total'] == 2
    assert result['days'][-2:] == [{'date': '2026-10-30', 'count': 1}, {'date': '2026-10-31', 'count': 1}]
    assert len(result['days']) == 90
    assert sum(day['count'] for day in result['days']) == 2
    assert 'paid-1' not in json.dumps(result)


def test_all_time_includes_purchase_before_chart_window():
    result = purchase_counts([{'id':'old'}], [{'reference':'old','created_at':'2026-01-01T00:00:00Z'}], NOW)
    assert result['total'] == 1
    assert not any(day['count'] for day in result['days'])


def test_empty_purchases_are_real_zeroes():
    result = purchase_counts([], [], NOW)
    assert result['total'] == 0
    assert result['last_payment_at'] is None
    assert len(result['days']) == 90


def test_missing_settlement_is_not_an_invented_date():
    with pytest.raises(ValueError):
        purchase_counts([{'id':'paid'}], [], NOW)


def test_live_purchase_filter_and_credential_redaction():
    calls = []
    def fetch(url, headers):
        calls.append((url, headers))
        return []
    service, transactions = check_supabase({'SUPABASE_URL':'https://project.supabase.co','SUPABASE_SERVICE_ROLE_KEY':'private-key'}, fetch, NOW)
    assert service['status'] == 'healthy'
    assert transactions['total'] == 0
    assert 'paid=eq.true' in calls[0][0] and 'session_id=like.cs_live_*' in calls[0][0]
    assert 'kind=eq.purchase' in calls[1][0]
    assert 'private-key' not in json.dumps((service, transactions))
    assert calls[0][1]['apikey'] == 'private-key'


def test_database_pagination_does_not_silently_truncate(monkeypatch):
    monkeypatch.setattr('tools.zebby_reader.PAGE_SIZE', 2)
    pages = iter([[{'id':'a'}, {'id':'b'}], [{'id':'c'}]])
    fetch = Mock(side_effect=lambda *_: next(pages))
    assert len(rows('https://project.supabase.co','secret','zebby_purchases','select=id',fetch)) == 3
    assert 'offset=2' in fetch.call_args.args[0]


def test_report_limit_fails_instead_of_showing_partial_totals(monkeypatch):
    monkeypatch.setattr('tools.zebby_reader.PAGE_SIZE', 1)
    monkeypatch.setattr('tools.zebby_reader.MAX_PAGES', 2)
    with pytest.raises(ValueError):
        rows('https://project.supabase.co','secret','zebby_purchases','select=id',lambda *_:[{'id':'a'}])


def test_provider_errors_never_include_credentials():
    def fail(*_):
        raise RuntimeError('Bearer very-private-key in provider URL')
    stripe = check_stripe({'STRIPE_SECRET_KEY':'rk_live_private'}, fail)
    database, transactions = check_supabase({'SUPABASE_URL':'https://project.supabase.co','SUPABASE_SERVICE_ROLE_KEY':'private'},fail,NOW)
    assert stripe['status'] == database['status'] == 'error'
    assert transactions is None
    assert 'very-private-key' not in json.dumps((stripe, database))


def test_stripe_check_uses_get_list_without_payment_mutation():
    fetch = Mock(return_value={'object':'list','data':[]})
    assert check_stripe({'STRIPE_SECRET_KEY':'rk_live_private'},fetch)['status'] == 'healthy'
    assert fetch.call_args.args[0] == 'https://api.stripe.com/v1/checkout/sessions?limit=1'


def test_azure_requires_live_ready_service_and_does_not_follow_redirects():
    get = Mock(return_value=SimpleNamespace(status_code=200,json=lambda:{'ok':True,'mode':'live'}))
    assert azure_check(get)['status'] == 'healthy'
    assert get.call_args.kwargs['allow_redirects'] is False
    get.return_value.json = lambda:{'ok':True,'mode':'test'}
    assert azure_check(get)['status'] == 'offline'


def fresh_report():
    now = datetime.now(timezone.utc)
    return dict(version=1,sampled_at=now.isoformat(),
                services=[dict(id=id,name=id.title(),status='healthy',detail='Responding',checked_at=now.isoformat()) for id in ('stripe','supabase')],
                transactions=purchase_counts([],[],now))


def test_cloud_ssh_is_pinned_bounded_and_redacts_unknown_fields():
    value=fresh_report()
    value['private_key']='hidden'
    runner=Mock(return_value=SimpleNamespace(returncode=0,stdout=json.dumps(value)))
    report=cloud_report({'key_path':'reader','known_hosts':'hosts','host':'reader@host'},runner)
    args=runner.call_args.args[0]
    assert 'StrictHostKeyChecking=yes' in args
    assert args[-1]=='status'
    assert runner.call_args.kwargs['timeout']==35
    assert 'hidden' not in json.dumps(report)


@pytest.mark.parametrize('mutation',[
    lambda r:r.update(sampled_at='2000-01-01T00:00:00Z'),
    lambda r:r['transactions'].update(total=-1),
    lambda r:r['transactions']['days'].pop(),
    lambda r:r['services'].pop(),
    lambda r:r['transactions']['days'][-1].update(count=3),
])
def test_malformed_reports_are_rejected(mutation):
    value=fresh_report();mutation(value)
    with pytest.raises((ValueError, KeyError)):
        validate_report(value)


def test_stale_status_preserves_counts_without_claiming_healthy(tmp_path):
    report=fresh_report()
    report['sampled_at']=(datetime.now(timezone.utc)-timedelta(minutes=4)).isoformat()
    report['transactions_current']=True
    (tmp_path/'zebby.json').write_text(json.dumps(report))
    result=status(tmp_path)
    assert result['status']=='unknown'
    assert all(s['status']=='unknown' for s in result['data']['services'])
    assert result['data']['transactions']['total']==0
    assert result['data']['transactions_stale'] is True


def test_missing_report_is_unavailable_not_zero(tmp_path):
    result=status(tmp_path)
    assert result['status']=='unknown'
    assert result['data']['transactions'] is None
    assert len(result['data']['services'])==3


def test_zebby_route_and_refresh_csrf(tmp_path,monkeypatch):
    monkeypatch.setenv('RONHUB_STATE_DIR',str(tmp_path))
    app=create_app({'report_key':'test-key'})
    client=app.test_client()
    assert client.get('/systems/zebby').status_code==200
    assert client.get('/hub/api/zebby').status_code==200
    assert client.post('/hub/api/zebby/refresh').status_code==403
    assert client.get('/hub/assets/zebby.css').status_code==200
