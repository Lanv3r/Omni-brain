import tempfile
import unittest
from pathlib import Path

from backend.database import dashboard_summary, initialize_database, list_records
from backend.seed import seed_demo_data


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test.sqlite3"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initialize_creates_empty_dashboard_tables(self):
        initialize_database(self.database_path)

        self.assertEqual(
            dashboard_summary(self.database_path),
            {"tickets": 0, "tasks": 0, "alerts": 0, "devices": 0},
        )

    def test_seed_loads_demo_records_idempotently(self):
        seed_demo_data(self.database_path)
        seed_demo_data(self.database_path)

        self.assertEqual(
            dashboard_summary(self.database_path),
            {"tickets": 5, "tasks": 7, "alerts": 6, "devices": 7},
        )
        self.assertEqual(
            list_records("tickets", self.database_path)[0]["id"], "DEMO-1048"
        )
        self.assertEqual(
            list_records("devices", self.database_path)[0]["id"], "BRIGHT-HQ-01"
        )


if __name__ == "__main__":
    unittest.main()
