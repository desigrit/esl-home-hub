import datetime
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from todo_service import (
    LIST_SELECT,
    TASK_SELECT,
    MsalTokenProvider,
    MicrosoftTodoService,
    TodoConfigurationError,
    TodoGraphError,
    build_todo_api_payload,
    build_todo_view,
)


TEST_CONFIG = {
    "client_id": "11111111-1111-1111-1111-111111111111",
    "tenant_id": "consumers",
    "cache_seconds": 30,
    "task_concurrency": 2,
    "request_timeout_seconds": 15,
}
LISTS_URL = f"https://graph.microsoft.com/v1.0/me/todo/lists?$select={LIST_SELECT}"


def tasks_url(list_id):
    return (
        f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks"
        f"?$select={TASK_SELECT}"
    )


class FakeResponse:
    def __init__(self, payload, status=200, headers=None):
        self.payload = payload
        self.status_code = status
        self.headers = headers or {}
        self.ok = 200 <= status < 300

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, headers, timeout):
        self.calls.append((url, headers, timeout))
        response = self.responses[url]
        if isinstance(response, list):
            response = response.pop(0)
        if isinstance(response, Exception):
            raise response
        return response if isinstance(response, FakeResponse) else FakeResponse(response)


class FakeTokenProvider:
    def get_access_token(self):
        return "test-token"


