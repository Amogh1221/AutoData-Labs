import sys
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("playwright", MagicMock())
sys.modules.setdefault("playwright.sync_api", MagicMock())

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routes import router
from api.dependencies import (
    get_source_service, get_research_service, get_completion_service, get_store, get_planner_service
)

app = FastAPI()
app.include_router(router)
client = TestClient(app)

class TestRoutes(unittest.TestCase):
    def setUp(self):
        self.mock_store = MagicMock()
        self.mock_source_service = MagicMock()
        self.mock_research_service = MagicMock()
        self.mock_completion_service = MagicMock()
        self.mock_planner = MagicMock()

        app.dependency_overrides[get_store] = lambda: self.mock_store
        app.dependency_overrides[get_source_service] = lambda: self.mock_source_service
        app.dependency_overrides[get_research_service] = lambda: self.mock_research_service
        app.dependency_overrides[get_completion_service] = lambda: self.mock_completion_service
        app.dependency_overrides[get_planner_service] = lambda: self.mock_planner

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("api.routes.executor.submit")
    def test_start_extraction_success(self, mock_submit):
        mock_future = MagicMock()
        mock_submit.return_value = mock_future

        payload = {
            "topic": "AI Startups 2026",
            "columns": [
                {"name": "company_name", "type": "string", "reason": "Name of startup", "required": True},
                {"name": "valuation", "type": "string", "reason": "Valuation", "required": False}
            ]
        }
        response = client.post("/api/start_extraction", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "started")
        self.assertIn("run_id", data)

    def test_stop_extraction_success(self):
        payload = {"run_id": "test-run-123"}
        response = client.post("/api/stop_extraction", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "stopping")

    def test_pause_and_resume_extraction_success(self):
        payload = {"run_id": "test-run-123"}
        response = client.post("/api/pause_extraction", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "paused")

        response = client.post("/api/resume_extraction", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "running")
