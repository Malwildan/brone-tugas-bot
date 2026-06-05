from collections.abc import Callable
from typing import Final, Protocol

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


class LoginFailedError(RuntimeError):
    pass


IAM_BLOCK_MARKERS: Final = (
    "sorry, you have been blocked",
    "you are unable to access ub.ac.id",
    "this website is using a security service",
)


class KeyboardLike(Protocol):
    def press(self, key: str) -> None: ...


class LocatorLike(Protocol):
    @property
    def first(self) -> "LocatorLike": ...

    def locator(self, selector: str) -> "LocatorLike": ...

    def inner_text(self, *, timeout: int) -> str: ...

    def click(self, *, timeout: int) -> None: ...


class PageLike(Protocol):
    url: str
    keyboard: KeyboardLike

    def locator(self, selector: str) -> LocatorLike: ...

    def wait_for_url(self, url: Callable[[str], bool], *, timeout: int) -> None: ...


def is_iam_block_page(body_text: str) -> bool:
    normalized = " ".join(body_text.casefold().split())
    return any(marker in normalized for marker in IAM_BLOCK_MARKERS)


def handle_saml_redirect(page: PageLike, *, wait_for_brone: bool = False) -> bool:
    if "iam.ub.ac.id" not in page.url:
        return False
    print("[brone] caught SAML redirect; inspecting page", flush=True)  # noqa: T201
    body_text = _body_text(page)
    print(f"[brone] SAML page body preview: {body_text[:300]}", flush=True)  # noqa: T201
    if is_iam_block_page(body_text):
        msg = (
            "UB IAM returned a security block page. Stopped without retrying to protect "
            "the account; do not keep running this from Railway until the network/session "
            "is trusted again."
        )
        raise LoginFailedError(msg)
    _submit_saml_form(page)
    if wait_for_brone:
        _wait_for_brone(page)
    return True


def _body_text(page: PageLike) -> str:
    try:
        return page.locator("body").inner_text(timeout=5_000)
    except (PlaywrightError, PlaywrightTimeoutError):
        return ""


def _submit_saml_form(page: PageLike) -> None:
    try:
        page.locator("form").first.locator(
            "input[type='submit'], button[type='submit'], button"
        ).first.click(timeout=3_000)
        print("[brone] clicked SAML form submit", flush=True)  # noqa: T201
    except (PlaywrightError, PlaywrightTimeoutError):
        try:
            page.keyboard.press("Enter")
            print("[brone] pressed Enter on SAML form", flush=True)  # noqa: T201
        except (PlaywrightError, PlaywrightTimeoutError) as error:
            print(f"[brone] SAML form submit failed: {error}", flush=True)  # noqa: T201


def _wait_for_brone(page: PageLike) -> None:
    try:
        page.wait_for_url(lambda url: "brone.ub.ac.id" in url, timeout=15_000)
    except (PlaywrightError, PlaywrightTimeoutError):
        print("[brone] SAML did not resolve; stopping before forced retry", flush=True)  # noqa: T201
        msg = "SAML login did not return to BRONE. Stopped before retrying authentication."
        raise LoginFailedError(msg) from None
