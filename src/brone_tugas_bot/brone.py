import re
from dataclasses import replace
from datetime import datetime
from typing import Final
from urllib.parse import urljoin

from playwright.sync_api import Locator, Page, sync_playwright

from brone_tugas_bot.models import Assignment
from brone_tugas_bot.parser import Candidate, parse_assignments
from brone_tugas_bot.settings import Settings

CARD_SELECTORS: Final = [
    "[data-region='event-item']",
    "[data-region='event-list-content'] .event",
    ".event",
    ".block_timeline .list-group-item",
    ".block_myoverview .card",
    ".dashboard-card",
    ".course-content li.activity",
    ".activity-item",
    ".list-group-item",
    ".card",
]
STATUS_LABELS: Final = (
    "Submission status",
    "Grading status",
    "Time remaining",
    "Last modified",
)
OPENED_RE: Final = re.compile(r"Opened:\s*(?P<value>.+?)(?:\n|Due:)", re.IGNORECASE | re.DOTALL)


class LoginFailedError(RuntimeError):
    pass


def discover_assignments(
    settings: Settings,
    *,
    now: datetime,
    lookahead_days: int,
    manual_login: bool,
    headless: bool,
) -> list[Assignment]:
    settings.browser_state_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(settings.browser_state_dir),
            headless=headless,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(settings.brone_url, wait_until="domcontentloaded")
        _complete_login(page, settings=settings, manual_login=manual_login)
        _visit_upcoming_calendar(page, settings.brone_url)
        candidates = _collect_candidates(page)
        assignments = parse_assignments(candidates, now=now, lookahead_days=lookahead_days)
        detailed_assignments = [
            _with_assignment_detail(page, assignment) for assignment in assignments
        ]
        context.close()

    return detailed_assignments


def _complete_login(page: Page, *, settings: Settings, manual_login: bool) -> None:
    if page.locator("#username").count() == 0:
        return
    if manual_login:
        page.wait_for_url(lambda url: "brone.ub.ac.id" in url, timeout=300_000)
        return
    page.locator("#username").fill(settings.brone_username)
    page.locator("#password").fill(settings.brone_password)
    page.locator("#kc-login").click()
    page.wait_for_load_state("domcontentloaded")
    if page.locator("#username").count() > 0:
        msg = "Login still shows UB Auth. Use --manual-login or check credentials."
        raise LoginFailedError(msg)


def _visit_upcoming_calendar(page: Page, home_url: str) -> None:
    calendar_url = urljoin(home_url, "/calendar/view.php?view=upcoming")
    page.goto(calendar_url, wait_until="domcontentloaded")


def _collect_candidates(page: Page) -> list[Candidate]:
    candidates: list[Candidate] = []
    for selector in CARD_SELECTORS:
        for element in page.locator(selector).all():
            text = element.inner_text(timeout=2_000).strip()
            if not text:
                continue
            url = _candidate_url(element)
            candidates.append(Candidate(text=text, url=url))
    return candidates


def _candidate_url(element: Locator) -> str | None:
    assignment_link = element.locator("a[href*='mod/assign/view.php']").first
    if assignment_link.count() > 0:
        return assignment_link.get_attribute("href")
    first_link = element.locator("a").first
    if first_link.count() > 0:
        return first_link.get_attribute("href")
    return None


def _with_assignment_detail(page: Page, assignment: Assignment) -> Assignment:
    if assignment.url is None or "/mod/assign/view.php" not in assignment.url:
        return assignment
    page.goto(assignment.url, wait_until="domcontentloaded")
    detail_text = page.locator("body").inner_text(timeout=10_000)
    title = _first_text(page, "h1") or assignment.title
    course = _course_name(page) or assignment.course
    description = _first_text(page, ".activity-description") or assignment.description
    opened = _opened_text(detail_text)
    status_values = _status_values(detail_text)
    return replace(
        assignment,
        title=title,
        course=course,
        opened=opened,
        description=description,
        submission_status=status_values.get("Submission status"),
        grading_status=status_values.get("Grading status"),
        time_remaining=status_values.get("Time remaining"),
    )


def _first_text(page: Page, selector: str) -> str | None:
    locator = page.locator(selector).first
    if locator.count() == 0:
        return None
    text = locator.inner_text(timeout=3_000).strip()
    return text or None


def _course_name(page: Page) -> str | None:
    breadcrumb = page.locator(".breadcrumb-item").first
    if breadcrumb.count() > 0:
        text = breadcrumb.inner_text(timeout=3_000).strip()
        if text:
            return text
    title = page.title()
    if ":" not in title:
        return None
    course_title = title.split(":", maxsplit=1)[0]
    return course_title.removeprefix("FILKOM_SI_").rsplit("_", maxsplit=1)[0] or None


def _opened_text(text: str) -> str | None:
    match = OPENED_RE.search(text)
    if match is None:
        return None
    return " ".join(match.group("value").split())


def _status_values(text: str) -> dict[str, str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    values: dict[str, str] = {}
    for index, line in enumerate(lines):
        prefixed = _prefixed_status_value(line)
        if prefixed is not None:
            label, value = prefixed
            values[label] = value
            continue
        if line not in STATUS_LABELS:
            continue
        value = _next_status_value(lines[index + 1 :])
        if value is not None:
            values[line] = value
    return values


def _prefixed_status_value(line: str) -> tuple[str, str] | None:
    normalized = " ".join(line.split())
    for label in STATUS_LABELS:
        prefix = f"{label} "
        if not normalized.startswith(prefix):
            continue
        value = _strip_status_label(normalized.removeprefix(prefix), label)
        if value:
            return label, value
    return None


def _strip_status_label(value: str, label: str) -> str:
    stripped = value.strip()
    while stripped.startswith(label):
        stripped = stripped.removeprefix(label).strip()
    return stripped


def _next_status_value(lines: list[str]) -> str | None:
    for line in lines:
        if line in STATUS_LABELS:
            continue
        prefixed = _prefixed_status_value(line)
        if prefixed is not None:
            return prefixed[1]
        return line
    return None
