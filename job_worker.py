"""One isolated controller process. Config arrives on stdin, never argv."""

import json
import sys

from controllers import dota_controller, energy_controller, f1_controller
from controllers import family_controller, strava_controller, todo_controller, weather_controller
from controllers import mercedes_controller
from gateway import GatewayPending
from runtime import JobSkipped, STATE_DIR, file_lock, redact

CONTROLLERS = {
    'dota': dota_controller, 'energy': energy_controller, 'f1': f1_controller,
    'family': family_controller, 'fitness': strava_controller,
    'todo': todo_controller, 'weather': weather_controller,
    'WebScraper': mercedes_controller,
}


def main():
    config = {}
    try:
        name = sys.argv[1]
        config = json.load(sys.stdin)
        with file_lock(STATE_DIR / f'job-{name}.lock', blocking=False):
            CONTROLLERS[name].run(config)
        return 0
    except GatewayPending as error:
        print(redact(error, config), flush=True)
        return 2
    except (JobSkipped, BlockingIOError) as error:
        print(redact(error, config), flush=True)
        return 3
    except Exception as error:
        print(redact(f'Update failed: {error}', config), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
