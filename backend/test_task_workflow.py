import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from backend.data_api import CreateTask, create_ticket_task, get_tasks, get_ticket_tasks
from backend.main import (
    TicketTaskSuggestionRequest,
    get_ticket_task_suggestions,
)
from backend.seed import seed_demo_data


class TicketTaskWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "workflow.sqlite3"
        self.previous_database_path = os.environ.get("DATABASE_PATH")
        os.environ["DATABASE_PATH"] = str(self.database_path)
        seed_demo_data()

    def tearDown(self):
        if self.previous_database_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = self.previous_database_path
        self.temp_dir.cleanup()

    def test_created_task_is_linked_and_listed_for_its_ticket(self):
        task = create_ticket_task(
            "DEMO-1048",
            CreateTask(
                title="Create a new account",
                description="Set up email and initial access.",
                due_date="2026-11-12",
                assignee="Morgan Chen",
                priority="High",
            ),
        )

        self.assertEqual(task["company"], "Brightside Studio")
        self.assertEqual(task["status"], "Pending")
        self.assertEqual(task["priority"], "High")
        self.assertEqual(task["ticket_id"], "DEMO-1048")
        self.assertEqual(task["due_date"], "2026-11-12")
        self.assertEqual(get_ticket_tasks("DEMO-1048"), [task])
        self.assertIn(task, get_tasks())

    def test_task_creation_rejects_unknown_ticket(self):
        with self.assertRaises(HTTPException) as error:
            create_ticket_task(
                "MISSING-1",
                CreateTask(title="Create a new account", due_date="2026-11-12"),
            )

        self.assertEqual(error.exception.status_code, 404)

    def test_task_creation_rejects_unknown_assignee_and_priority(self):
        with self.assertRaises(ValueError):
            CreateTask(
                title="Create a new account",
                due_date="2026-11-12",
                assignee="External Contractor",
            )
        with self.assertRaises(ValueError):
            CreateTask(
                title="Create a new account",
                due_date="2026-11-12",
                priority="Immediate",
            )

    @patch("backend.main.suggest_ticket_tasks")
    def test_suggested_tasks_are_validated_and_not_created(self, suggest_tasks):
        create_ticket_task(
            "DEMO-1048",
            CreateTask(
                title="Existing account review",
                due_date="2026-11-12",
            ),
        )
        suggest_tasks.return_value = (
            '{"suggestions":['
            '{"title":"Existing account review","description":"Duplicate.",'
            '"priority":"Medium"},'
            '{"title":"Verify email access",'
            '"description":"Confirm account sign-in and mail delivery.",'
            '"priority":"High"},'
            '{"title":"Confirm mailbox sync","description":"Check mail delivery.",'
            '"priority":"Medium"},'
            '{"title":"Check user login","description":"Test sign-in.",'
            '"priority":"Low"},'
            '{"title":"Extra suggestion","description":"Should be capped.",'
            '"priority":"Low"}]}'
        )

        result = get_ticket_task_suggestions(
            "DEMO-1048",
            TicketTaskSuggestionRequest(
                subject="New starter can't access email",
                description="Please verify the account.",
            ),
        )

        self.assertEqual(len(result.suggestions), 3)
        self.assertEqual(result.suggestions[0].title, "Verify email access")
        self.assertEqual(result.suggestions[0].priority, "High")
        self.assertEqual(len(get_ticket_tasks("DEMO-1048")), 1)
        suggest_tasks.assert_called_once()
        self.assertEqual(suggest_tasks.call_args.args[1], ["Existing account review"])

    @patch("backend.main.suggest_ticket_tasks")
    def test_task_suggestions_reject_invalid_model_output(self, suggest_tasks):
        suggest_tasks.return_value = (
            '{"suggestions":[{"title":"Bad priority",'
            '"description":"Not valid","priority":"Immediate"}]}'
        )

        with self.assertRaises(HTTPException) as error:
            get_ticket_task_suggestions(
                "DEMO-1048",
                TicketTaskSuggestionRequest(
                    subject="Subject",
                    description="Description",
                ),
            )

        self.assertEqual(error.exception.status_code, 502)

    def test_task_suggestions_reject_unknown_ticket(self):
        with self.assertRaises(HTTPException) as error:
            get_ticket_task_suggestions(
                "MISSING-1",
                TicketTaskSuggestionRequest(
                    subject="Subject",
                    description="Description",
                ),
            )

        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
