"""
Checkpoint System Tests

Tests for build progress tracking and resume capability:
- Checkpoint creation and storage
- File tracking for resume detection
- Session management
- Progress state persistence

Run with: pytest tests/test_checkpoint.py -v
"""

import tempfile
from pathlib import Path

import pytest

from build_budget_db import (
    create_database,
    _create_session_id,
    _save_checkpoint,
    _mark_file_processed,
    _get_last_checkpoint,
    _get_processed_files,
    _mark_session_complete,
)


class TestCheckpointCreation:
    """Test checkpoint creation and storage."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = create_database(db_path)
            yield conn
            conn.close()

    def test_create_session_id(self):
        """Session ID should be unique and properly formatted."""
        sid1 = _create_session_id()
        sid2 = _create_session_id()

        assert sid1.startswith("sess-")
        assert sid2.startswith("sess-")
        # Different calls should create different IDs
        assert sid1 != sid2

    def test_save_checkpoint(self, temp_db):
        """Checkpoint should be saved to database."""
        session_id = _create_session_id()

        _save_checkpoint(
            temp_db,
            session_id=session_id,
            files_processed=5,
            total_files=20,
            pages_processed=150,
            rows_inserted=2450,
            bytes_processed=125000,
            last_file="file5.xlsx",
            last_file_status="ok",
            notes="Test checkpoint"
        )

        # Verify checkpoint was saved
        cursor = temp_db.execute(
            "SELECT files_processed, total_files, pages_processed FROM build_progress WHERE session_id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        assert row is not None
        assert row == (5, 20, 150)

    def test_update_checkpoint(self, temp_db):
        """Checkpoint should update existing session."""
        session_id = _create_session_id()

        # First checkpoint
        _save_checkpoint(temp_db, session_id, 5, 20, 150, 2450, 125000)

        # Second checkpoint (update)
        _save_checkpoint(temp_db, session_id, 10, 20, 300, 4900, 250000)

        # Should only have one entry
        cursor = temp_db.execute(
            "SELECT COUNT(*) FROM build_progress WHERE session_id = ?",
            (session_id,)
        )
        assert cursor.fetchone()[0] == 1

        # Should have updated values
        cursor = temp_db.execute(
            "SELECT files_processed, pages_processed FROM build_progress WHERE session_id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        assert row == (10, 300)


class TestFileTracking:
    """Test file processing tracking."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = create_database(db_path)
            yield conn
            conn.close()

    def test_mark_file_processed(self, temp_db):
        """File should be marked as processed."""
        session_id = _create_session_id()

        _mark_file_processed(
            temp_db,
            session_id=session_id,
            file_path="path/to/file.xlsx",
            file_type="excel",
            rows_count=500,
            pages_count=0
        )

        # Verify file was recorded
        cursor = temp_db.execute(
            "SELECT file_type, rows_count FROM processed_files WHERE session_id = ? AND file_path = ?",
            (session_id, "path/to/file.xlsx")
        )
        row = cursor.fetchone()
        assert row is not None
        assert row == ("excel", 500)

    def test_get_processed_files(self, temp_db):
        """Should retrieve set of processed files for session."""
        session_id = _create_session_id()

        files = [
            ("path/to/file1.xlsx", "excel", 500, 0),
            ("path/to/file2.xlsx", "excel", 750, 0),
            ("path/to/file3.pdf", "pdf", 0, 45),
        ]

        for file_path, file_type, rows, pages in files:
            _mark_file_processed(temp_db, session_id, file_path, file_type, rows, pages)

        processed = _get_processed_files(temp_db, session_id)
        assert len(processed) == 3
        assert "path/to/file1.xlsx" in processed
        assert "path/to/file2.xlsx" in processed
        assert "path/to/file3.pdf" in processed


class TestCheckpointRetrieval:
    """Test checkpoint loading and resumption."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = create_database(db_path)
            yield conn
            conn.close()

    def test_get_last_checkpoint_none(self, temp_db):
        """Should return None when no checkpoint exists."""
        checkpoint = _get_last_checkpoint(temp_db)
        assert checkpoint is None

    def test_get_last_checkpoint(self, temp_db):
        """Should retrieve last checkpoint."""
        session_id = _create_session_id()

        _save_checkpoint(
            temp_db,
            session_id=session_id,
            files_processed=7,
            total_files=25,
            pages_processed=200,
            rows_inserted=3500,
            bytes_processed=175000,
            last_file="file7.xlsx",
            notes="Checkpoint test"
        )

        checkpoint = _get_last_checkpoint(temp_db)
        assert checkpoint is not None
        assert checkpoint["session_id"] == session_id
        assert checkpoint["files_processed"] == 7
        assert checkpoint["total_files"] == 25
        assert checkpoint["pages_processed"] == 200

    def test_get_last_checkpoint_ignores_completed(self, temp_db):
        """Should not return completed sessions."""
        session_id1 = _create_session_id()
        session_id2 = _create_session_id()

        # Save and complete first session
        _save_checkpoint(temp_db, session_id1, 5, 20, 150, 2450, 125000)
        _mark_session_complete(temp_db, session_id1, "Completed")

        # Save incomplete second session
        _save_checkpoint(temp_db, session_id2, 3, 20, 90, 1470, 75000)

        # Should get second (incomplete) session
        checkpoint = _get_last_checkpoint(temp_db)
        assert checkpoint["session_id"] == session_id2


class TestSessionCompletion:
    """Test session completion marking."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = create_database(db_path)
            yield conn
            conn.close()

    def test_mark_session_complete(self, temp_db):
        """Session should be marked as completed."""
        session_id = _create_session_id()

        _save_checkpoint(temp_db, session_id, 20, 20, 1200, 25000, 1250000)
        _mark_session_complete(temp_db, session_id, "All files processed successfully")

        # Verify status changed
        cursor = temp_db.execute(
            "SELECT status, notes FROM build_progress WHERE session_id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        assert row[0] == "completed"
        assert "All files processed successfully" in row[1]


class TestCheckpointIntegration:
    """Integration tests for checkpoint system."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = create_database(db_path)
            yield conn
            conn.close()

    def test_full_checkpoint_workflow(self, temp_db):
        """Test complete checkpoint workflow: save -> track -> retrieve -> complete."""
        session_id = _create_session_id()

        # Simulate processing files
        files = [
            ("file1.xlsx", "excel", 500),
            ("file2.xlsx", "excel", 750),
            ("file3.pdf", "pdf", None),
            ("file4.pdf", "pdf", None),
        ]

        for i, (filename, ftype, rows) in enumerate(files, 1):
            _mark_file_processed(
                temp_db,
                session_id,
                f"path/{filename}",
                ftype,
                rows_count=rows or 0,
                pages_count=25 if ftype == "pdf" else 0
            )

            _save_checkpoint(
                temp_db,
                session_id,
                files_processed=i,
                total_files=4,
                pages_processed=i * 25,
                rows_inserted=(500 + 750),
                bytes_processed=i * 100000,
                last_file=filename
            )

        # Retrieve checkpoint
        checkpoint = _get_last_checkpoint(temp_db)
        assert checkpoint["files_processed"] == 4
        assert checkpoint["pages_processed"] == 100

        # Verify processed files
        processed = _get_processed_files(temp_db, session_id)
        assert len(processed) == 4

        # Complete session
        _mark_session_complete(temp_db, session_id, "Workflow test completed")

        # Verify completion
        checkpoint = _get_last_checkpoint(temp_db)
        assert checkpoint is None  # Completed sessions shouldn't be returned


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
