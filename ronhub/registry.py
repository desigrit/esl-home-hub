"""System metadata and editable settings. Add systems here and a status adapter."""
SYSTEMS = [
    dict(id='esl', name='ESL Home Hub', description='Your household, at a glance.', host='Raspberry Pi', icon='display', path='/systems/esl', repository='https://github.com/desigrit/esl-home-hub'),
    dict(id='calendar', name='Family Calendar', description='Zectrix Note 4C', host='Raspberry Pi', icon='calendar', path='/systems/calendar', repository='https://github.com/desigrit/zectrix'),
    dict(id='insignia', name='Insignia Facebook Notifications', description='New posts from your community.', host='Azure VM', icon='bell', path='/systems/insignia', repository='https://github.com/desigrit/facebook-notifications-engine'),
    dict(id='reddit', name='Reddit Unban', description='Appeal history and workflow status.', host='Windows PC', icon='message', path='/systems/reddit', repository=None),
    dict(id='gpu', name='Local GPU', description='Shambu · Ollama over Tailscale', host='Windows PC', icon='server', path='/systems/gpu', repository='https://github.com/desigrit/shambu'),
]
DISPLAYS = [
    dict(id='weather', name='Weather', icon='sun', description='Weather across your cities'),
    dict(id='dota', name='Dota 2', icon='game', description='Road to Immortal'),
    dict(id='fitness', name='Fitness', icon='activity', description='Strava activity and goals'),
    dict(id='energy', name='Energy', icon='bolt', description='Shelly energy consumption'),
    dict(id='f1', name='Formula 1', icon='flag', description='Race weekends and standings'),
    dict(id='family', name='Family Calendar', icon='calendar', description='Calendar on an ESL display'),
    dict(id='todo', name='Microsoft To Do', icon='check', description='Task lists and display updates'),
    dict(id='WebScraper', name='Mercedes', icon='car', description='Vehicle listings from your scraper'),
]


def field(key, label, kind='text', **kwargs):
    return dict(key=key, label=label, type=kind, **kwargs)


FIELDS = {
    'dota': [field('steam_id', 'Steam ID'), field('baseline_mmr', 'Baseline MMR', 'number', min=0), field('target_mmr', 'Target MMR', 'number', min=0), field('baseline_match_id', 'Baseline match ID', 'number', min=0)],
    'fitness': [field('client_id', 'Strava client ID', form='fit_client_id'), field('client_secret', 'Client secret', 'password', form='fit_client_secret'), field('refresh_token', 'Refresh token', 'password', form='fit_refresh_token_new')],
    'energy': [field('device_id', 'Shelly device ID'), field('auth_key', 'Authentication key', 'password'), field('cost_per_kwh', 'Cost per kWh', 'number', min=0, step=0.001, form='energy_cost')],
    'todo': [field('tag_id', 'Display tag ID'), field('layout_id', 'Layout ID')],
    'system': [field('gateway_ip', 'Gateway address', form='sys_gateway_ip', required=True), field('store_code', 'Store code', form='sys_store_code', required=True)],
}
SCHEDULE_FIELDS = [field('enabled', 'Scheduled updates', 'checkbox'), field('mode', 'Update schedule', 'select', options=[['schedule', 'At specific times'], ['interval', 'At an interval']]), field('interval', 'Every (minutes)', 'number', min=1, max=525600), field('days', 'Every (days)', 'number', min=1, max=366), field('times', 'Update times', 'times')]


def fields_for(job):
    if job != 'system' and job not in {x['id'] for x in DISPLAYS}:
        raise KeyError(job)
    return FIELDS.get(job, []) + (SCHEDULE_FIELDS if job != 'system' else [])
