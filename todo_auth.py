import json
import sys
from pathlib import Path

from todo_service import (
    TodoError,
    authenticate_with_device_code,
)


def main():
    config_path = Path(__file__).with_name("config.json")
    if not config_path.exists():
        raise TodoError("config.json does not exist.")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    username = authenticate_with_device_code(config.get("todo", {}))
    print(f"\nSigned in as {username}.")
    print("Microsoft To Do is ready in RonHub.")


if __name__ == "__main__":
    try:
        main()
    except (TodoError, json.JSONDecodeError) as error:
        print(f"Microsoft To Do sign-in failed: {error}", file=sys.stderr)
        raise SystemExit(1)
