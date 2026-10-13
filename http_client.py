"""Bounded retries for reads, with errors that never include credential URLs."""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def retry_session():
    session = requests.Session()
    retry = Retry(total=2, connect=2, read=2, backoff_factor=2,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=('GET', 'HEAD', 'OPTIONS'),
                  raise_on_status=False, respect_retry_after_header=True)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def request_json(session, method, url, *, label, **kwargs):
    kwargs.setdefault('timeout', (10, 30))
    try:
        response = session.request(method, url, **kwargs)
    except requests.RequestException as error:
        raise RuntimeError(f'{label}: request failed ({type(error).__name__}).') from None
    if not 200 <= response.status_code < 300:
        if label.startswith('Strava') and response.status_code == 403:
            try:
                inactive = any(item.get('code') == 'Inactive' for item in response.json().get('errors', []))
            except (ValueError, TypeError, AttributeError):
                inactive = False
            if inactive:
                raise RuntimeError('Strava HTTP 403: the API application is inactive. Reactivate the app in Strava API settings. The previous tag data was preserved.')
        raise RuntimeError(f'{label}: HTTP {response.status_code}. No update was published.')
    try:
        return response.json()
    except ValueError:
        raise RuntimeError(f'{label}: invalid JSON response. No update was published.') from None
