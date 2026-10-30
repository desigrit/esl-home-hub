# RonHub

Home automation management at [ronhub.local:5000](http://ronhub.local:5000/), with a shared health overview and five system pages.

| System | Controls and evidence |
| --- | --- |
| ESL Home Hub | Eight display tabs, run history, individual settings and schedules, manual updates, Microsoft To Do lists, gateway settings |
| Family Calendar | Zectrix Note 4C preview, events, refresh, calendar settings, existing device and Google connection controls |
| Insignia Facebook Notifications | Azure monitor status, last completed scan, failures, notification queue, timer pause/resume when connected |
| Reddit Unban | Recorded appeal attempts, confirmation state, next eligible action, local automation status |
| Local GPU | Shambu host health, GPU load and VRAM, Ollama and Tailscale checks, installed models, observed activity |

The overview distinguishes failed work, missing evidence, paused schedules, sleeping devices, and stale reports. Raspberry Pi telemetry includes CPU, memory, storage, temperature, uptime, and required service status. Browser status updates every 20 seconds; the GPU page requests readings every five seconds. Polling preserves active controls and selections.

## Architecture

RonHub installs as a Flask module inside the existing Pi ESL application. `install(app, globals())` attaches the UI and adapters while using the existing scheduler, configuration validation, file locks, atomic saves, and controller jobs. The previous dashboard remains at `/legacy`.

- `ronhub/registry.py`: system metadata, display metadata, editable field definitions.
- `ronhub/health.py`: health decisions and freshness rules.
- `ronhub/service.py`: status adapters, aggregation, authenticated Windows reports.
- `ronhub/backend.py`: native ESL access and remote preview support. Settings are scoped to one display and use revision checks.
- `ronhub/__init__.py`: routes, CSRF protection, report authentication, calendar proxy.
- `ronhub/templates/` and `ronhub/static/`: responsive shell, page renderers, shared styles.
- `tools/windows_bridge.py`: read-only Reddit and Shambu reporting from Windows.
- `tools/insignia_reader.py`: restricted Azure SSH command for status and timer control.

Secret fields return only whether a value exists. A blank replacement preserves the saved value. External reports use a bearer key and are rejected when stale or malformed. Runtime data and credentials belong in `.runtime/ronhub/` on the Pi and `.private/` in this workspace.

## Run a local preview

Use Python 3.11 or newer. From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py --port 5173
```

Open `http://127.0.0.1:5173`. The remote ESL adapter reads the Pi's existing API and `/legacy` form. Configure `note_url` in `.runtime/ronhub/config.json` for a calendar controller reachable from the preview machine. Host metrics are produced on Linux; the deployed Pi is the authoritative host.

## Deploy on the Pi

The live checkout is `/home/ronhub/esl_hub`. Preserve any existing changes there. Build the application-only archive with:

```powershell
.venv\Scripts\python.exe tools\package.py
```

Transfer `.private/ronhub-release.tar.gz` to the Pi and extract it into a staging directory. From that directory, run:

```sh
sha256sum /home/ronhub/esl_hub/app.py
python3 tools/deploy_on_pi.py --expected-app-sha256 CURRENT_REVIEWED_SHA256
sudo systemctl restart esl_hub
```

The installer verifies the reviewed app hash, refuses to deploy while an ESL update is running, compiles the source, backs up the app and prior module, and inserts the module hook before scheduler startup. Its output identifies the backup directory under `.runtime/ronhub/backups/`. It leaves controller configuration, task history, device pairing, and existing templates intact.

After restart, verify `/healthz`, `/hub/api/state`, all five system pages, `/note/`, `/hub/api/todo-panel`, and the saved display settings. Compare enabled schedules and next-run timestamps to `schedule-before.json` in the backup.

To restore the previous dashboard, copy `app.py` from the chosen backup to `/home/ronhub/esl_hub/app.py`, then restart `esl_hub`. For a later module upgrade, also restore that backup's `ronhub/` directory. Keep the runtime state directory in place.

## Windows status bridge

The private `.private/bridge.json` holds these fields:

```json
{
  "url": "http://ronhub.local:5000",
  "report_key": "MATCH_THE_PI_RUNTIME_KEY",
  "project": "D:/Code/Reddit Unban",
  "codex_home": "D:/Codex/.codex"
}
```

The bridge reads the Shambu pairing key directly from `%LOCALAPPDATA%/Shambu/agent/config.json` to authenticate only to the loopback companion on port 11435. It sends a whitelisted health snapshot to RonHub, never the pairing key. Reddit status is sent every minute; Shambu status every five seconds. The GPU report expires after 65 seconds, GPU measurements after 15 seconds, and Reddit reports after three minutes.

Verify one report cycle, then install the hidden login task:

```powershell
.venv\Scripts\python.exe tools\windows_bridge.py --config .private\bridge.json --once
tools\install_windows_bridge.ps1
Get-ScheduledTask -TaskName RonHub-Status-Bridge
```

The task runs as the current user while signed in, restarts on failure, and disallows duplicate instances. To restart after changing configuration, stop and start `RonHub-Status-Bridge` in Task Scheduler. The bridge reads the existing appeal ledger and automation configuration without submitting appeals or changing the workflow.

## Azure connection

Insignia's dedicated Pi SSH key and pinned host key are held in the Pi runtime directory. The `insignia` configuration supplies `key_path`, `known_hosts`, `host`, optional `command` (default `status`), and optional `portal_url` for the Manage VM link. Install `tools/insignia_reader.py` on the Azure VM and restrict that public key's authorized command to the reader. The reader accepts only `status`, `pause`, and `resume`; its status path reads SQLite in read-only mode.

The VM normally starts at 5:55 a.m. Pacific and stops at 10:05 p.m. Checks run every five minutes during its monitoring window. Until connected, RonHub retains the last verified observation with its original timestamp and shows connection availability separately.

## Add a future system

1. Add the system's ID, label, icon, host, route, and repository to `SYSTEMS` in `registry.py`. Navigation and overview rows use that registry.
2. Add a bounded status adapter to `HubService` and register it in `snapshot()`. Return `status`, `summary`, `checked_at`, and optionally `metrics`, `next_run`, and system detail data.
3. Add a page renderer in `hub.js` and its route branch. Reuse status, activity, facts, form, and navigation components.
4. Add only the necessary management endpoints. Keep credentials on the server, protect mutations, and give external reports a freshness limit.
5. Test failures, stale data, paused work, and recovery as well as the healthy path. Deploy with a backup and inspect desktop and mobile pages.

Accepted states are `healthy`, `running`, `paused`, `sleeping`, `warning`, `error`, `offline`, and `unknown`. A reachable service alone does not prove successful work.

## Validation and design

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
node --check ronhub\static\hub.js
```

The automated tests cover health decisions, credential preservation, conflicting edits, input validation, report authentication, stale data, CSRF, routes, GPU telemetry, and host-only failures. Browser checks cover desktop/mobile layout, navigation, live device images, and focus/selection preservation during polling.

`DESIGN.md` and `.impeccable/design.json` describe the finished design system. Inter is self-hosted from the [official Inter repository](https://github.com/rsms/inter), with its SIL Open Font License in [ronhub/static/fonts/LICENSE.txt](../ronhub/static/fonts/LICENSE.txt).
