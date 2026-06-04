from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Assignment:
    title: str
    due_at: datetime
    url: str | None
    source_text: str
    course: str | None = None
    opened: str | None = None
    description: str | None = None
    submission_status: str | None = None
    grading_status: str | None = None
    time_remaining: str | None = None

    @property
    def event_key(self) -> str:
        normalized_title = " ".join(self.title.lower().split())
        return f"brone:{normalized_title}:{self.due_at.isoformat()}"
