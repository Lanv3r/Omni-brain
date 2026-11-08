import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.data_api import CreateTask, create_ticket_task
from backend.database import database_connection
from backend.main import get_practice_ticket, get_practice_tickets
from backend.seed import seed_demo_data


class PracticeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "practice.sqlite3"
        self.previous_database_path = os.environ.get("DATABASE_PATH")
        os.environ["DATABASE_PATH"] = str(self.database_path)
        seed_demo_data()

    def tearDown(self):
        if self.previous_database_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = self.previous_database_path
        self.temp_dir.cleanup()

    @patch("backend.main._practice_list")
    def test_ticket_list_joins_client_data_and_links_tasks(self, practice_list):
        company = {
            "id": 1001,
            "name": "Tidewater Ledger CPAs",
            "industry": "Financial Services",
            "core_plan": "Omni+ Proactive",
            "service_plans": ["Omni+ Proactive", "Server Backup"],
        }
        issue = {
            "id": 10042,
            "title": "Outlook keeps asking for credentials",
            "description": "Outlook repeatedly requests a password.",
            "status": "inprogress",
            "priority": "normal",
            "against_id": 1001,
            "contact_id": 3004,
            "assignee_name": "Jordan Blake",
            "date_opened": "2026-11-05T14:02:11Z",
            "class": "Email & M365",
        }
        practice_list.side_effect = lambda path: (
            [company] if "companies" in path else [issue]
        )

        result = get_practice_tickets()

        self.assertEqual(result["total"], 1)
        ticket = result["tickets"][0]
        self.assertEqual(ticket["id"], "ACC-10042")
        self.assertEqual(ticket["status"], "In progress")
        self.assertEqual(ticket["priority"], "Medium")
        self.assertEqual(ticket["client"]["name"], company["name"])
        self.assertEqual(ticket["client"]["industry"], company["industry"])

        with database_connection() as connection:
            record = connection.execute(
                "SELECT description, external_company_id FROM tickets WHERE id = ?",
                ("ACC-10042",),
            ).fetchone()
        self.assertEqual(record["description"], issue["description"])
        self.assertEqual(record["external_company_id"], 1001)

        task = create_ticket_task(
            "ACC-10042",
            CreateTask(title="Check mailbox sign-in", due_date="2026-11-09"),
        )
        self.assertEqual(task["company"], company["name"])
        self.assertEqual(task["ticket_id"], "ACC-10042")

    @patch("backend.main._practice_item")
    @patch("backend.main._practice_list")
    def test_ticket_details_include_contact_and_client_profile(
        self, practice_list, practice_item
    ):
        issue = {
            "id": 10042,
            "title": "Outlook keeps asking for credentials",
            "description": "Outlook repeatedly requests a password.",
            "status": "open",
            "priority": "high",
            "against_id": 1001,
            "contact_id": 3004,
            "date_opened": "2026-11-05T14:02:11Z",
            "class": "Email & M365",
        }
        company = {
            "id": 1001,
            "name": "Tidewater Ledger CPAs",
            "industry": "Financial Services",
            "core_plan": "Omni+ Proactive",
            "service_plans": ["Omni+ Proactive"],
        }
        practice_item.side_effect = lambda path: (
            issue if path.endswith("/issues/10042")
            else company if path.endswith("/companies/1001")
            else {"name": "Dana Brooks"}
        )
        practice_list.return_value = [
            {"field_name": "Employee", "value": "14"},
            {"field_name": "Parent Company", "value": None},
        ]

        result = get_practice_ticket("ACC-10042")

        self.assertEqual(result["requester"], "Dana Brooks")
        self.assertEqual(result["client"]["employee_count"], 14)
        self.assertIsNone(result["client"]["parent_company"])
        self.assertEqual(result["ticket_class"], "Email & M365")


if __name__ == "__main__":
    unittest.main()
