from dataclasses import dataclass
from itertools import islice
from typing import TypedDict

import httpx2

from brone_tugas_bot.http_client import create_client
from brone_tugas_bot.models import Assignment

DESCRIPTION_WORD_LIMIT = 90


class TelegramConfigError(RuntimeError):
    pass


class TelegramSendError(RuntimeError):
    pass


class TelegramPayload(TypedDict):
    chat_id: str
    text: str
    disable_web_page_preview: bool


@dataclass(frozen=True, slots=True)
class TelegramConfig:
    bot_token: str
    chat_id: str

    @classmethod
    def from_settings(cls, *, token: str, chat_id: str) -> "TelegramConfig":
        if not token.strip():
            msg = "Missing TELEGRAM_BOT_TOKEN in .env."
            raise TelegramConfigError(msg)
        if not chat_id.strip():
            msg = "Missing TELEGRAM_CHAT_ID in .env."
            raise TelegramConfigError(msg)
        return cls(bot_token=token.strip(), chat_id=chat_id.strip())


def format_assignments_message(assignments: list[Assignment]) -> str:
    if not assignments:
        return "No pending BRONE assignments found."
    lines = ["New BRONE assignment(s):"]
    for assignment in assignments:
        lines.extend(_assignment_lines(assignment))
    return "\n".join(lines)


def _assignment_lines(assignment: Assignment) -> list[str]:
    lines = [
        "",
        assignment.title,
        f"Due: {assignment.due_at.strftime('%Y-%m-%d %H:%M')}",
    ]
    if assignment.course is not None:
        lines.append(f"Course: {assignment.course}")
    if assignment.opened is not None:
        lines.append(f"Opened: {assignment.opened}")
    if assignment.submission_status is not None:
        lines.append(f"Submission: {assignment.submission_status}")
    if assignment.grading_status is not None:
        lines.append(f"Grading: {assignment.grading_status}")
    if assignment.time_remaining is not None:
        lines.append(f"Remaining: {assignment.time_remaining}")
    if assignment.description is not None:
        lines.extend(["", *_description_lines(assignment.description)])
    if assignment.url is not None:
        lines.extend(["", assignment.url])
    return lines


def _description_lines(description: str) -> list[str]:
    compact = " ".join(description.split())
    words = compact.split()
    preview = " ".join(islice(words, DESCRIPTION_WORD_LIMIT))
    suffix = "..." if len(words) > DESCRIPTION_WORD_LIMIT else ""
    return ["Details:", f"{preview}{suffix}"]


def send_telegram_message(text: str, config: TelegramConfig) -> None:
    payload: TelegramPayload = {
        "chat_id": config.chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    try:
        with create_client(base_url=f"https://api.telegram.org/bot{config.bot_token}") as client:
            response = client.post("/sendMessage", json=payload)
            response.raise_for_status()
    except httpx2.HTTPError as error:
        msg = f"Telegram send failed: {error}"
        raise TelegramSendError(msg) from error


def send_assignments_to_telegram(assignments: list[Assignment], config: TelegramConfig) -> None:
    send_telegram_message(format_assignments_message(assignments), config)
