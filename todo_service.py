import copy
import datetime
import json
import os
import re
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows development fallback
    fcntl = None

try:
    import msal
except ImportError:  # The dashboard can still show setup instructions.
    msal = None


GRAPH_ORIGIN = "https://graph.microsoft.com"
GRAPH_BASE_URL = f"{GRAPH_ORIGIN}/v1.0/"
GRAPH_SCOPES = ["https://graph.microsoft.com/Tasks.Read"]
PROJECT_ROOT = Path(__file__).resolve().parent
MAX_COLLECTION_PAGES = 10_000
MAX_INLINE_RETRY_DELAY_SECONDS = 5
LIST_SELECT = "id,displayName,isShared"
TASK_SELECT = "id,title,status,importance,dueDateTime,categories,recurrence"
_LOCAL_CACHE_LOCK = threading.RLock()


class TodoError(Exception):
    pass


class TodoConfigurationError(TodoError):
    pass


class TodoAuthenticationRequired(TodoError):
    pass


class TodoGraphError(TodoError):
    def __init__(
        self,
        message,
        *,
        status=None,
        code=None,
        request_id=None,
        retry_after=None,
    ):
        super().__init__(message)
        self.status = status
        self.code = code
        self.request_id = request_id
        self.retry_after = retry_after


def _positive_integer(value, default, *, minimum, maximum, name):
    try:
        parsed = int(value if value is not None else default)
    except (TypeError, ValueError) as error:
        raise TodoConfigurationError(f"{name} must be an integer.") from error

    if parsed < minimum or parsed > maximum:
        raise TodoConfigurationError(
            f"{name} must be between {minimum} and {maximum}."
        )
    return parsed


def validate_todo_config(config):
    config = config or {}
    client_id = str(config.get("client_id", "")).strip()
    try:
        parsed_client_id = uuid.UUID(client_id)
    except (ValueError, AttributeError) as error:
        raise TodoConfigurationError(
            "Add a valid Microsoft Application client ID to config.json."
        ) from error

    if parsed_client_id.int == 0:
        raise TodoConfigurationError(
            "Replace the placeholder Microsoft Application client ID in config.json."
        )

    tenant_id = str(config.get("tenant_id", "consumers")).strip() or "consumers"
    if not re.fullmatch(r"[A-Za-z0-9.-]+", tenant_id):
        raise TodoConfigurationError("The Microsoft tenant ID is invalid.")

    cache_path_value = config.get(
        "token_cache_path",
        "controllers/data/microsoft_todo_token_cache.json",
    )
    if not isinstance(cache_path_value, str) or not cache_path_value.strip():
        raise TodoConfigurationError("todo.token_cache_path must be a file path.")
    cache_path = Path(cache_path_value).expanduser()
    if not cache_path.is_absolute():
        cache_path = PROJECT_ROOT / cache_path

    return {
        "client_id": client_id,
        "tenant_id": tenant_id,
        "authority": f"https://login.microsoftonline.com/{tenant_id}",
        "token_cache_path": cache_path.resolve(),
        "cache_seconds": _positive_integer(
            config.get("cache_seconds"),
            30,
            minimum=0,
            maximum=3600,
            name="todo.cache_seconds",
        ),
        "task_concurrency": _positive_integer(
            config.get("task_concurrency"),
            4,
            minimum=1,
            maximum=8,
            name="todo.task_concurrency",
        ),
        "request_timeout_seconds": _positive_integer(
            config.get("request_timeout_seconds"),
            15,
            minimum=3,
            maximum=120,
            name="todo.request_timeout_seconds",
        ),
    }


def _require_msal():
    if msal is None:
        raise TodoConfigurationError(
            "Microsoft To Do support is not installed. Install the Python msal package."
        )


def _write_private_text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


