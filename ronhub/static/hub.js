'use strict';
(() => {
  const $ = (q, el = document) => el.querySelector(q);
  const $$ = (q, el = document) => [...el.querySelectorAll(q)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const paths = {
    home:'M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z',
    display:'M4 4h16v12H4zM8 21h8m-4-5v5',
    calendar:'M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Zm2-3v6m10-6v6M3 11h18m-14 4h2m6 0h2m-10 3h2',
    bell:'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Zm-8 12h4',
    message:'M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-6 3V6a2 2 0 0 1 2-2Zm2 5h10M7 13h7',
    settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1Z',
    refresh:'M20 7v5h-5M4 17v-5h5M5.5 8a7 7 0 0 1 11.8-3L20 8M4 16l2.7 3A7 7 0 0 0 18.5 16',
    check:'m5 12 4 4L19 6',
    close:'m6 6 12 12M6 18 18 6',
    menu:'M4 6h16M4 12h16M4 18h16',
    shield:'m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Zm-4 9 3 3 5-6',
    alert:'m12 3 10 18H2Zm0 6v5m0 3h.01',
    arrow:'M4 12h15m-6-6 6 6-6 6',
    chevron:'m9 5 7 7-7 7',
    external:'M14 3h7v7m0-7-11 11M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5',
    sun:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0-6v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5',
    game:'M7 6h10l3 3 2 9-3 2-4-5H9l-4 5-3-2 2-9Zm-1 5h5m-2.5-2.5v5M16 10h.01M19 13h.01',
    activity:'M2 12h4l3-8 6 16 3-8h4',
    bolt:'m13 2-9 12h7l-1 8L21 9h-8Z',
    flag:'M5 22V3m0 1c5-4 9 4 15 0v10c-6 4-10-4-15 0',
    car:'M4 10 6 4h12l2 6M3 10h18v8H3Zm2 8v3m14-3v3M6 14h2m8 0h2',
    clock:'M12 8v5l4 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
    server:'M3 3h18v7H3Zm0 11h18v7H3ZM7 6.5h.01M7 17.5h.01M12 6.5h5M12 17.5h5',
    pause:'M8 5v14M16 5v14',
    play:'m7 3 14 9-14 9Z',
    download:'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5'
  };
  function icon(name) { return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.display}"/></svg>`; }
  const labels = {healthy:'Healthy', warning:'Needs attention', error:'Needs attention', offline:'Unreachable', unknown:'Unverified', paused:'Paused', sleeping:'Quiet hours', running:'Updating'};
  const badge = (state, text) => `<span class="badge ${esc(state)}"><span class="dot ${esc(state)}"></span>${esc(text || labels[state] || state)}</span>`;
  const link = (href, text, external = false) => `<a class="text-link" href="${esc(href)}" ${external ? 'target="_blank" rel="noopener noreferrer"' : 'data-nav'}>${esc(text)}${icon(external ? 'external' : 'arrow')}</a>`;
  const timeFormat = new Intl.DateTimeFormat('en-US', {timeZone:'America/Los_Angeles', month:'short', day:'numeric', hour:'numeric', minute:'2-digit'});
  const dateFormat = new Intl.DateTimeFormat('en-US', {timeZone:'America/Los_Angeles', weekday:'short',month:'short',day:'numeric'});
  function fmt(value) { if (!value) return 'Not recorded'; const date = new Date(value); return isNaN(date) ? 'Not recorded' : timeFormat.format(date); }
  function relative(value) { const seconds = Math.floor((Date.now() - new Date(value).getTime()) / 1000); if (!Number.isFinite(seconds)) return 'Not recorded'; if (seconds < -60) return fmt(value); if (seconds < 60) return 'Just now'; if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`; if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`; return `${Math.floor(seconds / 86400)}d ago`; }
  function uptime(seconds) { if (!Number.isFinite(seconds)) return 'Unavailable'; const days = Math.floor(seconds / 86400); const hours = Math.floor(seconds % 86400 / 3600); return `${days ? days + 'd ' : ''}${hours}h`; }
  let state, routeKey = '', requestBusy = false, pageVersion = 0, dirty = false, timer, noticeTimer;
  const pending = new Set();
  const settingsCache = new Map();
  let deferredRender = false;
  const main = $('#main');
  const csrf = $('meta[name="hub-csrf"]').content;
  let failures = 0;

  async function api(path, options = {}) {
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), options.timeout || 20000);
    try {
      const response = await fetch(path, {...options, cache:'no-store', signal:abort.signal, headers:{'Accept':'application/json', ...(options.body ? {'Content-Type':'application/json'} : {}), ...(options.method === 'POST' ? {'X-Hub-CSRF':csrf} : {}), ...options.headers}});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'The request could not be completed.');
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('The request timed out. Refresh status before trying again.');
      throw error;
    } finally { clearTimeout(timeout); }
  }

  function toast(message, error = false) {
    clearTimeout(noticeTimer);
    const el = $('#toast');
    el.textContent = message; el.className = `toast${error ? ' error' : ''}`; el.hidden = false;
    noticeTimer = setTimeout(() => { el.hidden = true; }, error ? 10000 : 5000);
  }

  function currentRoute() {
    const parts = location.pathname.split('/').filter(Boolean);
    return {system:parts[0] === 'systems' ? parts[1] : parts[0] === 'settings' ? 'settings' : 'overview', section:parts[2] || '', view:new URLSearchParams(location.search).get('view') || 'activity'};
  }
  function sys(id) { return state?.systems.find(s => s.id === id); }
  function button(text, action, primary = false, extra = '') { return `<button class="btn${primary ? ' primary' : ''}" data-action="${esc(action)}" ${extra}>${icon(action === 'refresh' ? 'refresh' : action === 'run' ? 'play' : 'refresh')}<span>${esc(text)}</span></button>`; }
  function refreshButton() { return '<button class="btn" data-action="refresh" aria-label="Refresh status">' + icon('refresh') + '<span class="btn-label">Refresh status</span></button>'; }
  function heading(title, description, actions = refreshButton()) { return `<div class="page-heading"><div><h1>${esc(title)}</h1><p>${esc(description)}</p></div><div class="heading-actions">${actions}</div></div>`; }
  function empty(title, body) { return `<div class="empty"><h3>${esc(title)}</h3><p>${esc(body)}</p></div>`; }
  function fact(label, value) { return `<div><dt>${esc(label)}</dt><dd>${esc(value ?? 'Not recorded')}</dd></div>`; }
  function facts(rows, cls = '') { return `<dl class="facts ${cls}">${rows.map(([k,v]) => fact(k,v)).join('')}</dl>`; }
  function statusSummary(item) { return `<div class="health-strip ${esc(item.status)}"><span class="health-symbol">${icon(['error','warning','offline'].includes(item.status) ? 'alert' : 'shield')}</span><div><strong>${esc(item.summary)}</strong><p>${esc(item.checked_at ? 'Checked ' + fmt(item.checked_at) + ' Pacific' : 'No status has been received yet')}</p></div>${badge(item.status)}</div>`; }
  function metricLine(metrics) { return `<div class="metric-inline">${(metrics || []).map(m => `<div><span>${esc(m.label)}</span><strong>${esc(m.value)}</strong></div>`).join('')}</div>`; }
  function activity(items, includeName = true) {
    if (!items.length) return empty('No runs recorded yet', 'The next update will appear here with its result and output.');
    return `<div class="activity-list">${items.map((e,i) => `<details class="activity-entry" data-detail="${esc(e.timestamp || i)}-${esc(e.name)}"><summary><span class="dot ${esc(e.status)}"></span><span class="event-name"><strong>${esc(includeName ? e.name : e.label)}</strong>${includeName ? `<span class="system-caption">${esc(e.label)}</span>` : ''}</span><time title="${esc(fmt(e.timestamp))}">${esc(fmt(e.timestamp))}</time>${icon('chevron')}</summary><pre class="log-output">${esc(e.output || 'No output was recorded for this run.')}</pre></details>`).join('')}</div>`;
  }
  function logs(job) { return (job.logs || []).map(l => ({name:job.name, label:l.status, status:({'Success':'healthy','Failed':'error','Pending':'warning','Skipped':'paused'})[l.status] || 'unknown', timestamp:l.finished_at, output:l.output})); }
  function hostPanel() {
    const h = state.host;
    return `<section class="host-panel" aria-label="Raspberry Pi health"><div class="host-title"><h2>Raspberry Pi</h2>${badge(h.status, h.status === 'healthy' ? 'Online' : undefined)}</div><p>${esc(h.summary)}</p><div class="host-model">${esc(h.model || 'Host telemetry')}<br>${esc(h.hostname || 'ronhub.local')}</div>${(h.metrics || []).map(m => `<div class="metric"><div class="metric-head"><span>${esc(m.label)}</span><strong>${m.value == null ? 'Unavailable' : esc(m.value) + `<span class="muted">${esc(m.unit)}</span>`}</strong></div>${m.unit === '%' && m.value != null ? `<div class="meter" role="meter" aria-label="${esc(m.label)}" aria-valuenow="${Number(m.value)}" aria-valuemin="0" aria-valuemax="100"><span style="width:${Math.min(100,Math.max(0,Number(m.value)))}%"></span></div>` : ''}${m.detail ? `<small>${esc(m.detail)}</small>` : ''}</div>`).join('')}<div class="service-list">${(h.services || []).map(s => `<div><span>${esc(s.name)}</span><span class="service-state"><span class="dot ${s.status === 'active' ? 'healthy' : 'error'}"></span>${esc(s.status === 'active' ? 'Running' : s.status)}</span></div>`).join('')}</div><div class="host-foot"><span>Uptime ${uptime(h.uptime_seconds)}</span><span>${esc(h.checked_at ? relative(h.checked_at) : 'No reading')}</span></div></section>`;
  }
  function nextLabel(s) {
    if (s.id === 'gpu') return ['Remote access','Ollama · Tailscale'];
    if (s.id === 'esl') { const next = (s.jobs || []).map(j => j.next_run).filter(Boolean).sort()[0]; return next ? ['Next display update',fmt(next)] : ['Schedule','No upcoming run']; }
    if (s.next_run) return [s.id === 'calendar' ? 'Next refresh' : 'Next check',fmt(s.next_run)];
    if (s.id === 'insignia') return ['Monitoring window','6 a.m. to 10 p.m.'];
    return ['Next action',s.status === 'error' ? 'Review required' : s.status === 'paused' ? 'Paused' : 'Awaiting status'];
  }
  function overview() {
    const count = state.systems.filter(s => ['error','warning','offline','unknown'].includes(s.status)).length;
    const hostNeedsAttention = ['error','warning','offline','unknown'].includes(state.host.status);
    const healthy = state.systems.filter(s => s.status === 'healthy').length;
    const title = count ? `${count} system${count === 1 ? '' : 's'} need${count === 1 ? 's' : ''} attention${hostNeedsAttention ? ', along with the Raspberry Pi' : ''}` : hostNeedsAttention ? 'The Raspberry Pi needs attention' : 'Your home is running smoothly';
    const issueHtml = state.issues.length ? `<section><div class="section-heading"><h2>Needs attention <span class="count">${state.issues.length}</span></h2></div><div class="issues">${state.issues.map(i => `<div class="issue">${icon('alert')}<div class="issue-body"><div class="issue-title">${esc(i.title)}</div><p>${esc(i.detail)}</p>${link(i.path,i.action)}</div><a href="${esc(i.path)}" data-nav class="issue-arrow" aria-label="Review ${esc(i.title)}">${icon('chevron')}</a></div>`).join('')}</div></section>` : '';
    return heading('Home overview', 'A clear view of everything running at home.') + `<div class="health-strip ${esc(state.status)}"><span class="health-symbol">${icon(count || hostNeedsAttention ? 'alert' : 'shield')}</span><div><strong>${esc(title)}</strong><p>${healthy} healthy · ${state.systems.length} systems · Status updates automatically</p></div><div class="strip-meta"><strong>${state.host.status === 'healthy' ? 'Raspberry Pi online' : 'Check Raspberry Pi status'}</strong>Home network</div></div><div class="overview-grid"><div class="content-stack">${issueHtml}<section><div class="section-heading"><h2>Your systems <span class="count">${state.systems.length}</span></h2><span class="small muted">One home for all of them</span></div><div class="system-list">${state.systems.map(s => { const n = nextLabel(s); return `<a class="system-row" href="${esc(s.path)}" data-nav>${icon(s.icon)}<span><span class="system-name">${esc(s.name)}</span><span class="system-caption">${esc(s.id === 'calendar' ? 'Zectrix Note 4C · ' : '')}${esc(s.host)}</span></span><span>${badge(s.status)}</span><span class="system-next">${esc(n[0])}<strong>${esc(n[1])}</strong></span><span class="row-arrow">${icon('chevron')}</span></a>`; }).join('')}</div></section><section><div class="section-heading"><h2>Recent activity</h2><span class="small muted">Latest recorded runs</span></div>${activity(state.activity.slice(0,6))}</section></div><div class="side-column">${hostPanel()}<div class="help-note"><h3>Good to know</h3><p>Displays sleep between updates. Paused systems and scheduled quiet hours are shown separately from failures.</p></div></div></div>`;
  }
  function eslTabs(selected) {
    const jobs = sys('esl')?.jobs || [];
    return `<nav class="tabs" aria-label="ESL displays"><a class="tab ${!selected ? 'active' : ''}" href="/systems/esl" data-nav ${!selected ? 'aria-current="page"' : ''}>All displays</a>${jobs.map(j => `<a class="tab ${selected === j.id ? 'active' : ''}" href="/systems/esl/${esc(j.id)}" data-nav ${selected === j.id ? 'aria-current="page"' : ''}>${icon(j.icon)}${esc(j.name)}</a>`).join('')}</nav>`;
  }
  function subnav(items, active) { return `<nav class="subtabs" aria-label="Project views">${items.map(([id,label,href]) => `<a href="${esc(href)}" data-nav class="subtab ${id === active ? 'active' : ''}" ${id === active ? 'aria-current="page"' : ''}>${esc(label)}</a>`).join('')}</nav>`; }
  function eslPage(route) {
    const s = sys('esl');
    let html = heading('ESL Home Hub','Small displays. Everything worth a glance.') + eslTabs(route.section);
    if (!route.section) {
      html += statusSummary(s) + `<div class="section-heading"><h2>Displays & schedules</h2>${link('/settings','Gateway settings')}</div><div class="system-list display-table">${(s.jobs || []).map(j => `<a class="system-row" href="/systems/esl/${esc(j.id)}" data-nav>${icon(j.icon)}<span><span class="system-name">${esc(j.name)}</span><span class="system-caption">${esc(j.description)}</span></span><span>${badge(j.status)}</span><span class="system-next">Next update<strong>${esc(j.next_run ? fmt(j.next_run) : j.enabled ? 'Not scheduled' : 'Paused')}</strong></span><span class="row-arrow">${icon('chevron')}</span></a>`).join('')}</div><section class="section-space"><div class="section-heading"><h2>Recent display activity</h2></div>${activity(state.activity.filter(a => a.system === 'esl').slice(0,8))}</section>`;
      return html;
    }
    const job = (s.jobs || []).find(j => j.id === route.section);
    if (!job) return html + empty('Display not found','Choose one of the displays above.');
    const root = `/systems/esl/${job.id}`;
    html += `<div class="detail-heading"><div class="row-title"><h2>${esc(job.name)}</h2>${badge(job.status)}</div><button class="btn primary" data-action="run" data-job="${esc(job.id)}" ${job.running || pending.has(job.id) ? 'disabled' : ''}>${icon('play')}${job.running || pending.has(job.id) ? 'Updating display...' : 'Run update'}</button></div>`;
    const views = [['activity','Activity',root],['settings','Settings',root+'?view=settings']];
    if (job.id === 'todo') views.splice(1,0,['tasks','Task lists',root+'?view=tasks']);
    html += subnav(views,route.view);
    if (route.view === 'settings') return html + `<div class="form-layout"><div id="settings-container" data-job="${esc(job.id)}"><p>Loading saved settings...</p></div><aside class="form-note"><h3>Settings for ${esc(job.name)}</h3><p>Save changes to update this display's schedule and connection. Run an update to check the result.</p><p class="section-space">All schedule times use America/Los_Angeles.</p></aside></div>`;
    if (route.view === 'tasks') return html + `<div class="section-heading"><h2>Your Microsoft To Do lists</h2><button class="btn small" data-action="todo-refresh">${icon('refresh')}Refresh tasks</button></div><div id="todo-content" class="todo-container" aria-live="polite"><p>Loading your task lists...</p></div>`;
    return html + `<div class="detail-grid"><section><div class="section-heading"><h3>Run history</h3><span class="small muted">Latest ${job.logs?.length || 0} runs</span></div>${activity(logs(job),false)}</section><aside class="panel"><h3>Update schedule</h3><p>${esc(job.summary)}</p>${facts([['Scheduled updates',job.enabled ? 'Enabled' : 'Paused'],['Next run',job.next_run ? fmt(job.next_run) : 'Not scheduled'],['Last result',job.logs?.[0]?.status || 'Not recorded'],['Last update',fmt(job.logs?.[0]?.finished_at)]])}<div class="schedule-note">${link(root+'?view=settings','Edit settings & schedule')}</div></aside></div>`;
  }
  function calendarPage(route) {
    const s = sys('calendar'), d = s.data || {};
    const view = route.view;
    const tabs = [['activity','Display & events','/systems/calendar'],['settings','Settings','/systems/calendar?view=settings'],['advanced','Device & connection','/systems/calendar?view=advanced']];
    let html = heading('Family Calendar','Zectrix Note 4C · A quiet view of what’s coming up.', `<button class="btn primary" data-action="calendar-refresh">${icon('refresh')}Refresh calendar</button>`) + subnav(tabs,view);
    if (view === 'settings') return html + `<div class="form-layout"><form id="calendar-form" class="settings-form"><section class="form-section"><h3>Calendar connection</h3><div class="form-fields"><label class="field field-wide">Google calendar ID<input name="calendar_id" value="${esc(d.settings?.calendar_id)}" required autocomplete="off"></label><label class="field field-wide">Timezone<input name="timezone" value="${esc(d.settings?.timezone || 'America/Los_Angeles')}" required list="timezones"><small>Daily updates follow midnight in this timezone, including daylight saving changes.</small></label><datalist id="timezones"><option value="America/Los_Angeles"><option value="America/New_York"><option value="Asia/Kolkata"><option value="Europe/London"></datalist></div></section><div class="form-actions"><button class="btn primary" type="submit">Save calendar settings</button><p class="form-message" role="status"></p></div></form><aside class="form-note"><h3>One update, every midnight</h3><p>The Note wakes, downloads its calendar, and returns to sleep. Refresh the calendar here to prepare the latest events. A short press of the Note's button retrieves them sooner.</p><div class="section-space">${link('/systems/calendar?view=advanced','Manage Google connection & device')}</div></aside></div>`;
    if (view === 'advanced') return html + `<div class="section-heading"><div><h2>Device & Google connection</h2><p>Pair your Note, manage sign-in, or use the reference firmware tools.</p></div></div><iframe class="embedded-controller" id="note-frame" title="Zectrix device and connection controls" src="/note/?embedded=1"></iframe>`;
    html += statusSummary(s);
    if (!s.data) return html + empty('Calendar unavailable','Check the calendar controller on the Pi, then refresh status.');
    const seen = d.device_seen || {};
    return html + `<div class="calendar-layout"><div><div class="preview-surface"><div class="device-frame"><img src="/hub/api/calendar/frame?v=${encodeURIComponent(d.digest || '')}" width="800" height="600" alt="Current Family Calendar image prepared for the Zectrix Note 4C. Events are listed below."></div><div class="preview-meta"><span>Note 4C</span><span>400 × 300 · Four colors</span></div></div><div class="preview-actions"><a class="text-link" href="/note/api/frame.png?native=1&download=1">${icon('download')}Download PNG</a><a class="text-link" href="/note/api/frame.bin">${icon('download')}Device file</a></div></div><div class="content-stack"><section><h2>Display status</h2>${facts([['Calendar connection',d.google_connected ? 'Connected' : 'Needs attention'],['Events available',d.total ?? 0],['Shown on display',d.shown ?? 0],['Calendar fetched',fmt(d.fetched_at)],['Note last checked in',fmt(seen.seen_at)],['Next daily update',fmt(d.next_update)]])}</section><section class="panel"><h3>Ready when the Note wakes</h3><p>The calendar updates at midnight. The Note sleeps between updates to save its battery.</p><p>${esc(d.holiday ? 'Next holiday: ' + d.holiday.name + ' · ' + d.holiday.date : 'No upcoming holiday selected.')}</p></section></div></div><section class="section-space"><div class="section-heading"><h2>On your display</h2><span class="small muted">${esc(d.shown || 0)} events</span></div><div class="event-list">${(d.rows || []).map(e => `<div class="calendar-event"><span>${esc(e.date_label)}</span><span>${esc(e.all_day ? 'All day' : e.time)}</span><strong>${esc(e.title)}</strong></div>`).join('') || empty('A clear calendar','Upcoming events will appear here after the next refresh.')}</div></section>`;
  }
  function insigniaPage() {
    const s=sys('insignia'), d=s.data || {};
    const azureUrl = s.manage_url || 'https://portal.azure.com/';
    return heading('Insignia Facebook Notifications','New posts from Insignia Seattle Residents.') + statusSummary(s) + `<div class="detail-grid"><div><section><div class="section-heading"><h2>Monitoring activity</h2>${badge(d.last_result === 'failed' ? 'error' : s.status, d.last_result ? d.last_result.replaceAll('_',' ') : 'Awaiting status')}</div>${metricLine(s.metrics)}${facts([['Last completed scan',fmt(d.checkpoint)],['Consecutive scan failures',d.scan_failures ?? 'Unknown'],[s.connected&&new Date(d.next_scan_at)>Date.now()?'Next retry':'Last reported retry',d.next_scan_at ? fmt(d.next_scan_at) : 'Not recorded'],['Recovery checks',`${d.recovery_streak ?? 0} of 3`],['Delivery queue',d.delivery_paused || `${d.pending ?? 0} pending`],['Facebook session',d.paused || 'No login pause reported'],['Last observed',fmt(s.last_observed_at || s.checked_at)]])}</section>${d.last_failure_reason ? `<section class="section-space"><h2>Latest issue</h2><div class="notice">${esc(d.last_failure_reason)}</div><p class="small">The monitor keeps its last completed checkpoint and retries with increasing delays. A failed scan does not count as a completed check.</p></section>` : ''}<section class="section-space"><h2>Connections</h2><div class="connection-row">${icon('message')}<div><strong>Insignia Seattle Residents</strong><small>Private Facebook group</small></div>${link('https://www.facebook.com/groups/insigniaseattleresidents/','Open group',true)}</div><div class="connection-row">${icon('server')}<div><strong>insignia-monitor-vm</strong><small>Azure · West US 2</small></div>${link(azureUrl,'Manage VM',true)}</div><div class="connection-row">${icon('bell')}<div><strong>Pushover</strong><small>Post notifications and failure alerts</small></div>${link('https://pushover.net/','Manage',true)}</div></section></div><aside class="content-stack"><section class="panel"><h3>Daily monitoring</h3>${facts([['Checks','Every 5 minutes'],['Active hours','6 a.m. to 10 p.m.'],['VM starts','5:55 a.m.'],['VM stops','10:05 p.m.'],['Timezone','Pacific']])}<p>The VM powers down overnight and catches up when monitoring resumes.</p>${d.timer_active != null ? `<div class="schedule-note"><p>Scheduled checks: ${d.timer_active ? 'Enabled' : 'Paused'}</p><button class="btn small" data-action="insignia-${d.timer_active ? 'pause' : 'resume'}">${d.timer_active ? 'Pause scheduled checks' : 'Resume scheduled checks'}</button></div>` : ''}</section><section class="panel"><h3>When something needs fixing</h3><ol class="steps"><li>Read the latest issue and next retry time.</li><li>Open Azure to inspect the monitor service.</li><li>If Facebook needs sign-in, use the project's login tool on this computer.</li></ol><div class="section-space">${link('https://github.com/desigrit/facebook-notifications-engine','Project & recovery guide',true)}</div></section></aside></div>`;
  }
  function redditPage() {
    const s=sys('reddit'),d=s.data || {}, history=d.history || [];
    return heading('Reddit Unban','Appeal history, timing, and the next step for u/' + (d.username || 'DesiGrit') + '.') + statusSummary(s) + `<div class="detail-grid"><div>${metricLine(s.metrics)}<div class="section-heading"><h2>Appeal history</h2><span class="small muted">Newest first</span></div>${history.length ? `<div class="activity-list">${history.map((r,i) => `<details class="activity-entry" data-detail="reddit-${esc(r.id || i)}" ${i === 0 ? 'open' : ''}><summary><span class="event-name"><strong>${esc(r.status === 'unknown' ? 'Receipt not confirmed' : r.status === 'success' ? 'Appeal confirmed' : (r.status || 'Unknown').replace(/^./,s=>s.toUpperCase()))}</strong><span class="system-caption">${esc(r.validation_attempt ? 'Validation attempt' : r.setup_test ? 'Setup attempt' : 'Appeal check')}</span></span><time>${esc(fmt(r.finished_at || r.timestamp))}</time>${icon('chevron')}</summary><div class="history-message">${r.message ? `<strong>${r.status === 'success' ? 'Message sent' : 'Attempted message'}</strong><blockquote>${esc(r.message)}</blockquote>` : ''}<p>${esc(r.detail)}</p></div></details>`).join('')}</div>` : empty('No appeal history received','Keep the Windows status bridge running to see the recorded workflow history.')}<div class="external-links">${link('https://www.reddit.com/appeals','Open Reddit appeals',true)}</div></div><aside class="content-stack"><section class="panel"><h3>Workflow</h3>${facts([['Account','u/' + (d.username || 'DesiGrit')],['Automation',d.automation_status || 'Unknown'],['Next appeal',s.next_run ? fmt(s.next_run) : 'Awaiting review'],['Eligible hours','3 a.m. to 6 a.m.'],['Minimum interval','24 hours'],['Timezone','Pacific'],['Windows report',fmt(s.checked_at)]])}</section><section class="panel"><h3>${d.workflow_state?.blocked ? 'Review the unconfirmed attempt' : 'Managed on your PC'}</h3><p>${d.workflow_state?.blocked ? 'The last attempt has no confirmed Reddit receipt. The workflow is paused until you review the result and authorize another validation.' : 'The scheduled workflow on your Windows PC handles the timing and records each result.'}</p><p>Manage the “Daily Reddit appeal for DesiGrit” automation in Codex. Its logs and timing stay together here.</p></section></aside></div>`;
  }
  function gpuPage() {
    const s=sys('gpu'), d=s.data || {}, readings=d.gpuMetrics?.devices || [];
    const checks=d.checks || [];
    const stateMap={ok:'healthy',idle:'paused',warning:'warning',error:'error',fail:'error',unknown:'unknown'};
    const history=d.gpuHistory?.source==='ollama-gpu-estimate'?d.gpuHistory:null;
    const active=new Set(history?.activeHours || []), current=Math.floor(Date.now()/3600000)*3600000;
    const hours=Array.from({length:49},(_,i)=>current-(48-i)*3600000);
    return heading('Local GPU','Shambu · Your home GPU, available over Tailscale.') + statusSummary(s) + `<div class="detail-grid"><div><section><div class="section-heading"><div><h2>${esc(d.gpuName || 'GPU host')}</h2><p>${esc(d.serverName || 'Dabba Cartel')} · ${esc(d.version ? 'Ollama '+d.version : 'Awaiting host details')}</p></div>${badge(s.connected&&checks.find(c=>c.id==='gpu')?.state==='idle'?'paused':s.status,s.connected&&checks.find(c=>c.id==='gpu')?.state==='idle'?'Ollama idle':undefined)}</div>${readings.length?readings.map(r=>`<div class="gpu-readings"><div><span>GPU load${readings.length>1?' · GPU '+r.index:''}</span><strong>${r.loadPercent==null?'Unavailable':esc(r.loadPercent)+'<small>%</small>'}</strong><div class="meter"><span style="width:${Math.min(100,Math.max(0,Number(r.loadPercent)||0))}%"></span></div></div><div><span>VRAM used</span><strong>${r.memoryUsedMib==null?'Unavailable':(r.memoryUsedMib/1024).toFixed(1)}<small>${r.memoryTotalMib==null?'':' / '+(r.memoryTotalMib/1024).toFixed(0)+' GB'}</small></strong><div class="meter"><span style="width:${r.memoryTotalMib?Math.min(100,Math.max(0,r.memoryUsedMib/r.memoryTotalMib*100)):0}%"></span></div></div></div>`).join(''):empty('Live readings unavailable','The next fresh reading from the Shambu companion will appear here.')}<p class="page-footnote">${esc(s.sampled_at?'Host report '+fmt(s.sampled_at)+'.':'Waiting for a host report.')} Live readings refresh every five seconds.</p></section><section class="section-space"><div class="section-heading"><h2>Connection checks</h2><span class="small muted">Reported by the GPU PC</span></div>${checks.map(c=>`<div class="connection-row">${icon(c.id==='gpu'?'server':c.id==='models'?'display':c.id==='tailscale'?'shield':'activity')}<div><strong>${esc(c.title)}</strong><small>${esc(c.detail)}</small></div>${badge(s.connected?(stateMap[c.state]||'unknown'):'unknown',s.connected?c.label:'Stale')}</div>`).join('')}</section><section class="section-space"><div class="section-heading"><h2>Model library</h2><span class="small muted">${esc(d.modelCount??0)} installed</span></div>${(d.installedModels||[]).map(m=>`<div class="connection-row">${icon('display')}<div><strong>${esc(m.name)}</strong><small>${(Number(m.size)/1024**3).toFixed(1)} GB</small></div><span class="small muted">${(d.loadedModels||[]).some(l=>l.name===m.name)?'Loaded':'Available'}</span></div>`).join('')||empty('No model list received','Available models appear after Ollama responds.')}<p class="page-footnote">Checks read the model list without loading a model.</p></section></div><aside class="content-stack"><section class="panel"><h3>Remote access</h3>${facts([['Connection','Tailscale'],['Server',d.serverName||'Dabba Cartel'],['Ollama port','11434'],['Host companion','11435'],['Response time',d.latencyMs!=null?d.latencyMs+' ms':'Unknown']])}<label class="field section-space">Ollama address<input readonly value="${esc(d.externalEndpoint||'Awaiting endpoint')}" aria-label="Tailscale Ollama address"></label><div class="section-space">${link('https://login.tailscale.com/admin/machines','Manage Tailscale',true)}</div></section><section class="panel"><h3>Ollama activity</h3><p>Observed activity during the last 48 hours.</p>${history?`<div class="activity-hours" role="img" aria-label="${hours.filter(h=>active.has(h)).length} hourly windows with observed Ollama GPU activity in the last 48 hours">${hours.map(h=>`<span class="hour ${active.has(h)?'busy':''}" title="${esc(fmt(h))}: ${active.has(h)?'Activity observed':'No activity recorded'}"></span>`).join('')}</div><div class="chart-axis"><span>48h ago</span><span>Now</span></div><p class="small">${esc(history.burstCount??0)} recorded activity bursts</p>`:'<p class="small">Waiting for activity history.</p>'}</section><section class="panel"><h3>Shambu</h3><p>Use the Shambu app to pair another device and manage the host companion.</p><div class="section-space">${link('https://github.com/desigrit/shambu','Project & setup guide',true)}</div></section></aside></div>`;
  }
  function hubSettings() {
    return heading('Hub settings','Connections and shared settings for your home.') + `<div class="detail-grid"><div><section><div class="section-heading"><h2>ESL gateway</h2></div><div id="settings-container" data-job="system"><p>Loading gateway settings...</p></div></section><section class="section-space"><div class="section-heading"><h2>Connected systems</h2></div>${state.systems.map(s => `<div class="connection-row">${icon(s.icon)}<div><strong>${esc(s.name)}</strong><small>${esc(s.host)} · ${esc(s.summary)}</small></div>${link(s.path,'Open')}</div>`).join('')}</section><section class="section-space"><h2>Keep your hub growing</h2><p class="form-note">New systems join the same overview, navigation, and activity history. Each system keeps its own settings and connection.</p><div class="section-space">${link('/hub/integration-guide','Integration guide')}</div></section></div><aside class="content-stack">${hostPanel()}<section class="panel"><h3>Local, by design</h3><p>RonHub runs on your Raspberry Pi. System status refreshes every 20 seconds while this page is open.</p><p>All displayed times use Pacific time.</p></section></aside></div>`;
  }
  function syncChrome() {
    const route=currentRoute();
    $$('.nav-link').forEach(a => { const active=a.id === 'nav-' + route.system; a.classList.toggle('active',active); if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current'); });
    const title = route.system === 'overview' ? 'Overview' : route.system === 'settings' ? 'Hub settings' : sys(route.system)?.name || 'System';
    $('#breadcrumbs').textContent = 'Your home / ' + title;
    document.title = `RonHub | ${title}`;
    if (!state) return;
    state.systems.forEach(s => { const dot=$(`[data-nav-status="${s.id}"]`); if(dot){dot.className='nav-state '+s.status;dot.setAttribute('aria-label',labels[s.status]);dot.title=labels[s.status];} });
    $('#rail-dot').className='dot '+state.host.status;
    $('#rail-health').textContent=state.host.status==='healthy'?'Raspberry Pi online':'Check Pi status';
    $('#rail-time').textContent=state.host.hostname||'ronhub.local';
    $('#updated-at').textContent='Updated '+relative(state.checked_at)+' · Pacific time';
  }
  function render(force=false) {
    syncChrome();
    if (!state) return;
    const route=currentRoute();
    const newKey=location.pathname+location.search;
    const selected = window.getSelection();
    const interacting = main.contains(document.activeElement) && document.activeElement !== main;
    const selecting = selected && !selected.isCollapsed && main.contains(selected.anchorNode);
    // Retain the exact nodes and selection until the person finishes interacting.
    // Status is still fetched and navigation indicators continue to update.
    if (!force && newKey === routeKey && (interacting || selecting)) { deferredRender = true; return; }
    deferredRender = false;
    const keepForm = !force && newKey===routeKey && ($('#settings-form') || $('#calendar-form') || $('#note-frame') || $('#todo-content'));
    if(keepForm) return;
    const open=new Set($$('details[open]',main).map(d=>d.dataset.detail));
    routeKey=newKey;
    pageVersion++;
    const scrollY=window.scrollY;
    main.innerHTML=route.system==='overview'?overview():route.system==='esl'?eslPage(route):route.system==='calendar'?calendarPage(route):route.system==='insignia'?insigniaPage():route.system==='reddit'?redditPage():route.system==='gpu'?gpuPage():route.system==='settings'?hubSettings():empty('System not found','Choose a system in the navigation.');
    $$('details[data-detail]',main).forEach(d=>{if(open.has(d.dataset.detail))d.open=true;});
    main.setAttribute('aria-busy','false');
    if($('#settings-container')) loadSettings($('#settings-container').dataset.job,pageVersion);
    if($('#todo-content')) loadTodo(false,pageVersion);
    if(force) window.scrollTo(0,0); else window.scrollTo(0,scrollY);
  }

  async function refresh(manual=false) {
    if(requestBusy)return;
    requestBusy=true;
    clearTimeout(timer);
    const controls=$$('[data-action="refresh"]'); controls.forEach(b=>b.disabled=true);
    try {
      state=await api('/hub/api/state'+(manual?'?refresh=1':''),{timeout:24000}); failures=0;
      $('#connection-banner').hidden=true;
      render();
      if(manual)toast('Status refreshed.');
    } catch(error) {
      failures++;
      const banner=$('#connection-banner');banner.textContent='Cannot reach RonHub. '+(state?'Showing the last received status from '+fmt(state.checked_at)+'. ':'')+'Check the Pi and home network. Retrying automatically.';banner.hidden=false;
      $('#rail-dot').className='dot offline';$('#rail-health').textContent='RonHub unreachable';
      if(!state){main.innerHTML=heading('Home overview','Your home is temporarily out of reach.')+`<section class="error-panel"><h2>Cannot connect to your systems</h2><p>Check that the Raspberry Pi is online and connected to your home network.</p><button class="btn" data-action="refresh">${icon('refresh')}Try again</button></section>`;main.setAttribute('aria-busy','false');}
      if(manual)toast(error.message,true);
    } finally { requestBusy=false;controls.forEach(b=>b.disabled=false);timer=setTimeout(()=>refresh(),Math.min(60000,failures?20000*failures:pending.size?3000:20000)); }
  }
  function settingsMarkup(job, payload) {
    const normal=payload.fields.filter(f=>!['enabled','mode','interval','days','times'].includes(f.key));
    const schedule=payload.fields.filter(f=>['enabled','mode','interval','days','times'].includes(f.key));
    const fields = list => list.map(f => fieldMarkup(f,payload.values[f.key])).join('');
    return `<form id="settings-form" data-job="${esc(job)}" class="settings-form">${normal.length?`<section class="form-section"><h3>${job==='system'?'Gateway connection':'Connection & display'}</h3><div class="form-fields">${fields(normal)}</div></section>`:''}${schedule.length?`<section class="form-section"><h3>Scheduled updates</h3>${fieldMarkup(schedule.find(f=>f.key==='enabled'),payload.values.enabled)}<div class="form-fields">${fields(schedule.filter(f=>f.key!=='enabled'))}</div></section>`:''}<div class="form-actions"><button type="submit" class="btn primary">Save ${job==='system'?'gateway':'display'} settings</button><button type="button" class="btn quiet" data-action="reload-settings">Reload saved settings</button><p class="form-message" role="status"></p></div></form>`;
  }
  function fieldMarkup(f,value) {
    if(f.type==='checkbox')return `<label class="switch-field"><input type="checkbox" name="${esc(f.key)}" ${value?'checked':''}>Enable scheduled updates</label>`;
    if(f.type==='times')return `<div class="field field-wide" data-schedule="schedule"><span>Update times</span><div class="time-list">${(Array.isArray(value)?value:[]).map((t,i)=>timeInput(t,i)).join('')}</div><button type="button" class="btn small" data-action="add-time">Add time</button><small>Pacific time</small></div>`;
    const schedule=f.key==='interval'?'interval':f.key==='days'?'schedule':null;
    const input=f.type==='select'?`<select name="${esc(f.key)}">${f.options.map(([k,label])=>`<option value="${esc(k)}" ${value===k?'selected':''}>${esc(label)}</option>`).join('')}</select>`:`<input type="${esc(f.type)}" name="${esc(f.key)}" value="${f.type==='password'?'':esc(value)}" ${f.min!=null?`min="${f.min}"`:''} ${f.max!=null?`max="${f.max}"`:''} ${f.step?`step="${f.step}"`:''} ${f.required?'required':''} ${f.type==='password'?'autocomplete="new-password" placeholder="Enter a replacement"':''}>`;
    return `<label class="field" ${schedule?`data-schedule="${schedule}"`:''}>${esc(f.label)}${input}${f.type==='password'?`<small>${value?'A credential is saved. Leave blank to keep it.':'No credential is saved.'}</small>`:''}</label>`;
  }
  function timeInput(value,index) { return `<div class="time-item"><input type="time" name="times" aria-label="Update time ${index+1}" value="${esc(value)}" required><button type="button" class="remove-time" data-action="remove-time" aria-label="Remove update time">${icon('close')}</button></div>`; }
  function syncSchedule(){const mode=$('[name="mode"]')?.value;$$('[data-schedule]').forEach(el=>{el.hidden=el.dataset.schedule!==mode;$$('input',el).forEach(i=>i.required=!el.hidden&&i.type==='time');});}
  async function loadSettings(job, version) {
    const el=$('#settings-container');
    try { const data=await api('/hub/api/settings/'+encodeURIComponent(job));if(version!==pageVersion||!el.isConnected)return;settingsCache.set(job,data);el.innerHTML=settingsMarkup(job,data);syncSchedule();dirty=false; }
    catch(error){if(version!==pageVersion)return;el.innerHTML=`<div class="error-panel"><h3>Settings could not load</h3><p>${esc(error.message)}</p><button class="btn" data-action="reload-settings">Try again</button></div>`;}
  }
  async function loadTodo(force=false,version=pageVersion){
    const el=$('#todo-content');if(!el)return;
    try {const res=await fetch('/hub/api/todo-panel'+(force?'?refresh=1':''),{cache:'no-store',signal:AbortSignal.timeout(45000)});const html=await res.text();if(version!==pageVersion||!el.isConnected)return;el.innerHTML=html;const header=$('.todo-header',el);if(header)header.remove();}
    catch(error){if(version!==pageVersion)return;el.innerHTML=`<div class="error-panel"><h3>Task lists could not load</h3><p>Check the Microsoft connection, then refresh your tasks.</p><button class="btn" data-action="todo-refresh">Try again</button></div>`;}
  }
  async function navigate(href) {
    if(dirty && !window.confirm('You have unsaved changes. Leave this page?'))return;
    dirty=false;history.pushState({},'',href);render(true);$('#main-nav').classList.remove('open');$('.mobile-menu').setAttribute('aria-expanded','false');main.focus({preventScroll:true});
  }
  document.addEventListener('click',async event=>{
    const a=event.target.closest('a[data-nav]');
    if(a&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&!event.altKey&&event.button===0){event.preventDefault();navigate(a.getAttribute('href'));return;}
    const todoRefresh=event.target.closest('[data-todo-refresh]');if(todoRefresh){event.preventDefault();loadTodo(true);return;}
    const b=event.target.closest('[data-action]');if(!b||b.disabled)return;
    const action=b.dataset.action;
    if(action==='refresh'){refresh(true);return;}
    if(action==='add-time'){const list=$('.time-list');list.insertAdjacentHTML('beforeend',timeInput('08:00',list.children.length));dirty=true;return;}
    if(action==='remove-time'){b.closest('.time-item').remove();dirty=true;return;}
    if(action==='reload-settings'){if(dirty&&!confirm('Discard your unsaved settings?'))return;loadSettings($('#settings-container').dataset.job,pageVersion);return;}
    if(action==='todo-refresh'){b.disabled=true;await loadTodo(true);if(b.isConnected)b.disabled=false;return;}
    if(action==='run'){
      const job=b.dataset.job;if(pending.has(job))return;
      pending.add(job);b.disabled=true;b.lastChild.textContent='Starting update...';
      try{await api('/hub/api/run/'+encodeURIComponent(job),{method:'POST'});toast('Update started. Its result will appear in run history.');}
      catch(error){toast(error.message,true);}
      finally{pending.delete(job);await refresh();}
      return;
    }
    if(action==='calendar-refresh'){
      b.disabled=true;
      try{await api('/hub/api/calendar/refresh',{method:'POST',body:'{}',timeout:65000});toast('Calendar refreshed. The Note retrieves it on its next wake.');await refresh();}
      catch(error){toast(error.message,true);}
      finally{if(b.isConnected)b.disabled=false;}
      return;
    }
    if(action==='insignia-pause'||action==='insignia-resume'){
      b.disabled=true;
      try{await api('/hub/api/insignia/'+(action.endsWith('pause')?'pause':'resume'),{method:'POST'});toast(action.endsWith('pause')?'Scheduled checks paused.':'Scheduled checks resumed.');await refresh(true);}
      catch(error){toast(error.message,true);}finally{if(b.isConnected)b.disabled=false;}
    }
  });
  document.addEventListener('input',event=>{if(event.target.closest('#settings-form,#calendar-form'))dirty=true;});
  document.addEventListener('change',event=>{if(event.target.name==='mode')syncSchedule();});
  document.addEventListener('submit',async event=>{
    if(event.target.id!=='settings-form'&&event.target.id!=='calendar-form')return;
    event.preventDefault();const form=event.target;const submit=$('[type="submit"]',form);const message=$('.form-message',form);submit.disabled=true;message.className='form-message';message.textContent='Saving settings...';
    try{
      if(form.id==='settings-form'){
        const job=form.dataset.job,payload=settingsCache.get(job),data=new FormData(form),values={};
        payload.fields.forEach(f=>{values[f.key]=f.type==='checkbox'?data.has(f.key):f.type==='times'?data.getAll('times'):data.get(f.key)??payload.values[f.key];});
        const saved=await api('/hub/api/settings/'+encodeURIComponent(job),{method:'POST',body:JSON.stringify({values,revision:payload.revision})});
        settingsCache.set(job,saved);$$('input[type="password"]',form).forEach(i=>i.value='');
      }else{
        const data=new FormData(form);await api('/hub/api/calendar/settings',{method:'POST',body:JSON.stringify({calendar_id:data.get('calendar_id'),timezone:data.get('timezone')}),timeout:65000});
      }
      dirty=false;message.textContent='Settings saved.';await refresh();
    }catch(error){message.className='form-message error';message.textContent=error.message;}
    finally{if(submit.isConnected)submit.disabled=false;}
  });
  $('.mobile-menu').addEventListener('click',()=>{const open=$('#main-nav').classList.toggle('open');$('.mobile-menu').setAttribute('aria-expanded',String(open));});
  window.addEventListener('popstate',()=>{if(dirty&&!confirm('You have unsaved changes. Leave this page?')){history.pushState({},'',routeKey);return;}dirty=false;render(true);});
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  document.addEventListener('focusout',()=>{if(deferredRender)setTimeout(()=>render(),0);});
  document.addEventListener('selectionchange',()=>{if(deferredRender&&window.getSelection()?.isCollapsed)render();});
  setInterval(async()=>{if(document.hidden||currentRoute().system!=='gpu'||requestBusy||!state)return;try{const gpu=await api('/hub/api/gpu');state.systems=state.systems.map(s=>s.id==='gpu'?{...s,...gpu}:s);render();}catch(_){}},5000);
  $$('[data-icon]').forEach(el=>el.innerHTML=icon(el.dataset.icon));
  $('#today').textContent=dateFormat.format(new Date());
  const legacy=new URLSearchParams(location.search).get('tab');
  if(legacy){history.replaceState({},'',legacy==='note4'?'/systems/calendar':legacy==='system'?'/settings':'/systems/esl/'+legacy);}
  syncChrome();refresh();
})();
