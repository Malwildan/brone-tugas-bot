from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from brone_tugas_bot.models import Assignment
from brone_tugas_bot.telegram import (
    TelegramConfig,
    TelegramConfigError,
    format_assignments_message,
)

JAKARTA = ZoneInfo("Asia/Jakarta")


def test_format_assignments_message_when_assignments_exist() -> None:
    # Given
    assignments = [
        Assignment(
            title="Tugas Individu - Pengembangan Website",
            due_at=datetime(2026, 6, 12, 23, 59, tzinfo=JAKARTA),
            url="https://brone.ub.ac.id/calendar/view.php?view=upcoming",
            source_text="Course event Deskripsi Tugas",
            course="Desain Antar Muka Pengguna",
            opened="Monday, 4 May 2026, 12:00 AM",
            description="Deskripsi Tugas: Mahasiswa diminta membuat website responsif.",
            submission_status="No submissions have been made yet",
            grading_status="Not graded",
            time_remaining="8 days 1 hour remaining",
        ),
    ]

    # When
    message = format_assignments_message(assignments)

    # Then
    assert "New BRONE assignment(s):" in message
    assert "Tugas Individu - Pengembangan Website" in message
    assert "Due: 2026-06-12 23:59" in message
    assert "Course: Desain Antar Muka Pengguna" in message
    assert "Opened: Monday, 4 May 2026, 12:00 AM" in message
    assert "Submission: No submissions have been made yet" in message
    assert "Grading: Not graded" in message
    assert "Remaining: 8 days 1 hour remaining" in message
    assert "Details:" in message
    assert "https://brone.ub.ac.id/calendar/view.php?view=upcoming" in message


def test_format_assignments_message_when_no_assignments_exist() -> None:
    # Given
    assignments: list[Assignment] = []

    # When
    message = format_assignments_message(assignments)

    # Then
    assert message == "No pending BRONE assignments found."


def test_telegram_config_when_missing_token() -> None:
    # Given
    token = ""
    chat_id = "7145117685"

    # When
    with pytest.raises(TelegramConfigError, match="TELEGRAM_BOT_TOKEN"):
        # Then
        TelegramConfig.from_settings(token=token, chat_id=chat_id)
