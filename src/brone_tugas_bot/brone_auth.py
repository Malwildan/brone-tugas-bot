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
CLOUDFLARE_CHALLENGE_MARKERS: Final = (
    "performing security verification",
    "verifies you are not a bot",
    "malicious bots",
    "ray id:",
    "performance and security by cloudflare",
)


class KeyboardLike(Protocol):
    def press(self, key: str) -> None: ...


class LocatorLike(Protocol):
    @property
    def first(self) -> "LocatorLike": ...

    def locator(self, selector: str) -> "LocatorLike": ...

    def inner_text(self, *, timeout: int) -> str: ...

    def click(self, *, timeout: int) -> None: ...

    def count(self) -> int: ...


class PageLike(Protocol):
    url: str
    keyboard: KeyboardLike

    def locator(self, selector: str) -> LocatorLike: ...

    def wait_for_url(self, url: Callable[[str], bool], *, timeout: int) -> None: ...


def is_iam_block_page(body_text: str) -> bool:
    normalized = " ".join(body_text.casefold().split())
    return any(marker in normalized for marker in IAM_BLOCK_MARKERS)


def is_cloudflare_challenge_page(body_text: str) -> bool:
    normalized = " ".join(body_text.casefold().split())
    return any(marker in normalized for marker in CLOUDFLARE_CHALLENGE_MARKERS)


def handle_saml_redirect(page: PageLike, *, wait_for_brone: bool = False) -> bool:
    if "iam.ub.ac.id" not in page.url:
        return False
    print("[brone] caught SAML redirect; inspecting page", flush=True)  # noqa: T201
    body_text = _body_text(page)
    print(f"[brone] SAML page body preview: {body_text[:300]}", flush=True)  # noqa: T201
    if _has_login_form(page):
        return False
    if not body_text.strip():
        msg = (
            "UB IAM returned an unreadable security-verification page. Stopped before "
            "submitting anything. On Railway this usually means Cloudflare is challenging "
            "the datacenter browser; run the bot from a trusted local/private network "
            "instead of Railway."
        )
        raise LoginFailedError(msg)
    if _is_brone_page(body_text):
        return True
    if is_cloudflare_challenge_page(body_text):
        msg = (
            "UB IAM is showing Cloudflare security verification to this host. Railway's "
            "datacenter browser cannot safely pass that auth gate; run the bot locally or "
            "on a trusted private machine/network."
        )
        raise LoginFailedError(msg)
    if is_iam_block_page(body_text):
        msg = (
            "UB IAM returned a security block page. Stopped without retrying to protect "
            "the account; do not keep running this from Railway until the network/session "
            "is trusted again."
        )
        raise LoginFailedError(msg)
    if not _has_saml_relay_form(page):
        if wait_for_brone:
            _wait_for_brone(page)
            return True
        msg = "IAM page is neither a login form nor a SAML relay form. Stopped before submitting."
        raise LoginFailedError(msg)
    _submit_saml_form(page)
    if wait_for_brone:
        _wait_for_brone(page)
    return True


def _has_login_form(page: PageLike) -> bool:
    return page.locator("#username").count() > 0 or page.locator("#password").count() > 0


def _is_brone_page(body_text: str) -> bool:
    normalized = " ".join(body_text.casefold().split())
    return "dashboard" in normalized and "course overview" in normalized


def _has_saml_relay_form(page: PageLike) -> bool:
    return (
        page.locator("form input[name='SAMLResponse'], form input[name='SAMLRequest']").count()
        > 0
    )


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
        msg = "SAML relay form submit failed. Stopped before keyboard fallback."
        raise LoginFailedError(msg) from None


def _wait_for_brone(page: PageLike) -> None:
    try:
        page.wait_for_url(lambda url: "brone.ub.ac.id" in url, timeout=15_000)
    except (PlaywrightError, PlaywrightTimeoutError):
        print("[brone] SAML did not resolve; stopping before forced retry", flush=True)  # noqa: T201
        msg = "SAML login did not return to BRONE. Stopped before retrying authentication."
        raise LoginFailedError(msg) from None