@contextmanager
def open_token_cache(cache_path, *, start_empty=False):
    _require_msal()
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = Path(f"{cache_path}.lock")

    with _LOCAL_CACHE_LOCK:
        with open(lock_path, "a+", encoding="utf-8") as lock_handle:
            os.chmod(lock_path, 0o600)
            if fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)

            cache = msal.SerializableTokenCache()
            if cache_path.exists() and not start_empty:
                try:
                    cache.deserialize(cache_path.read_text(encoding="utf-8"))
                except (ValueError, json.JSONDecodeError) as error:
                    raise TodoAuthenticationRequired(
                        "The Microsoft sign-in cache is unreadable. Run the sign-in command again."
                    ) from error

            try:
                yield cache
            finally:
                if cache.has_state_changed:
                    _write_private_text(cache_path, cache.serialize())
                if fcntl is not None:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


class MsalTokenProvider:
    def __init__(self, config):
        self.config = validate_todo_config(config)

    def get_access_token(self):
        with open_token_cache(self.config["token_cache_path"]) as token_cache:
            application = msal.PublicClientApplication(
                self.config["client_id"],
                authority=self.config["authority"],
                token_cache=token_cache,
                timeout=self.config["request_timeout_seconds"],
            )
            accounts = application.get_accounts()
            if not accounts:
                raise TodoAuthenticationRequired(
                    "Microsoft sign-in is required. Run python3 todo_auth.py on the Raspberry Pi."
                )
            if len(accounts) != 1:
                raise TodoAuthenticationRequired(
                    "More than one Microsoft account is cached. Run python3 todo_auth.py to select one account."
                )

            result = application.acquire_token_silent(
                GRAPH_SCOPES,
                account=accounts[0],
            )
            if not result or "access_token" not in result:
                raise TodoAuthenticationRequired(
                    "Microsoft needs you to sign in again. Run python3 todo_auth.py on the Raspberry Pi."
                )
            return result["access_token"]


def authenticate_with_device_code(config, output=print):
    validated = validate_todo_config(config)
    with open_token_cache(validated["token_cache_path"], start_empty=True) as token_cache:
        application = msal.PublicClientApplication(
            validated["client_id"],
            authority=validated["authority"],
            token_cache=token_cache,
            timeout=validated["request_timeout_seconds"],
        )
        flow = application.initiate_device_flow(scopes=GRAPH_SCOPES)
        if "user_code" not in flow:
            raise TodoAuthenticationRequired(
                "Microsoft could not start device-code sign-in. Check the app registration."
            )

        output(flow["message"])
        result = application.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            code = result.get("error", "authentication_failed")
            raise TodoAuthenticationRequired(
                f"Microsoft sign-in failed with {code}."
            )

        accounts = application.get_accounts()
        return accounts[0].get("username", "the selected Microsoft account")


def _validate_graph_url(value):
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "graph.microsoft.com"
        or not parsed.path.startswith("/v1.0/")
    ):
        raise TodoGraphError("Microsoft Graph returned an unsafe pagination URL.")
    return value


def _graph_error(response):
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    inner_error = error.get("innerError", {}) if isinstance(error, dict) else {}
    return TodoGraphError(
        "Microsoft Graph could not return the To Do data.",
        status=response.status_code,
        code=error.get("code") if isinstance(error, dict) else None,
        request_id=(
            response.headers.get("request-id")
            or inner_error.get("request-id")
            or inner_error.get("requestId")
        ),
        retry_after=response.headers.get("Retry-After"),
    )


