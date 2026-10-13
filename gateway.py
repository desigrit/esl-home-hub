"""Submit one Rainus update and distinguish acceptance from tag delivery."""

import copy
import time
from urllib.parse import quote

import requests

from runtime import STATE_DIR, file_lock


class GatewayError(RuntimeError):
    pass


class GatewayPending(GatewayError):
    pass


def _body(response, label):
    if response.status_code != 200:
        raise GatewayError(f'{label}: HTTP {response.status_code}.')
    try:
        body = response.json()
    except ValueError:
        raise GatewayError(f'{label}: invalid JSON response.') from None
    if not isinstance(body, dict):
        raise GatewayError(f'{label}: invalid response structure.')
    return body


def publish(system, payload, *, session=None, timeout=20):
    """Return only after the gateway confirms delivery to at least one tag.

    Rainus supports -1 for server-generated task IDs. Whole-second timestamps
    collide across controllers; retrying the same ID only repeats HTTP 500.
    POSTs are deliberately not retried after an ambiguous network failure.
    """
    request_session = session or requests.Session()
    base = f"http://{system['gateway_ip']}"
    payload = copy.deepcopy(payload)
    payload['taskId'] = -1
    payload['priorTaskId'] = -1
    confirmation_seconds = max(1, min(120, int(system.get('gateway_confirmation_seconds', 45))))
    try:
        with file_lock(STATE_DIR / 'gateway.lock'):
            response = request_session.post(base + '/api/product', json=payload, timeout=timeout)
        body = _body(response, 'Gateway update')
        if body.get('result') != 'ok':
            raise GatewayError('Gateway rejected the update: ' + str(body.get('result', 'missing result'))[:200])
        task_id = body.get('data', {}).get('taskId')
        if task_id is None or str(task_id) in ('', '-1'):
            raise GatewayError('Gateway accepted the update but returned no task ID.')
        task_id = str(task_id)
        print(f'Gateway accepted task {task_id}; waiting for tag confirmation.', flush=True)
        deadline = time.monotonic() + confirmation_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GatewayPending(f'Gateway task {task_id} was accepted, but tag delivery is still unconfirmed after {confirmation_seconds}s. Check tag battery and radio connectivity.')
            try:
                response = request_session.get(base + '/api/status/task/' + quote(task_id, safe=''), timeout=min(10, remaining))
                status = _body(response, 'Gateway delivery status')
            except (requests.RequestException, GatewayError):
                time.sleep(min(2, max(0, deadline - time.monotonic())))
                continue
            if str(status.get('taskId')) != task_id:
                raise GatewayError('Gateway returned delivery status for a different task.')
            tags = status.get('tagSts')
            if status.get('endTime') not in (None, -1, '-1', 0, '0'):
                if (isinstance(tags, list) and tags and
                        all(tag.get('status') == 'ok' for tag in tags) and
                        str(status.get('successRate')) == '100'):
                    print(f'Tag delivery confirmed for task {task_id} ({len(tags)} tag(s)).', flush=True)
                    return task_id
                raise GatewayError(f'Gateway task {task_id} completed without successful delivery to every tag. Check tag assignment, battery, and radio connectivity.')
            time.sleep(min(2, max(0, deadline - time.monotonic())))
    except requests.RequestException as error:
        raise GatewayError(f'Gateway request failed ({type(error).__name__}); acceptance is unconfirmed.') from None
    finally:
        if session is None:
            request_session.close()
