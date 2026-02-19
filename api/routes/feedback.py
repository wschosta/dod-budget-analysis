"""
Feedback API endpoint (TIGER-008).

Provides a POST endpoint for users to submit feedback. Feedback is stored
in a local JSON file until GitHub integration is configured.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from api.models import FeedbackSubmission

router = APIRouter(prefix="/feedback", tags=["feedback"])

FEEDBACK_FILE = Path("feedback.json")


class FeedbackResponse(BaseModel):
    """Successful feedback submission response."""
    status: str = Field(..., description="Submission status", examples=["received"])
    id: str = Field(..., description="Unique feedback ID", examples=["a1b2c3d4-e5f6-7890-abcd-ef1234567890"])


class GitHubIntegrationNote(BaseModel):
    """Note about GitHub integration status."""
    detail: str = Field(..., description="Status message")


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=FeedbackResponse,
    responses={
        201: {"description": "Feedback received successfully"},
        422: {"description": "Validation error — invalid input"},
    },
    summary="Submit user feedback",
    description="Submit a bug report, feature request, or data issue. "
                "Feedback is stored locally until GitHub integration is configured.",
)
def submit_feedback(feedback: FeedbackSubmission) -> FeedbackResponse:
    """Accept user feedback and log it to a local JSON file."""
    feedback_id = str(uuid.uuid4())
    entry = {
        "id": feedback_id,
        "type": feedback.type,
        "description": feedback.description,
        "email": feedback.email,
        "page_url": feedback.page_url,
        "submitted_at": datetime.now().isoformat(),
    }

    # Append to feedback.json
    existing = []
    if FEEDBACK_FILE.exists():
        try:
            existing = json.loads(FEEDBACK_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            existing = []

    existing.append(entry)
    FEEDBACK_FILE.write_text(json.dumps(existing, indent=2))

    return FeedbackResponse(status="received", id=feedback_id)