class MicrosoftTodoService:
    def __init__(
        self,
        config,
        *,
        token_provider=None,
        session=None,
        monotonic=time.monotonic,
        sleep=time.sleep,
    ):
        self.config = validate_todo_config(config)
        self.token_provider = token_provider or MsalTokenProvider(config)
        self.session = session or requests
        self.monotonic = monotonic
        self.sleep = sleep
        self._snapshot = None
        self._snapshot_time = 0
        self._snapshot_lock = threading.Lock()

    def get_snapshot(self, *, force=False):
        with self._snapshot_lock:
            cache_age = self.monotonic() - self._snapshot_time
            if (
                not force
                and self._snapshot is not None
                and cache_age < self.config["cache_seconds"]
            ):
                return copy.deepcopy(self._snapshot)

            access_token = self.token_provider.get_access_token()
            lists = self._get_collection(
                f"{GRAPH_BASE_URL}me/todo/lists?$select={LIST_SELECT}", access_token
            )

            def with_tasks(task_list):
                list_id = task_list.get("id")
                if not list_id:
                    raise TodoGraphError(
                        "Microsoft Graph returned a task list without an ID."
                    )
                tasks = self._get_collection(
                    f"{GRAPH_BASE_URL}me/todo/lists/"
                    f"{quote(str(list_id), safe='')}/tasks?$select={TASK_SELECT}",
                    access_token,
                )
                return {**task_list, "tasks": tasks}

            if lists:
                worker_count = min(self.config["task_concurrency"], len(lists))
                with ThreadPoolExecutor(max_workers=worker_count) as executor:
                    lists_with_tasks = list(executor.map(with_tasks, lists))
            else:
                lists_with_tasks = []

            snapshot = {
                "fetchedAt": datetime.datetime.now(datetime.timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "lists": lists_with_tasks,
            }
            self._snapshot = snapshot
            self._snapshot_time = self.monotonic()
            return copy.deepcopy(snapshot)

    def _get_collection(self, initial_url, access_token):
        values = []
        next_url = _validate_graph_url(initial_url)
        visited_urls = set()

        while next_url:
            if next_url in visited_urls or len(visited_urls) >= MAX_COLLECTION_PAGES:
                raise TodoGraphError(
                    "Microsoft Graph returned an invalid pagination sequence."
                )
            visited_urls.add(next_url)
            page = self._get_page(next_url, access_token)
            page_values = page.get("value") if isinstance(page, dict) else None
            if not isinstance(page_values, list):
                raise TodoGraphError(
                    "Microsoft Graph returned an invalid collection response."
                )
            values.extend(page_values)

            next_link = page.get("@odata.nextLink")
            next_url = _validate_graph_url(next_link) if next_link else None

        return values

    def _get_page(self, url, access_token):
        for attempt in range(3):
            try:
                response = self.session.get(
                    url,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {access_token}",
                    },
                    timeout=self.config["request_timeout_seconds"],
                )
            except requests.Timeout as error:
                if attempt < 2:
                    self.sleep(0.25 * (2**attempt))
                    continue
                raise TodoGraphError("The Microsoft Graph request timed out.") from error
            except requests.RequestException as error:
                if attempt < 2:
                    self.sleep(0.25 * (2**attempt))
                    continue
                raise TodoGraphError("Could not reach Microsoft Graph.") from error

            if response.ok:
                try:
                    return response.json()
                except ValueError as error:
                    raise TodoGraphError(
                        "Microsoft Graph returned invalid JSON."
                    ) from error

            if response.status_code == 401:
                raise TodoAuthenticationRequired(
                    "Microsoft needs you to sign in again. Run python3 todo_auth.py on the Raspberry Pi."
                )

            retryable = response.status_code in (429, 502, 503, 504)
            if retryable and attempt < 2:
                retry_after = response.headers.get("Retry-After")
                if retry_after is None:
                    self.sleep(0.25 * (2**attempt))
                    continue
                try:
                    retry_delay = int(retry_after)
                except (TypeError, ValueError):
                    retry_delay = MAX_INLINE_RETRY_DELAY_SECONDS + 1
                if 0 <= retry_delay <= MAX_INLINE_RETRY_DELAY_SECONDS:
                    self.sleep(retry_delay)
                    continue

            raise _graph_error(response)

        raise TodoGraphError("Microsoft Graph could not return the To Do data.")


