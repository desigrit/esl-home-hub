// Update run feedback without reloading or replacing unsaved settings.
(() => {
    const connection = document.getElementById('connection-status');
    const seen = new Map();
    const pending = new Set();
    const actionErrors = new Map();
    let refreshing = false;
    let timer;

    async function request(url, options = {}) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);
        try {
            return await fetch(url, { ...options, signal: controller.signal, cache: 'no-store' });
        } finally {
            clearTimeout(timeout);
        }
    }

    function renderLogs(name, logs) {
        const host = document.querySelector(`[data-job-logs="${name}"]`);
        const signature = JSON.stringify(logs);
        if (!host || seen.get(name) === signature) return;
        seen.set(name, signature);
        const opened = new Set(Array.from(host.querySelectorAll('details[open]')).map(node => node.dataset.run));
        const fragment = document.createDocumentFragment();
        for (const log of logs) {
            const details = document.createElement('details');
            details.className = 'log-entry';
            details.dataset.run = log.finished_at || log.time;
            details.open = opened.has(details.dataset.run);
            const summary = document.createElement('summary');
            summary.className = 'log-header';
            const label = document.createElement('span');
            const status = document.createElement('span');
            status.className = log.status === 'Success' ? 'status-success' : log.status === 'Failed' ? 'status-fail' : 'status-pending';
            status.textContent = log.status;
            const timestamp = document.createElement('span');
            timestamp.className = 'ms-2 text-white';
            timestamp.textContent = log.time;
            label.append(status, timestamp);
            const prompt = document.createElement('span');
            prompt.className = 'text-muted';
            prompt.textContent = 'View output';
            summary.append(label, prompt);
            const output = document.createElement('div');
            output.className = 'log-output';
            output.textContent = log.output;
            details.append(summary, output);
            fragment.append(details);
        }
        if (!logs.length) {
            const empty = document.createElement('p');
            empty.className = 'text-muted small';
            empty.textContent = 'No runs recorded yet.';
            fragment.append(empty);
        }
        host.replaceChildren(fragment);
    }

    async function refresh() {
        if (refreshing) return;
        clearTimeout(timer);
        refreshing = true;
        let anyRunning = false;
        try {
            const response = await request('/api/status');
            if (!response.ok) throw new Error('Status request failed.');
            const payload = await response.json();
            connection.hidden = payload.scheduler_running;
            connection.textContent = 'The update scheduler is stopped. Restart ESL Hub on the Pi.';
            for (const [name, job] of Object.entries(payload.jobs)) {
                const running = job.running || pending.has(name);
                if (job.running) actionErrors.delete(name);
                anyRunning ||= running;
                const control = document.querySelector(`[data-run-job="${name}"]`);
                if (control) {
                    control.textContent = running ? 'Updating tag...' : 'Run Update Now';
                    control.classList.toggle('disabled', running);
                    control.setAttribute('aria-disabled', String(running));
                }
                const state = document.querySelector(`[data-job-state="${name}"]`);
                if (state) {
                    const next = job.next_run ? new Date(job.next_run).toLocaleString() : null;
                    state.textContent = actionErrors.get(name) || (running ? 'Running. Waiting for API data and tag delivery.' : !job.enabled ? 'Scheduled updates are disabled.' : next ? `Next update: ${next}` : 'No upcoming update is scheduled.');
                }
                renderLogs(name, job.logs);
            }
        } catch (_) {
            connection.hidden = false;
            connection.textContent = 'Cannot refresh run status. Check the connection to RonHub. Retrying automatically.';
        } finally {
            refreshing = false;
            timer = setTimeout(refresh, anyRunning ? 2000 : 15000);
        }
    }

    document.querySelectorAll('[data-run-job]').forEach(control => {
        control.addEventListener('click', async event => {
            event.preventDefault();
            const name = control.dataset.runJob;
            if (pending.has(name) || control.getAttribute('aria-disabled') === 'true') return;
            pending.add(name);
            control.classList.add('disabled');
            control.setAttribute('aria-disabled', 'true');
            control.textContent = 'Starting update...';
            try {
                const response = await request(`/trigger/${name}`, { method: 'POST' });
                if (!response.ok) throw new Error('Could not start the update.');
                actionErrors.delete(name);
            } catch (_) {
                actionErrors.set(name, 'The update request could not be confirmed. Check the connection and try again.');
            } finally {
                pending.delete(name);
                await refresh();
            }
        });
    });

    const form = document.getElementById('configuration-form');
    form.addEventListener('submit', async event => {
        event.preventDefault();
        const button = form.querySelector('[type="submit"]');
        if (button.disabled) return;
        const status = document.getElementById('configuration-status');
        button.disabled = true;
        status.textContent = 'Saving configuration...';
        try {
            const response = await request(form.action, { method: 'POST', body: new FormData(form) });
            if (!response.ok) {
                const error = await response.json().catch(() => ({ error: 'RonHub could not save the settings. Your entries are still here. Try again.' }));
                throw new Error(error.error || 'Could not save configuration.');
            }
            status.textContent = 'Configuration saved.';
            form.querySelectorAll('[type="password"]').forEach(field => { field.value = ''; });
            await refresh();
        } catch (error) {
            status.textContent = error.name === 'AbortError' ? 'Saving timed out. Your entries are still here. Check the connection before trying again.' : error.message;
        } finally {
            button.disabled = false;
        }
    });
    refresh();
})();
