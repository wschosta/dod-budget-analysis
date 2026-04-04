"""Tests for api/routes/feedback.py — feedback submission endpoint."""

import json

import pytest


@pytest.fixture(autouse=True)
def _clean_feedback_file(tmp_path, monkeypatch):
    """Redirect feedback storage to a temp file and clean up after each test."""
    import api.routes.feedback as fb_module

    feedback_path = tmp_path / "feedback.json"
    monkeypatch.setattr(fb_module, "FEEDBACK_FILE", feedback_path)
    yield
    if feedback_path.exists():
        feedback_path.unlink()


class TestSubmitFeedback:
    def test_valid_bug_report(self, client):
        resp = client.post(
            "/api/v1/feedback",
            json={
                "type": "bug",
                "description": "The search results page shows no data for Army queries.",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "received"
        assert "id" in body
        assert len(body["id"]) > 0

    def test_valid_feature_request(self, client):
        resp = client.post(
            "/api/v1/feedback",
            json={
                "type": "feature",
                "description": "Please add the ability to export charts as PNG images.",
            },
        )
        assert resp.status_code == 201

    def test_valid_data_issue(self, client):
        resp = client.post(
            "/api/v1/feedback",
            json={
                "type": "data-issue",
                "description": "FY2025 amounts for Navy R-2 exhibit appear to be doubled.",
            },
        )
        assert resp.status_code == 201

    def test_with_optional_fields(self, client):
        resp = client.post(
            "/api/v1/feedback",
            json={
                "type": "bug",
                "description": "Charts don't render correctly in dark mode on Safari.",
                "email": "test@example.com",
                "page_url": "/charts",
            },
        )
        assert resp.status_code == 201

    def test_missing_type_returns_422(self, client):
        resp = client.post(
            "/api/v1/feedback",
            json={"description": "Some valid description text here."},
        )
        assert resp.status_code == 422

    def test_missing_description_returns_422(self, client):
        resp = client.post(
            "/api/v1/feedback",
            json={"type": "bug"},
        )
        assert resp.status_code == 422

    def test_invalid_type_returns_422(self, client):
        resp = client.post(
            "/api/v1/feedback",
            json={
                "type": "complaint",
                "description": "This is a valid length description for testing.",
            },
        )
        assert resp.status_code == 422

    def test_description_too_short_returns_422(self, client):
        resp = client.post(
            "/api/v1/feedback",
            json={"type": "bug", "description": "short"},
        )
        assert resp.status_code == 422

    def test_unique_ids(self, client):
        """Two submissions should produce different IDs."""
        payload = {
            "type": "bug",
            "description": "A repeated feedback item for uniqueness testing.",
        }
        r1 = client.post("/api/v1/feedback", json=payload).json()
        r2 = client.post("/api/v1/feedback", json=payload).json()
        assert r1["id"] != r2["id"]


class TestFeedbackFileStorage:
    def test_feedback_persisted_to_file(self, client, tmp_path, monkeypatch):
        import api.routes.feedback as fb_module

        feedback_path = tmp_path / "persist_test.json"
        monkeypatch.setattr(fb_module, "FEEDBACK_FILE", feedback_path)

        client.post(
            "/api/v1/feedback",
            json={
                "type": "bug",
                "description": "Testing persistence to JSON file on disk.",
            },
        )
        assert feedback_path.exists()
        data = json.loads(feedback_path.read_text())
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["type"] == "bug"
        assert "submitted_at" in data[0]

    def test_multiple_submissions_appended(self, client, tmp_path, monkeypatch):
        import api.routes.feedback as fb_module

        feedback_path = tmp_path / "append_test.json"
        monkeypatch.setattr(fb_module, "FEEDBACK_FILE", feedback_path)

        for i in range(3):
            client.post(
                "/api/v1/feedback",
                json={
                    "type": "feature",
                    "description": f"Feature request number {i} with enough chars.",
                },
            )
        data = json.loads(feedback_path.read_text())
        assert len(data) == 3

    def test_corrupted_file_recovery(self, client, tmp_path, monkeypatch):
        """Endpoint should recover from a corrupted feedback file."""
        import api.routes.feedback as fb_module

        feedback_path = tmp_path / "corrupted.json"
        feedback_path.write_text("NOT VALID JSON {{{")
        monkeypatch.setattr(fb_module, "FEEDBACK_FILE", feedback_path)

        resp = client.post(
            "/api/v1/feedback",
            json={
                "type": "bug",
                "description": "Testing recovery from corrupted feedback file.",
            },
        )
        assert resp.status_code == 201
        data = json.loads(feedback_path.read_text())
        assert len(data) == 1
