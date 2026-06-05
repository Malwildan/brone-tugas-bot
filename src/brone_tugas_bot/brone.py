import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
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
    debug_dump_dir: Path | None = None,
) -> list[Assignment]:
    settings.browser_state_dir.mkdir(parents=True, exist_ok=True)
    if debug_dump_dir is not None:
        debug_dump_dir.mkdir(parents=True, exist_ok=True)
    selector_counts: dict[str, int] = {}
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(settings.browser_state_dir),
            headless=headless,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(settings.brone_url, wait_until="domcontentloaded")
        _complete_login(page, settings=settings, manual_login=manual_login)
        candidates = _collect_candidates_from_calendar(
            page, settings.brone_url, debug_dump_dir=debug_dump_dir, counts=selector_counts
        )
        if not _has_assignment_url(candidates):
            print(
                "[brone] calendar yielded no assign candidates; falling back to dashboard.",
                flush=True,
            )
            dashboard_candidates = _collect_candidates_from_dashboard(
                page, settings.brone_url, debug_dump_dir=debug_dump_dir, counts=selector_counts
            )
            candidates.extend(dashboard_candidates)
        assignments = parse_assignments(candidates, now=now, lookahead_days=lookahead_days)
        detailed_assignments = [
            _with_assignment_detail(page, assignment) for assignment in assignments
        ]
        context.close()

    if selector_counts:
        summary = ", ".join(f"{sel}={n}" for sel, n in selector_counts.items())
        print(f"[brone] selector matches: {summary}", flush=True)
    return detailed_assignments


def _complete_login(page: Page, *, settings: Settings, manual_login: bool) -> None:
    if _handle_saml_redirect(page, wait_for_brone=True):
        pass
    if page.locator("#username").count() > 0:
        if manual_login:
            page.wait_for_url(lambda url: "brone.ub.ac.id" in url, timeout=300_000)
            return
        page.locator("#username").fill(settings.brone_username)
        page.locator("#password").fill(settings.brone_password)
        page.locator("#kc-login").click()
        page.wait_for_load_state("domcontentloaded")
        _handle_saml_redirect(page, wait_for_brone=True)
        if page.locator("#username").count() > 0:
            msg = "Login still shows UB Auth. Use --manual-login or check credentials."
            raise LoginFailedError(msg)


def _handle_saml_redirect(page: Page, *, wait_for_brone: bool = False) -> bool:
    if "iam.ub.ac.id" not in page.url:
        return False
    print(f"[brone] caught SAML redirect; dumping page for debug", flush=True)
    try:
        body_text = page.locator("body").inner_text(timeout=5_000)
        print(f"[brone] SAML page body preview: {body_text[:300]}", flush=True)
    except Exception:
        pass
    try:
        page.locator("form").first.locator("input[type='submit'], button[type='submit'], button").first.click(timeout=3_000)
        print("[brone] clicked SAML form submit", flush=True)
    except Exception:
        try:
            page.keyboard.press("Enter")
            print("[brone] pressed Enter on SAML form", flush=True)
        except Exception as error:
            print(f"[brone] SAML form submit failed: {error}", flush=True)
    if wait_for_brone:
        try:
            page.wait_for_url(lambda url: "brone.ub.ac.id" in url, timeout=15_000)
        except Exception:
            print("[brone] SAML didn't resolve — forcing brone.ub.ac.id navigation", flush=True)
            page.goto("https://brone.ub.ac.id/my/", wait_until="domcontentloaded")
            page.wait_for_timeout(3_000)
    return True


def _clear_iam_cookies(page: Page) -> None:
    try:
        cookies = page.context.cookies()
        cleared = 0
        for cookie in cookies:
            domain = cookie.get("domain", "")
            if "iam.ub.ac.id" in domain or "keycloak" in domain.lower():
                page.context.clear_cookies(name=cookie.get("name"))
                cleared += 1
        print(f"[brone] cleared {cleared} IAM/Keycloak cookies", flush=True)
    except Exception as error:
        print(f"[brone] failed to clear IAM cookies: {error}", flush=True)


def _visit_upcoming_calendar(page: Page, home_url: str) -> None:
    calendar_url = urljoin(home_url, "/calendar/view.php?view=upcoming")
    page.goto(calendar_url, wait_until="domcontentloaded")


def _wait_for_dashboard(page: Page, *, debug_dump_dir: Path | None) -> None:
    _handle_saml_redirect(page, wait_for_brone=True)
    try:
        page.locator(
            "[data-region='event-item'], [data-region='event-list-content'] .event, "
            "[data-region='event-list-content']"
        ).first.wait_for(state="visible", timeout=10_000)
    except Exception:
        if debug_dump_dir is not None:
            _dump_html(page, debug_dump_dir / "dashboard.html")
        print(
            f"[brone] dashboard did not render event items; current url={page.url}",
            flush=True,
        )


def _wait_for_calendar(page: Page, *, debug_dump_dir: Path | None) -> None:
    _handle_saml_redirect(page, wait_for_brone=True)
    try:
        page.locator(
            "[data-region='event-item'], [data-region='event-list-content'] .event, "
            "[data-region='event-list-content']"
        ).first.wait_for(state="visible", timeout=10_000)
    except Exception:
        if debug_dump_dir is not None:
            _dump_html(page, debug_dump_dir / "calendar.html")
        print(
            f"[brone] calendar did not render event items; current url={page.url}",
            flush=True,
        )


def _collect_candidates_from_dashboard(
    page: Page,
    home_url: str,
    *,
    debug_dump_dir: Path | None,
    counts: dict[str, int],
) -> list[Candidate]:
    page.goto(home_url, wait_until="domcontentloaded")
    _wait_for_dashboard(page, debug_dump_dir=debug_dump_dir)
    return _scrape_selectors(page, debug_dump_dir=debug_dump_dir, counts=counts, source="dashboard")


def _collect_candidates_from_calendar(
    page: Page,
    home_url: str,
    *,
    debug_dump_dir: Path | None,
    counts: dict[str, int],
) -> list[Candidate]:
    _visit_upcoming_calendar(page, home_url)
    _wait_for_calendar(page, debug_dump_dir=debug_dump_dir)
    return _scrape_selectors(page, debug_dump_dir=debug_dump_dir, counts=counts, source="calendar")


def _scrape_selectors(
    page: Page,
    *,
    debug_dump_dir: Path | None,
    counts: dict[str, int],
    source: str,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for selector in CARD_SELECTORS:
        try:
            elements = page.locator(selector).all()
        except Exception as error:
            print(f"[brone] selector {selector!r} failed on {source}: {error}", flush=True)
            counts[selector] = 0
            continue
        counts[selector] = len(elements)
        for element in elements:
            try:
                text = element.inner_text(timeout=2_000).strip()
            except Exception:
                continue
            if not text:
                continue
            url = _candidate_url(element)
            candidates.append(Candidate(text=text, url=url))
    if debug_dump_dir is not None and not candidates:
        _dump_html(page, debug_dump_dir / f"{source}-no-candidates.html")
    return candidates


def _dump_html(page: Page, path: Path) -> None:
    try:
        path.write_text(page.content(), encoding="utf-8")
    except Exception as error:
        print(f"[brone] failed to dump html to {path}: {error}", flush=True)


def _has_assignment_url(candidates: list[Candidate]) -> bool:
    return any(
        candidate.url is not None and "/mod/assign/view.php" in candidate.url
        for candidate in candidates
    )


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
