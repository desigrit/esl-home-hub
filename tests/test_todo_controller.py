import contextlib
import datetime
import io
import unittest

from controllers import todo_controller
from todo_service import build_todo_view


def task(
    title,
    *,
    status="notStarted",
    importance="normal",
    due=None,
    recurrence=None,
):
    value = {
        "id": title,
        "title": title,
        "status": status,
        "importance": importance,
        "categories": [],
        "recurrence": recurrence,
    }
    if due:
        value["dueDateTime"] = {"dateTime": f"{due}T00:00:00", "timeZone": "UTC"}
    return value


class FakeTodoService:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.force_values = []

    def get_snapshot(self, *, force=False):
        self.force_values.append(force)
        return self.snapshot


class FakeResponse:
    status_code = 200


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse()


class TodoControllerTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.datetime(
            2026,
            9,
            19,
            16,
            5,
            tzinfo=datetime.timezone(datetime.timedelta(hours=-7)),
        )

    def test_register_contract_supports_lists_global_tasks_and_focus_tasks(self):
        lists = []
        for index in range(9):
            list_tasks = [task(f"Task {index}")]
            if index == 2:
                list_tasks.append(task("Overdue task", due="2026-09-18"))
            lists.append({
                "id": f"list-{index}",
                "displayName": f"List {index}",
                "tasks": list_tasks,
            })
        lists.append({"id": "empty", "displayName": "Empty", "tasks": []})

        view = build_todo_view(
            {"fetchedAt": "2026-09-19T23:00:00Z", "lists": lists},
            today=self.now.date(),
        )
        pr = todo_controller.build_pr_data(view, now=self.now)

        self.assertEqual(len(pr), 250)
        self.assertEqual(pr[todo_controller.PR_STATE], "3")
        self.assertEqual(pr[todo_controller.PR_ACTIVE_TOTAL], "10")
        self.assertEqual(pr[todo_controller.PR_ACTIVE_LISTS], "9")
        self.assertEqual(pr[todo_controller.PR_EMPTY_LISTS], "1")
        self.assertEqual(pr[todo_controller.PR_LIST_OVERFLOW], "1")
        self.assertEqual(pr[todo_controller.LIST_START], "List 0")
        self.assertEqual(pr[todo_controller.PR_FOCUS_NAME], "List 0")
        self.assertEqual(pr[todo_controller.PR_FOCUS_POSITION], "1 of 9")
        self.assertEqual(pr[todo_controller.GLOBAL_TASK_START], "Overdue task")
        self.assertEqual(pr[todo_controller.GLOBAL_TASK_START + 3], "3")
        self.assertEqual(pr[todo_controller.FOCUS_TASK_START], "Task 0")
        self.assertEqual(pr[todo_controller.PR_CONTRACT_VERSION], "1")

    def test_empty_state_is_explicit(self):
        view = build_todo_view({"fetchedAt": None, "lists": []}, today=self.now.date())

        pr = todo_controller.build_pr_data(view, now=self.now)

        self.assertEqual(pr[todo_controller.PR_STATE], "0")
        self.assertEqual(pr[todo_controller.PR_EMPTY_MESSAGE], "All lists are clear")

    def test_run_pushes_the_gateway_payload_without_logging_task_content(self):
        snapshot = {
            "fetchedAt": "2026-09-19T23:00:00Z",
            "lists": [{
                "id": "list-1",
                "displayName": "Private list",
                "tasks": [task("Private task")],
            }],
        }
        service = FakeTodoService(snapshot)
        session = FakeSession()
        config = {
            "system": {"gateway_ip": "192.168.220.206", "store_code": "2000"},
            "todo": {
                "tag_id": "TAG_TODO",
                "layout_id": "4p20c_Todo",
                "gateway_timeout_seconds": 12,
            },
        }

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            pr = todo_controller.run(
                config,
                service=service,
                session=session,
                now=self.now,
            )

        self.assertEqual(service.force_values, [True])
        self.assertEqual(len(session.calls), 1)
        request = session.calls[0]
        self.assertEqual(request["url"], "http://192.168.220.206/api/product")
        self.assertEqual(request["timeout"], 12)
        product = request["json"]["product"][0]
        self.assertEqual(product["prCode"], "TAG_TODO")
        self.assertEqual(product["layoutId"], "4p20c_Todo")
        self.assertEqual(product["prInfo"], pr)
        self.assertEqual(product["nfc"], "")
        self.assertNotIn("Private list", output.getvalue())
        self.assertNotIn("Private task", output.getvalue())

    def test_run_requires_a_tag_id_before_fetching_tasks(self):
        service = FakeTodoService({"lists": []})
        config = {
            "system": {"gateway_ip": "192.168.220.206", "store_code": "2000"},
            "todo": {"tag_id": ""},
        }

        with self.assertRaisesRegex(ValueError, "todo.tag_id"):
            todo_controller.run(config, service=service, now=self.now)

        self.assertEqual(service.force_values, [])
if __name__ == "__main__":
    unittest.main()
