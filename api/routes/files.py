"""
Budget document file-serving endpoint.

GET /api/v1/files/{file_path}

Serves source budget documents (PDFs, Excel files) from the local
DoD_Budget_Documents directory.  The file_path is the relative path
stored in budget_lines.source_file (e.g. "FY2026/PB/US_Army/r1.xlsx").

Security: resolves the full path and verifies it is inside DOCS_DIR
before serving, preventing path traversal attacks.

Configuration:
    APP_DOCS_DIR   Root of the budget documents directory.
                   Default: DoD_Budget_Documents (relative to CWD).
"""

import mimetypes
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(tags=["files"])

# ---------------------------------------------------------------------------
# Docs directory — configurable via env var, defaults to DoD_Budget_Documents
# ---------------------------------------------------------------------------
_DOCS_DIR = Path(os.environ.get("APP_DOCS_DIR", "DoD_Budget_Documents")).resolve()


@router.get(
    "/files/{file_path:path}",
    summary="Serve a budget source document",
    response_class=FileResponse,
)
def serve_budget_file(file_path: str) -> FileResponse:
    """Return a budget source document (PDF or Excel) by its relative path.

    ``file_path`` must be the value stored in ``budget_lines.source_file``
    (a path relative to the DoD_Budget_Documents root).  Any attempt to
    escape that directory via ``..`` components is rejected with 400.
    """
    # Normalise and resolve to an absolute path
    try:
        target = (_DOCS_DIR / file_path).resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid file path")

    # Strict containment check — reject any traversal out of DOCS_DIR
    try:
        target.relative_to(_DOCS_DIR)
    except ValueError:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")

    if not target.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {file_path}",
        )
    if not target.is_file():
        raise HTTPException(status_code=400, detail="Not a file")

    media_type, _ = mimetypes.guess_type(str(target))
    if media_type is None:
        media_type = "application/octet-stream"

    return FileResponse(
        path=str(target),
        media_type=media_type,
        filename=target.name,
    )
