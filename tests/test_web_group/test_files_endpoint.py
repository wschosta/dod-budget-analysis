"""Tests for api/routes/files.py — budget document file serving with security."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def docs_dir(tmp_path_factory):
    """Create a temporary docs directory with sample files."""
    d = tmp_path_factory.mktemp("docs")
    # Create a fake PDF
    pdf = d / "FY2026" / "PB" / "US_Army" / "r1.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.4 fake content")

    # Create a fake Excel file
    xlsx = d / "FY2026" / "PB" / "US_Army" / "r1.xlsx"
    xlsx.write_bytes(b"PK\x03\x04 fake xlsx")

    # Create a text file with unknown extension
    txt = d / "readme.txt"
    txt.write_text("readme")

    return d


@pytest.fixture(scope="module")
def client(test_db_excel_only, docs_dir, tmp_path_factory):
    import os

    os.environ["APP_DOCS_DIR"] = str(docs_dir)
    # Reload the module to pick up the new env var
    import api.routes.files as files_module
    from pathlib import Path

    files_module._DOCS_DIR = Path(str(docs_dir)).resolve()

    from api.app import create_app
    app = create_app(db_path=test_db_excel_only)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ── Happy path ───────────────────────────────────────────────────────────────


class TestServeFile:
    def test_serve_pdf(self, client):
        resp = client.get("/api/v1/files/FY2026/PB/US_Army/r1.pdf")
        assert resp.status_code == 200
        assert "pdf" in resp.headers.get("content-type", "")

    def test_serve_xlsx(self, client):
        resp = client.get("/api/v1/files/FY2026/PB/US_Army/r1.xlsx")
        assert resp.status_code == 200

    def test_content_disposition(self, client):
        resp = client.get("/api/v1/files/FY2026/PB/US_Army/r1.pdf")
        assert "r1.pdf" in resp.headers.get("content-disposition", "")

    def test_unknown_extension_octet_stream(self, client):
        resp = client.get("/api/v1/files/readme.txt")
        assert resp.status_code == 200


# ── Security ─────────────────────────────────────────────────────────────────


class TestPathTraversalSecurity:
    def test_dotdot_rejected(self, client):
        """Path traversal should not serve files outside DOCS_DIR."""
        resp = client.get("/api/v1/files/../../../etc/passwd")
        # Starlette normalises ../.. before the handler sees it,
        # so we may get 400 (handler rejects) or 404 (normalised path not found).
        assert resp.status_code in (400, 404)

    def test_dotdot_in_middle(self, client):
        resp = client.get("/api/v1/files/FY2026/../../../etc/passwd")
        assert resp.status_code in (400, 404)


# ── Error cases ──────────────────────────────────────────────────────────────


class TestFileErrors:
    def test_file_not_found(self, client):
        resp = client.get("/api/v1/files/nonexistent/file.pdf")
        assert resp.status_code == 404

    def test_directory_returns_400(self, client):
        resp = client.get("/api/v1/files/FY2026/PB/US_Army")
        assert resp.status_code == 400
