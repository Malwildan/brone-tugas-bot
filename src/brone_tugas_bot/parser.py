import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

import dateparser

from brone_tugas_bot.models import Assignment

KEYWORDS: Final = (
    "assignment",
    "assignments",
    "tugas",
    "quiz",
    "kuis",
    "due",
    "deadline",
    "tenggat",
    "dikumpulkan",
    "submission",
)

DATE_HINT_RE: Final = re.compile(
    r"(?P<hint>"
    r"(?:due|deadline|tenggat|dikumpulkan|submission)[^\n\r]{0,90}|"
    r"\b\d{1,2}\s+[A-Za-zÀ-ÿ]+(?:\s+\d{4})?(?:,?\s+\d{1,2}:\d{2})?"
    r")",
    re.IGNORECASE,
)
DATE_LABEL_RE: Final = re.compile(
    r"^(?:due|deadline|tenggat|dikumpulkan|submission)\s*:?\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Candidate:
    text: str
    url: str | None


def parse_assignments(
    candidates: Iterable[Candidate],
    *,
    now: datetime,
    lookahead_days: int,
) -> list[Assignment]:
    deadline = now.timestamp() + (lookahead_days * 24 * 60 * 60)
    seen: set[str] = set()
    assignments: list[Assignment] = []

    for candidate in candidates:
        if not _looks_like_assignment(candidate.text):
            continue
        due_at = _extract_due_date(candidate.text, now=now)
        if due_at is None:
            continue
        if due_at.timestamp() < now.timestamp() or due_at.timestamp() > deadline:
            continue
        title = _extract_title(candidate.text)
        assignment = Assignment(
            title=title,
            due_at=due_at,
            url=_assignment_url(candidate.url),
            source_text=_compact(candidate.text),
            course=_extract_course(candidate.text),
            description=_extract_description(candidate.text),
        )
        if assignment.event_key in seen:
            continue
        seen.add(assignment.event_key)
        assignments.append(assignment)

    return sorted(assignments, key=lambda item: item.due_at)


def _looks_like_assignment(text: str) -> bool:
    lower = text.lower()
    return any(keyword in lower for keyword in KEYWORDS)


def _extract_due_date(text: str, *, now: datetime) -> datetime | None:
    for match in DATE_HINT_RE.finditer(text):
        date_text = DATE_LABEL_RE.sub("", match.group("hint")).strip()
        parsed = dateparser.parse(
            date_text,
            languages=["en", "id"],
            settings={
                "PREFER_DATES_FROM": "future",
                "RELATIVE_BASE": now,
                "RETURN_AS_TIMEZONE_AWARE": False,
            },
        )
        if parsed is not None:
            clean = parsed.replace(second=0, microsecond=0)
            if clean.tzinfo is None:
                return clean.replace(tzinfo=ZoneInfo("Asia/Jakarta"))
            return clean
    return None


def _extract_title(text: str) -> str:
    compact = _compact(text)
    first_line = compact.split(" is due ", maxsplit=1)[0]
    first_line = first_line.split(" Due ", maxsplit=1)[0]
    return first_line[:120].strip(" -:") or "BRONE Assignment"


def _extract_course(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if line.casefold() == "course event" and index + 1 < len(lines):
            return lines[index + 1]
    return None


def _extract_description(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if line.casefold() != "course event":
            continue
        description_lines = lines[index + 2 :]
        description = _compact(" ".join(description_lines))
        return description or None
    compact = _compact(text)
    marker = "Deskripsi Tugas:"
    if marker not in compact:
        return None
    description = marker + compact.split(marker, maxsplit=1)[1].strip()
    return description or None


def _assignment_url(url: str | None) -> str | None:
    if url is None:
        return None
    return url.replace("&action=editsubmission", "").replace("?action=editsubmission", "")


def _compact(text: str) -> str:
    return " ".join(text.split())
