import unittest
from unittest.mock import patch

from backend.main import PROCESS_PLAN_SOURCES, get_process_plans


class ProcessPlanEndpointTests(unittest.TestCase):
    @patch("backend.main._fetch_document")
    def test_returns_selected_source_guides_without_external_links(self, fetch_document):
        fetch_document.side_effect = lambda source: {
            "path": source["path"],
            "title": source["title"],
            "content": f"# {source['title']}\n\n## Steps\n1. Do the work.",
        }

        result = get_process_plans()

        self.assertEqual(
            [plan["id"] for plan in result["plans"]],
            [source["id"] for source in PROCESS_PLAN_SOURCES],
        )
        self.assertEqual(len(result["plans"]), len(PROCESS_PLAN_SOURCES))
        for plan in result["plans"]:
            self.assertNotIn("source_url", plan)
            self.assertNotIn("source_path", plan)
            self.assertIn("1. Do the work.", plan["content"])

    @patch("backend.main._fetch_document")
    def test_upstream_errors_are_not_hidden(self, fetch_document):
        from fastapi import HTTPException

        fetch_document.side_effect = HTTPException(
            status_code=502, detail="Could not reach practice API."
        )

        with self.assertRaises(HTTPException) as error:
            get_process_plans()

        self.assertEqual(error.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
