from datetime import datetime
from zoneinfo import ZoneInfo

from brone_tugas_bot.parser import Candidate, parse_assignments

JAKARTA = ZoneInfo("Asia/Jakarta")


def test_parse_assignments_when_moodle_due_text_is_present() -> None:
    # Given
    now = datetime(2026, 6, 4, 20, 0, tzinfo=JAKARTA)
    candidates = [
        Candidate(
            text="Assignment 3: UI Kit\nDue Friday, 5 June 2026, 23:59",
            url="https://brone.ub.ac.id/mod/assign/view.php?id=123",
        ),
    ]

    # When
    assignments = parse_assignments(candidates, now=now, lookahead_days=30)

    # Then
    assert len(assignments) == 1
    assert assignments[0].title == "Assignment 3: UI Kit"
    assert assignments[0].due_at == datetime(2026, 6, 5, 23, 59, tzinfo=JAKARTA)
    assert assignments[0].url == "https://brone.ub.ac.id/mod/assign/view.php?id=123"


def test_parse_assignments_when_calendar_card_has_course_and_description() -> None:
    # Given
    now = datetime(2026, 6, 4, 20, 0, tzinfo=JAKARTA)
    candidates = [
        Candidate(
            text=(
                "Tugas Individu - Pengembangan Website is due\n"
                "Friday, 12 June, 11:59 PM\n"
                "Course event\n"
                "Desain Antar Muka Pengguna\n"
                "Deskripsi Tugas: Build a hosted website."
            ),
            url="https://brone.ub.ac.id/mod/assign/view.php?id=187675&action=editsubmission",
        ),
    ]

    # When
    assignments = parse_assignments(candidates, now=now, lookahead_days=30)

    # Then
    assert len(assignments) == 1
    assert assignments[0].title == "Tugas Individu - Pengembangan Website"
    assert assignments[0].course == "Desain Antar Muka Pengguna"
    assert assignments[0].description == "Deskripsi Tugas: Build a hosted website."
    assert assignments[0].url == "https://brone.ub.ac.id/mod/assign/view.php?id=187675"


def test_parse_assignments_when_text_has_no_deadline() -> None:
    # Given
    now = datetime(2026, 6, 4, 20, 0, tzinfo=JAKARTA)
    candidates = [Candidate(text="Assignment folder with no visible date", url=None)]

    # When
    assignments = parse_assignments(candidates, now=now, lookahead_days=30)

    # Then
    assert assignments == []


def test_parse_assignments_when_deadline_is_duplicate() -> None:
    # Given
    now = datetime(2026, 6, 4, 20, 0, tzinfo=JAKARTA)
    text = "Tugas Besar Due 10 June 2026, 21:00"
    candidates = [Candidate(text=text, url=None), Candidate(text=text, url=None)]

    # When
    assignments = parse_assignments(candidates, now=now, lookahead_days=30)

    # Then
    assert len(assignments) == 1