class TodoServiceTests(unittest.TestCase):
    def test_fetches_all_list_and_task_pages(self):
        responses = {
            LISTS_URL: {
                "value": [{"id": "list-1", "displayName": "Tasks"}],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/todo/lists?$skiptoken=next",
            },
            "https://graph.microsoft.com/v1.0/me/todo/lists?$skiptoken=next": {
                "value": [{"id": "list/2", "displayName": "Home"}]
            },
            tasks_url("list-1"): {
                "value": [{"id": "task-1", "title": "First"}],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/todo/lists/list-1/tasks?$skiptoken=two",
            },
            "https://graph.microsoft.com/v1.0/me/todo/lists/list-1/tasks?$skiptoken=two": {
                "value": [{"id": "task-2", "title": "Second"}]
            },
            tasks_url("list%2F2"): {
                "value": []
            },
        }
        session = FakeSession(responses)
        service = MicrosoftTodoService(
            TEST_CONFIG,
            token_provider=FakeTokenProvider(),
            session=session,
        )

        snapshot = service.get_snapshot()

        self.assertEqual(len(snapshot["lists"]), 2)
        self.assertEqual(
            [task["title"] for task in snapshot["lists"][0]["tasks"]],
            ["First", "Second"],
        )
        self.assertTrue(
            all(call[1]["Authorization"] == "Bearer test-token" for call in session.calls)
        )

    def test_refuses_pagination_outside_graph(self):
        session = FakeSession({
            LISTS_URL: {
                "value": [],
                "@odata.nextLink": "https://example.com/steal-token",
            }
        })
        service = MicrosoftTodoService(
            TEST_CONFIG,
            token_provider=FakeTokenProvider(),
            session=session,
        )

        with self.assertRaisesRegex(TodoGraphError, "unsafe pagination URL"):
            service.get_snapshot()
        self.assertEqual(len(session.calls), 1)

    def test_refuses_a_repeated_pagination_link(self):
        repeated_url = LISTS_URL
        session = FakeSession({
            repeated_url: {
                "value": [],
                "@odata.nextLink": repeated_url,
            }
        })
        service = MicrosoftTodoService(
            TEST_CONFIG,
            token_provider=FakeTokenProvider(),
            session=session,
        )

        with self.assertRaisesRegex(TodoGraphError, "invalid pagination sequence"):
            service.get_snapshot()
        self.assertEqual(len(session.calls), 1)

    def test_reuses_a_recent_snapshot(self):
        session = FakeSession({
            LISTS_URL: {"value": []}
        })
        service = MicrosoftTodoService(
            TEST_CONFIG,
            token_provider=FakeTokenProvider(),
            session=session,
            monotonic=lambda: 100,
        )

        first = service.get_snapshot()
        second = service.get_snapshot()

        self.assertEqual(first, second)
        self.assertEqual(len(session.calls), 1)

    def test_returns_graph_retry_after_without_an_early_retry(self):
        session = FakeSession({
            LISTS_URL: FakeResponse(
                {"error": {"code": "TooManyRequests"}},
                status=429,
                headers={"Retry-After": "30"},
            )
        })
        service = MicrosoftTodoService(
            TEST_CONFIG,
            token_provider=FakeTokenProvider(),
            session=session,
        )

        with self.assertRaises(TodoGraphError) as raised:
            service.get_snapshot()
        self.assertEqual(raised.exception.status, 429)
        self.assertEqual(raised.exception.retry_after, "30")
        self.assertEqual(len(session.calls), 1)

    def test_retries_a_short_graph_retry_after(self):
        sleeps = []
        session = FakeSession({
            LISTS_URL: [
                FakeResponse(
                    {"error": {"code": "TooManyRequests"}},
                    status=429,
                    headers={"Retry-After": "1"},
                ),
                {"value": []},
            ]
        })
        service = MicrosoftTodoService(
            TEST_CONFIG,
            token_provider=FakeTokenProvider(),
            session=session,
            sleep=sleeps.append,
        )

        snapshot = service.get_snapshot()

        self.assertEqual(snapshot["lists"], [])
        self.assertEqual(sleeps, [1])
        self.assertEqual(len(session.calls), 2)

    def test_retries_a_transport_timeout(self):
        session = FakeSession({
            LISTS_URL: [
                requests.Timeout("temporary timeout"),
                {"value": []},
            ]
        })
        service = MicrosoftTodoService(
            TEST_CONFIG,
            token_provider=FakeTokenProvider(),
            session=session,
            sleep=lambda _seconds: None,
        )

        snapshot = service.get_snapshot()

        self.assertEqual(snapshot["lists"], [])
        self.assertEqual(len(session.calls), 2)

    def test_rejects_the_placeholder_client_id(self):
        with self.assertRaises(TodoConfigurationError):
            MicrosoftTodoService({
                **TEST_CONFIG,
                "client_id": "00000000-0000-0000-0000-000000000000",
            })

    def test_builds_page_view_and_due_counts(self):
        snapshot = {
            "fetchedAt": "2026-09-19T17:00:00Z",
            "lists": [{
                "id": "list-1",
                "displayName": "Tasks",
                "tasks": [
                    {
                        "id": "1",
                        "title": "Overdue",
                        "status": "notStarted",
                        "dueDateTime": {"dateTime": "2026-09-18T00:00:00", "timeZone": "UTC"},
                    },
                    {
                        "id": "2",
                        "title": "Today",
                        "status": "notStarted",
                        "dueDateTime": {"dateTime": "2026-09-19T00:00:00", "timeZone": "UTC"},
                    },
                    {"id": "3", "title": "Done", "status": "completed"},
                ],
            }],
        }

        view = build_todo_view(snapshot, today=datetime.date(2026, 9, 19))

        self.assertEqual(view["active_count"], 2)
        self.assertEqual(view["completed_count"], 1)
        self.assertEqual(view["due_today_count"], 1)
        self.assertEqual(view["overdue_count"], 1)
        self.assertEqual(view["lists"][0]["active_tasks"][0]["title"], "Overdue")

    def test_api_payload_omits_task_notes_and_linked_resources(self):
        payload = build_todo_api_payload({
            "fetchedAt": "2026-09-19T17:00:00Z",
            "lists": [{
                "id": "list-1",
                "displayName": "Tasks",
                "tasks": [{
                    "id": "task-1",
                    "title": "Visible title",
                    "body": {"content": "private note"},
                    "linkedResources": [{"webUrl": "https://private.example"}],
                }],
            }],
        })

        task = payload["lists"][0]["tasks"][0]
        self.assertEqual(task["title"], "Visible title")
        self.assertNotIn("body", task)
        self.assertNotIn("linkedResources", task)

    def test_rejects_null_token_cache_path_as_configuration_error(self):
        with self.assertRaisesRegex(TodoConfigurationError, "token_cache_path"):
            MicrosoftTodoService({
                **TEST_CONFIG,
                "token_cache_path": None,
            })

    def test_msal_requests_use_the_configured_timeout(self):
        fake_application = mock.Mock()
        fake_application.get_accounts.return_value = [{"username": "test@example.com"}]
        fake_application.acquire_token_silent.return_value = {
            "access_token": "test-token"
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            config = {
                **TEST_CONFIG,
                "token_cache_path": str(Path(temporary_directory) / "cache.json"),
            }
            with mock.patch(
                "todo_service.msal.PublicClientApplication",
                return_value=fake_application,
            ) as application_factory:
                token = MsalTokenProvider(config).get_access_token()

        self.assertEqual(token, "test-token")
        self.assertEqual(
            application_factory.call_args.kwargs["timeout"],
            TEST_CONFIG["request_timeout_seconds"],
        )


if __name__ == "__main__":
    unittest.main()
