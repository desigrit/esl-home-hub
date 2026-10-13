import concurrent.futures
import copy
import datetime as dt
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import requests

os.environ['ESL_HUB_DISABLE_SCHEDULER'] = '1'
import app
import gateway
from controllers import dota_controller, energy_controller, strava_controller, weather_controller
from http_client import request_json
import runtime
from scheduling import CalendarDaysTrigger


class Response:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.system = {'gateway_ip': 'gateway', 'gateway_confirmation_seconds': 5}
        self.payload = {'taskId': 'same-second', 'product': [{'prCode': 'tag'}]}
        self.session = Mock()
        self.session.post.return_value = Response({'result': 'ok', 'data': {'taskId': 'new-id'}})
        self.session.get.return_value = Response({'taskId': 'new-id', 'endTime': 1,
                                                  'successRate': 100, 'tagSts': [{'status': 'ok'}]})
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(gateway, 'STATE_DIR', Path(self.temp.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_gateway_allocates_id_and_requires_delivery_confirmation(self):
        result = gateway.publish(self.system, self.payload, session=self.session)
        self.assertEqual(result, 'new-id')
        self.assertEqual(self.session.post.call_args.kwargs['json']['taskId'], -1)
        self.assertEqual(self.session.post.call_args.kwargs['json']['priorTaskId'], -1)
        self.assertEqual(self.payload['taskId'], 'same-second')
        self.assertTrue(self.session.get.called)

    def test_http_200_rejection_is_failure(self):
        self.session.post.return_value = Response({'result': 'invalid product'})
        with self.assertRaisesRegex(gateway.GatewayError, 'rejected'):
            gateway.publish(self.system, self.payload, session=self.session)
        self.session.get.assert_not_called()

    def test_http_500_is_not_retried_with_duplicate_task_id(self):
        self.session.post.return_value = Response({'result': 'duplicate'}, 500)
        with self.assertRaisesRegex(gateway.GatewayError, 'HTTP 500'):
            gateway.publish(self.system, self.payload, session=self.session)
        self.assertEqual(self.session.post.call_count, 1)

    def test_invalid_json_and_missing_task_id_fail(self):
        for body in (ValueError('bad JSON'), {'result': 'ok'}, []):
            self.session.post.return_value = Response(body)
            with self.assertRaises(gateway.GatewayError):
                gateway.publish(self.system, self.payload, session=self.session)

    def test_failed_or_unassigned_tag_is_not_success(self):
        for tags in ([], [{'status': 'ng'}], [{'status': 'ok'}, {'status': 'ng'}]):
            self.session.get.return_value = Response({'taskId': 'new-id', 'endTime': 1, 'successRate': 100, 'tagSts': tags})
            with self.assertRaisesRegex(gateway.GatewayError, 'without successful delivery'):
                gateway.publish(self.system, self.payload, session=self.session)

    def test_accepted_but_unconfirmed_is_pending(self):
        self.session.get.return_value = Response({'taskId': 'new-id', 'endTime': -1, 'successRate': 0, 'tagSts': [{'status': 'ng'}]})
        clock = [0]
        with patch.object(gateway.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(gateway.time, 'sleep', side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
            with self.assertRaises(gateway.GatewayPending):
                gateway.publish(self.system, self.payload, session=self.session)
        self.assertEqual(self.session.post.call_count, 1)

    def test_transport_error_does_not_leak_url_or_retry_post(self):
        self.session.post.side_effect = requests.ReadTimeout('http://host/?api_key=secret')
        with self.assertRaises(gateway.GatewayError) as result:
            gateway.publish(self.system, self.payload, session=self.session)
        self.assertNotIn('secret', str(result.exception))
        self.assertEqual(self.session.post.call_count, 1)


class StateTests(unittest.TestCase):
    def test_concurrent_atomic_updates_preserve_every_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            runtime.atomic_json(path, {'count': 0, 'fitness': {'refresh_token': 'token'}})
            def increment(_):
                runtime.update_json(path, lambda state: state.update(count=state['count'] + 1))
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(increment, range(50)))
            self.assertEqual(runtime.read_json(path)['count'], 50)
            self.assertEqual(runtime.read_json(path)['fitness']['refresh_token'], 'token')

    def test_failed_write_preserves_original_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            runtime.atomic_json(path, {'good': True})
            with self.assertRaises(TypeError):
                runtime.atomic_json(path, {'bad': object()})
            self.assertEqual(runtime.read_json(path), {'good': True})

    def test_redaction_removes_config_secrets_and_query_credentials(self):
        text = runtime.redact('failure abc-secret auth_key=abc123&other=ok', {'fitness': {'client_secret': 'abc-secret'}})
        self.assertNotIn('abc-secret', text)
        self.assertNotIn('abc123', text)


class ScheduleTests(unittest.TestCase):
    def test_weekly_schedule_survives_restart(self):
        trigger = CalendarDaysTrigger(days=7, hour=23, minute=0, anchor='2026-10-07', timezone='America/Los_Angeles')
        now = dt.datetime(2026, 10, 12, 18, tzinfo=ZoneInfo('America/Los_Angeles'))
        self.assertEqual(trigger.get_next_fire_time(None, now).date(), dt.date(2026, 10, 14))

    def test_daily_schedule_preserves_wall_clock_across_dst(self):
        zone = ZoneInfo('America/Los_Angeles')
        trigger = CalendarDaysTrigger(days=1, hour=8, minute=0, anchor='2026-10-30', timezone=zone)
        previous = dt.datetime(2026, 10, 31, 8, tzinfo=zone)
        following = trigger.get_next_fire_time(previous, previous)
        self.assertEqual((following.day, following.hour), (1, 8))
        self.assertEqual(following.utcoffset(), dt.timedelta(hours=-8))

    def test_nonexistent_spring_time_normalizes_forward(self):
        zone = ZoneInfo('America/Los_Angeles')
        trigger = CalendarDaysTrigger(days=1, hour=2, minute=30, anchor='2026-03-08', timezone=zone)
        following = trigger.get_next_fire_time(None, dt.datetime(2026, 3, 8, 0, tzinfo=zone))
        self.assertEqual((following.hour, following.minute), (3, 30))


class ControllerFailureTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((runtime.ROOT / 'config.example.json').read_text())
        self.session = Mock()
        self.session.__enter__ = Mock(return_value=self.session)
        self.session.__exit__ = Mock(return_value=False)

    def test_strava_inactive_preserves_tag_instead_of_publishing_zeroes(self):
        self.session.request.side_effect = [
            Response({'access_token': 'access-token'}),
            Response({'errors': [{'code': 'Inactive'}]}, 403),
        ]
        with patch.object(strava_controller, 'retry_session', return_value=self.session), patch.object(strava_controller, 'publish') as publish:
            with self.assertRaisesRegex(RuntimeError, 'inactive'):
                strava_controller.run(self.config)
        publish.assert_not_called()

    def test_strava_refresh_preserves_other_recent_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            current = copy.deepcopy(self.config)
            current['energy']['cost_per_kwh'] = 0.5
            runtime.atomic_json(path, current)
            self.session.request.side_effect = [Response({'access_token': 'access', 'refresh_token': 'rotated'}), Response([], 503)]
            with patch.object(strava_controller, 'CONFIG_FILE', path), patch.object(strava_controller, 'retry_session', return_value=self.session):
                with self.assertRaisesRegex(RuntimeError, 'HTTP 503'):
                    strava_controller.run(self.config)
            saved = runtime.read_json(path)
            self.assertEqual(saved['fitness']['refresh_token'], 'rotated')
            self.assertEqual(saved['energy']['cost_per_kwh'], 0.5)

    def test_empty_shelly_history_does_not_update_tag(self):
        self.session.request.return_value = Response({'history': []})
        with patch.object(energy_controller, 'retry_session', return_value=self.session), patch.object(energy_controller, 'publish') as publish:
            with self.assertRaisesRegex(RuntimeError, 'no completed'):
                energy_controller.run(self.config)
        publish.assert_not_called()

    def test_shelly_ytd_uses_prior_months_and_excludes_today(self):
        class FixedDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 12, 10)
        def row(date, consumption):
            return {'datetime': date + ' 00:00:00', 'tariff_id': '1', 'consumption': consumption, 'cost': consumption / 10000}
        # Deliberately unordered daily data, as observed from Shelly.
        self.session.request.side_effect = [
            Response({'history': [row('2026-10-12',9000), row('2026-10-11',2000), row('2026-10-01',1000), row('2026-09-30',4000)]}),
            Response({'history': [row('2026-01-01',100000), row('2026-09-01',200000)]}),
        ]
        with patch.object(energy_controller.datetime,'datetime',FixedDateTime), patch.object(energy_controller,'retry_session',return_value=self.session), patch.object(energy_controller,'publish') as publish:
            energy_controller.run(self.config)
        fields = publish.call_args.args[1]['product'][0]['prInfo']
        self.assertEqual(fields[51],'2.0 kWh')
        self.assertEqual(fields[53],'7 kWh')
        self.assertEqual(fields[56],'303 kWh')
        self.assertEqual(fields[92],'Oct 11')
        self.assertEqual(self.session.request.call_args.kwargs['params']['date_to'],'2026-09-30 23:59:59')

    def test_stale_shelly_data_is_not_stamped_as_fresh(self):
        self.session.request.return_value=Response({'history':[{'datetime':'2020-01-01 00:00:00','tariff_id':'1','consumption':1000,'cost':1}]})
        with patch.object(energy_controller,'retry_session',return_value=self.session), patch.object(energy_controller,'publish') as publish:
            with self.assertRaisesRegex(RuntimeError,'stale'):
                energy_controller.run(self.config)
        publish.assert_not_called()

    def test_weather_failure_does_not_update_tag(self):
        self.config['weather']['locations'] = {name: {'lat': 0, 'lon': 0} for name in ('Seattle', 'Delhi', 'Hyderabad')}
        self.session.request.return_value = Response({}, 503)
        with patch.object(weather_controller, 'retry_session', return_value=self.session), patch.object(weather_controller, 'publish') as publish:
            with self.assertRaises(RuntimeError):
                weather_controller.run(self.config)
        publish.assert_not_called()

    def test_dota_fetches_beyond_first_100_matches_to_baseline(self):
        def match(identifier):
            return {'match_id': identifier, 'start_time': 100, 'player_slot': 0, 'radiant_win': True}
        first = [match(i) for i in range(300, 200, -1)]
        second = [match(i) for i in range(200, 100, -1)]
        self.session.request.side_effect = [Response(first), Response(second)]
        result = dota_controller.fetch_ranked_matches(self.session, 'player', 150, dt.datetime(2026, 10, 12))
        self.assertEqual(len(result), 200)
        self.assertEqual(self.session.request.call_args.kwargs['params']['offset'], 100)

    def test_dota_repeated_page_fails_instead_of_inflating_mmr(self):
        page = [{'match_id': i, 'start_time': 100, 'player_slot': 0, 'radiant_win': True} for i in range(300, 200, -1)]
        self.session.request.return_value = Response(page)
        with self.assertRaisesRegex(RuntimeError, 'repeated a page'):
            dota_controller.fetch_ranked_matches(self.session, 'player', 150, dt.datetime(2026, 10, 12))

    def test_dota_server_error_does_not_return_an_empty_success(self):
        self.session.request.return_value=Response({'error':'Internal Server Error'},500)
        with self.assertRaisesRegex(RuntimeError,'HTTP 500'):
            dota_controller.fetch_ranked_matches(self.session,'player',150,dt.datetime(2026,10,12))


class AppRobustnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = json.loads((runtime.ROOT / 'config.example.json').read_text())
        self.patches = [patch.object(app, 'CONFIG_FILE', self.root/'config.json'),
                        patch.object(app, 'LOG_FILE', self.root/'logs.json'),
                        patch.object(app, 'STATE_DIR', self.root/'state')]
        for item in self.patches:
            item.start()
        runtime.atomic_json(app.CONFIG_FILE, self.config)
        self.client = app.app.test_client()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_invalid_settings_preserve_saved_config_and_schedules(self):
        original = Path(app.CONFIG_FILE).read_text()
        with patch.object(app, 'reschedule_all') as reschedule:
            response = self.client.post('/update', data={'dota_mode': 'interval', 'dota_interval': '0'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Path(app.CONFIG_FILE).read_text(), original)
        reschedule.assert_not_called()

    def test_blank_secret_fields_preserve_rotating_credentials(self):
        with patch.object(app, 'reschedule_all'):
            response = self.client.post('/update', data={'fit_client_id': 'client', 'fit_client_secret': '', 'fit_refresh_token_new': ''})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(runtime.read_json(app.CONFIG_FILE)['fitness']['refresh_token'], self.config['fitness']['refresh_token'])

    def test_dashboard_does_not_include_saved_secrets(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.config['fitness']['client_secret'].encode(), response.data)
        self.assertNotIn(self.config['fitness']['refresh_token'].encode(), response.data)
        self.assertNotIn(self.config['energy']['auth_key'].encode(), response.data)

    def test_parallel_run_logs_are_isolated_and_preserved(self):
        script = "import sys,time\nname=sys.argv[1]\nprint(name+' start', flush=True)\ntime.sleep(0.1)\nprint(name+' end', flush=True)\n"
        (self.root/'job_worker.py').write_text(script)
        with patch.object(app, 'ROOT', self.root):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda name: app.run_job(name, force=True), ('dota','energy')))
        logs=app.load_logs()
        for name, other in (('dota','energy'), ('energy','dota')):
            self.assertEqual(logs[name][0]['status'], 'Success')
            self.assertIn(name+' start', logs[name][0]['output'])
            self.assertNotIn(other+' start', logs[name][0]['output'])
        self.assertEqual(results, [True, True])

    def test_controller_failure_and_pending_status_are_not_success(self):
        for code, status in ((1,'Failed'),(2,'Pending'),(3,'Skipped')):
            with patch.object(app.subprocess, 'run', return_value=subprocess.CompletedProcess([],code,'some output')):
                app.run_job('fitness',force=True)
            self.assertEqual(app.load_logs()['fitness'][0]['status'],status)

    def test_hung_worker_is_bounded_and_logged_failed(self):
        with patch.object(app.subprocess, 'run', side_effect=subprocess.TimeoutExpired('worker',30,output=b'partial output')):
            app.run_job('weather',force=True)
        self.assertEqual(app.load_logs()['weather'][0]['status'],'Failed')
        self.assertIn('timed out',app.load_logs()['weather'][0]['output'])
        self.assertNotIn('weather',app._active_jobs)

    def test_duplicate_worker_does_not_start(self):
        app._job_locks['dota'].acquire()
        try:
            with patch.object(app.subprocess, 'run') as run:
                self.assertFalse(app.run_job('dota',force=True))
                run.assert_not_called()
        finally:
            app._job_locks['dota'].release()

    def test_unknown_manual_job_is_404(self):
        self.assertEqual(self.client.post('/trigger/unknown').status_code,404)

    def test_old_success_records_are_explicitly_unverified(self):
        runtime.atomic_json(app.LOG_FILE, {'dota':[{'time':'08:00 AM, Oct 12','status':'Success','output':'old mixed output'}]})
        self.assertEqual(app.load_logs()['dota'][0]['status'],'Unverified')


if __name__ == '__main__':
    unittest.main()
