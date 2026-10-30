"""RonHub UI, installed alongside the existing controllers and scheduler."""
import hmac
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit
import requests
from flask import Blueprint, Flask, Response, jsonify, render_template, request
from .backend import Conflict, NativeBackend, RemoteBackend
from .registry import SYSTEMS, DISPLAYS, fields_for
from .service import HubService, read_json, write_json


def install(app, runtime=None, config=None):
    state_dir = Path(os.environ.get('RONHUB_STATE_DIR', Path.cwd() / '.runtime' / 'ronhub'))
    config = config or read_json(state_dir / 'config.json', {})
    config.setdefault('note_url', 'http://127.0.0.1:29174')
    config.setdefault('esl_url', 'http://ronhub.local:5000')
    if not config.get('report_key'):
        config['report_key'] = secrets.token_urlsafe(36)
        write_json(state_dir / 'config.json', config)
    csrf = secrets.token_urlsafe(32)
    backend = NativeBackend(app, runtime) if runtime else RemoteBackend(config['esl_url'])
    service = HubService(backend, config, state_dir)
    app.extensions['ronhub'] = service
    hub = Blueprint('hub', __name__, template_folder='templates', static_folder='static', static_url_path='/hub/assets')

    def shell():
        return render_template('hub.html', csrf=csrf, systems=SYSTEMS, displays=DISPLAYS)

    if 'index' in app.view_functions:
        old_index = app.view_functions['index']
        app.add_url_rule('/legacy', 'legacy', old_index)
        app.view_functions['index'] = shell
    else:
        app.add_url_rule('/', 'index', shell)

    @hub.get('/systems/<system>')
    @hub.get('/systems/<system>/<section>')
    @hub.get('/settings')
    def page(system=None, section=None):
        if system and system not in {x['id'] for x in SYSTEMS}:
            return shell(), 404
        return shell()

    @hub.before_request
    def protect():
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            if request.content_length and request.content_length > 65536:
                return jsonify(error='The request is too large.'), 413
            if request.path in ('/hub/api/reports/reddit', '/hub/api/reports/gpu'):
                key = request.headers.get('Authorization', '').removeprefix('Bearer ')
                if not hmac.compare_digest(key, config['report_key']):
                    return jsonify(error='Status bridge authentication failed.'), 401
            elif not hmac.compare_digest(request.headers.get('X-Hub-CSRF', ''), csrf) or request.headers.get('Origin') not in (None, request.host_url.rstrip('/')):
                return jsonify(error='Reload this page before making changes.'), 403

    @app.after_request
    def hub_headers(response):
        if request.path.startswith(('/hub/', '/systems', '/settings')) or request.path == '/':
            response.headers['Cache-Control'] = 'no-store, private'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['Referrer-Policy'] = 'same-origin'
            response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
        return response

    @hub.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 409 if isinstance(error, Conflict) else 400

    @hub.errorhandler(KeyError)
    def missing(error):
        return jsonify(error='This display was not found.'), 404

    @hub.get('/hub/api/state')
    def state():
        return jsonify(service.snapshot(force=request.args.get('refresh') == '1'))

    @hub.get('/hub/api/settings/<job>')
    def settings(job):
        fields_for(job)
        return jsonify(backend.settings(job))

    @hub.post('/hub/api/settings/<job>')
    def save(job):
        fields_for(job)
        payload = request.get_json(silent=True) or {}
        result = backend.save(job, payload.get('values'), payload.get('revision'))
        service.cached_at = 0
        return jsonify(result)

    @hub.post('/hub/api/run/<job>')
    def run(job):
        if job not in {x['id'] for x in DISPLAYS}:
            raise KeyError(job)
        result = backend.trigger(job)
        service.cached_at = 0
        return jsonify(result), 202

    @hub.post('/hub/api/reports/reddit')
    def report():
        service.receive_reddit(request.get_json(silent=True))
        return jsonify(ok=True)

    @hub.post('/hub/api/reports/gpu')
    def gpu_report():
        service.receive_gpu(request.get_json(silent=True))
        return jsonify(ok=True)

    @hub.get('/hub/api/gpu')
    def gpu_status():
        return jsonify(service.gpu())

    @hub.post('/hub/api/insignia/<action>')
    def insignia_action(action):
        return jsonify(service.insignia_action(action))

    @hub.get('/hub/api/calendar/frame')
    def frame():
        try:
            res = requests.get(config['note_url'] + '/api/frame.png', params={'scale': '2', 'native': '1'}, timeout=10)
            return Response(res.content, status=res.status_code, content_type=res.headers.get('Content-Type', 'image/png'))
        except requests.RequestException:
            return jsonify(error='Calendar preview is unavailable.'), 502

    @hub.route('/hub/api/calendar/<action>', methods=['POST'])
    def calendar_action(action):
        endpoints = {'refresh': '/api/refresh', 'settings': '/api/settings', 'check': '/api/device/check', 'send': '/api/device/send'}
        if action not in endpoints:
            raise KeyError(action)
        # Read the controller's own CSRF token, preserving its existing protection.
        from html.parser import HTMLParser
        class TokenParser(HTMLParser):
            token = None
            def handle_starttag(self, tag, attrs):
                a = dict(attrs)
                if tag == 'meta' and a.get('name') == 'csrf-token':
                    self.token = a.get('content')
        try:
            landing = requests.get(config['note_url'] + '/', params={'embedded': '1'}, timeout=8)
            parser = TokenParser()
            parser.feed(landing.text)
            if not parser.token:
                return jsonify(error='The calendar controller could not be opened. Reload and try again.'), 502
            result = requests.post(config['note_url'] + endpoints[action], json=request.get_json(silent=True) or {}, headers={'X-CSRF-Token': parser.token}, timeout=60)
            service.cached_at = 0
            return Response(result.content, status=result.status_code, content_type='application/json')
        except requests.RequestException:
            return jsonify(error='The calendar request could not be confirmed. Refresh status before trying again.'), 502

    @hub.get('/hub/api/todo')
    def todo():
        if runtime:
            context, status = runtime['get_todo_render_context'](runtime['load_config'](), force_refresh=request.args.get('refresh') == '1')
            return jsonify(context), status
        # Preview uses the existing read-only task panel.
        res = requests.get(config['esl_url'] + '/todo/fragment', timeout=30)
        return Response(res.content, status=res.status_code, content_type='text/html')

    @hub.get('/hub/api/todo-panel')
    def todo_panel():
        if runtime:
            return runtime['todo_fragment']()
        res = requests.get(config['esl_url'] + '/todo/fragment', params=request.args, timeout=30)
        return Response(res.content, status=res.status_code, content_type='text/html')

    @hub.get('/hub/integration-guide')
    def integration_guide():
        return render_template('integrations.html')

    app.register_blueprint(hub)
    return app


def create_app(config=None):
    return install(Flask(__name__), config=config)