def _due_date(task):
    date_time = (task.get("dueDateTime") or {}).get("dateTime")
    if not date_time or len(date_time) < 10:
        return None
    try:
        return datetime.date.fromisoformat(date_time[:10])
    except ValueError:
        return None


def _due_label(due_date, today):
    if due_date == today:
        return "Today"
    if due_date == today + datetime.timedelta(days=1):
        return "Tomorrow"
    if due_date.year == today.year:
        return due_date.strftime("%b %d").replace(" 0", " ")
    return due_date.strftime("%b %d, %Y").replace(" 0", " ")


def build_todo_view(snapshot, *, today=None):
    today = today or datetime.date.today()
    view_lists = []
    active_total = 0
    completed_total = 0
    due_today_total = 0
    overdue_total = 0

    for source_list in snapshot.get("lists", []):
        active_tasks = []
        completed_tasks = []

        for source_task in source_list.get("tasks", []):
            due = _due_date(source_task)
            status = source_task.get("status", "notStarted")
            completed = status == "completed"
            due_tone = None
            if due and not completed:
                if due < today:
                    due_tone = "overdue"
                    overdue_total += 1
                elif due == today:
                    due_tone = "today"
                    due_today_total += 1

            task = {
                "id": source_task.get("id"),
                "title": source_task.get("title") or "Untitled task",
                "importance": source_task.get("importance", "normal"),
                "status": status,
                "due_date": due,
                "due_iso": due.isoformat() if due else None,
                "due_label": _due_label(due, today) if due else None,
                "due_tone": due_tone,
                "categories": source_task.get("categories") or [],
                "has_recurrence": bool(source_task.get("recurrence")),
            }
            if completed:
                completed_tasks.append(task)
            else:
                active_tasks.append(task)

        active_tasks.sort(
            key=lambda task: (
                task["due_date"] is None,
                task["due_date"] or datetime.date.max,
                task["importance"] != "high",
                task["title"].casefold(),
            )
        )
        completed_tasks.sort(key=lambda task: task["title"].casefold())

        active_total += len(active_tasks)
        completed_total += len(completed_tasks)
        view_lists.append(
            {
                "id": source_list.get("id"),
                "name": source_list.get("displayName") or "Untitled list",
                "is_shared": bool(source_list.get("isShared")),
                "active_tasks": active_tasks,
                "completed_tasks": completed_tasks,
            }
        )

    fetched_at = snapshot.get("fetchedAt")
    fetched_label = None
    if fetched_at:
        try:
            parsed = datetime.datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            fetched_label = parsed.astimezone().strftime("%b %d at %I:%M %p").replace(
                " 0", " "
            )
        except ValueError:
            fetched_label = None

    return {
        "fetched_at": fetched_at,
        "fetched_label": fetched_label,
        "lists": view_lists,
        "list_count": len(view_lists),
        "active_count": active_total,
        "completed_count": completed_total,
        "due_today_count": due_today_total,
        "overdue_count": overdue_total,
    }


def build_todo_api_payload(snapshot):
    """Return the documented API shape without notes or linked resources."""
    lists = []
    for source_list in snapshot.get("lists", []):
        tasks = []
        for source_task in source_list.get("tasks", []):
            tasks.append({
                "id": source_task.get("id"),
                "title": source_task.get("title") or "Untitled task",
                "status": source_task.get("status", "notStarted"),
                "importance": source_task.get("importance", "normal"),
                "dueDateTime": source_task.get("dueDateTime"),
                "categories": source_task.get("categories") or [],
                "recurrence": source_task.get("recurrence"),
            })
        lists.append({
            "id": source_list.get("id"),
            "displayName": source_list.get("displayName") or "Untitled list",
            "isShared": bool(source_list.get("isShared")),
            "tasks": tasks,
        })

    return {
        "fetchedAt": snapshot.get("fetchedAt"),
        "lists": lists,
    }
