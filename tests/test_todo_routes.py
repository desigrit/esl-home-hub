import json
import os
import unittest

os.environ["ESL_HUB_DISABLE_SCHEDULER"] = "1"

import app as app_module


class FakeTodoService:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def get_snapshot(self, *, force=False):
        return self.snapshot


class FailingTodoService:
    def get_snapshot(self, *, force=False):
        raise RuntimeError("simulated identity provider failure")


class TodoRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.previous_load_config = app_module.load_config
        config = self.previous_load_config()
        config["todo"]["api_key"] = "test-api-key"
        app_module.load_config = lambda: config
        self.previous_service = app_module._todo_service
        self.previous_key = app_module._todo_service_key
        app_module._todo_service = FakeTodoService({
            "fetchedAt": "2026-09-19T17:00:00Z",
            "lists": [{
                "id": "list-1",
                "displayName": "Tasks",
                "tasks": [{
                    "id": "task-1",
                    "title": "Buy coffee",
                    "status": "notStarted",
                }],
            }],
        })
        app_module._todo_service_key = json.dumps(
            config["todo"], sort_keys=True
        )

    def tearDown(self):
        app_module.load_config = self.previous_load_config
        app_module._todo_service = self.previous_service
        app_module._todo_service_key = self.previous_key

    def test_todo_page_renders_server_side(self):
        response = self.client.get("/todo")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Microsoft To Do", response.data)
        self.assertIn(b"Buy coffee", response.data)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_api_returns_the_snapshot(self):
        response = self.client.get(
            "/api/todo",
            headers={"X-API-Key": "test-api-key"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["lists"][0]["displayName"], "Tasks")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_api_keeps_json_contract_for_unexpected_service_failure(self):
        app_module._todo_service = FailingTodoService()

        response = self.client.get(
            "/api/todo",
            headers={"X-API-Key": "test-api-key"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(response.json["error"], "todo_service_error")
        self.assertNotIn(b"simulated identity provider failure", response.data)

    def test_page_hides_unexpected_service_failure(self):
        app_module._todo_service = FailingTodoService()

        response = self.client.get("/todo")

        self.assertEqual(response.status_code, 502)
        self.assertIn(b"Microsoft To Do is unavailable", response.data)
        self.assertNotIn(b"simulated identity provider failure", response.data)

    def test_api_rejects_a_missing_key(self):
        response = self.client.get("/api/todo")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json["error"], "unauthorized")

    def test_api_fails_closed_when_no_key_is_configured(self):
        config = app_module.load_config()
        config["todo"]["api_key"] = ""
        app_module.load_config = lambda: config

        response = self.client.get("/api/todo")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["error"], "configuration_required")


if __name__ == "__main__":
    unittest.main()
