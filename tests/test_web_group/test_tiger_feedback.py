"""
Tests for the feedback API endpoint (TIGER-008).
"""
import json
import sqlite3
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Stub optional dependencies
for _mod in ("pdfplumber", "openpyxl", "pandas"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client(tmp_path):
    """TestClient with a temporary database."""
    db = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE budget_lines (id INTEGER PRIMARY KEY, source_file TEXT);
        CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY);
        CREATE TABLE ingested_files (file_path TEXT PRIMARY KEY, file_type TEXT,
            file_size INTEGER, file_modified REAL, ingested_at TEXT,
            row_count INTEGER, status TEXT);
    """)
    conn.close()

    from api.app import create_app
    app = create_app(db_path=db)
    return TestClient(app)


class TestFeedbackEndpoint:
    def test_valid_feedback_returns_201(self, client, tmp_path):
        """Valid feedback submission returns 201 with status and id."""
        with patch("api.routes.feedback.FEEDBACK_FILE", tmp_path / "feedback.json"):
            response = client.post("/api/v1/feedback", json={
                "type": "bug",
                "description": "Search results are missing FY2025 data for Army.",
            })
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "received"
        assert "id" in data
        # Verify UUID format
        assert len(data["id"]) == 36

    def test_valid_feedback_with_optional_fields(self, client, tmp_path):
        """Feedback with email and page_url is accepted."""
        with patch("api.routes.feedback.FEEDBACK_FILE", tmp_path / "feedback.json"):
            response = client.post("/api/v1/feedback", json={
                "type": "feature",
                "description": "Please add a comparison chart for FY2024 vs FY2025.",
                "email": "user@example.com",
                "page_url": "/charts",
            })
        assert response.status_code == 201

    def test_data_issue_type(self, client, tmp_path):
        """data-issue type is accepted."""
        with patch("api.routes.feedback.FEEDBACK_FILE", tmp_path / "feedback.json"):
            response = client.post("/api/v1/feedback", json={
                "type": "data-issue",
                "description": "PE 0602120A has incorrect funding amounts.",
            })
        assert response.status_code == 201

    def test_invalid_type_returns_422(self, client):
        """Invalid feedback type returns 422."""
        response = client.post("/api/v1/feedback", json={
            "type": "invalid-type",
            "description": "This should fail validation.",
        })
        assert response.status_code == 422

    def test_short_description_returns_422(self, client):
        """Description shorter than 10 chars returns 422."""
        response = client.post("/api/v1/feedback", json={
            "type": "bug",
            "description": "Short",
        })
        assert response.status_code == 422

    def test_missing_description_returns_422(self, client):
        """Missing description returns 422."""
        response = client.post("/api/v1/feedback", json={
            "type": "bug",
        })
        assert response.status_code == 422

    def test_feedback_logged_to_file(self, client, tmp_path):
        """Feedback is appended to feedback.json file."""
        feedback_file = tmp_path / "feedback.json"
        with patch("api.routes.feedback.FEEDBACK_FILE", feedback_file):
            client.post("/api/v1/feedback", json={
                "type": "bug",
                "description": "First feedback entry for testing purposes.",
            })
            client.post("/api/v1/feedback", json={
                "type": "feature",
                "description": "Second feedback entry for testing purposes.",
            })

        data = json.loads(feedback_file.read_text())
        assert len(data) == 2
        assert data[0]["type"] == "bug"
        assert data[1]["type"] == "feature"
