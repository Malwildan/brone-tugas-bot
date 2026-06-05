from collections.abc import Callable

import pytest

from brone_tugas_bot.brone_auth import LoginFailedError, handle_saml_redirect


class FakeKeyboard:
    def __init__(self) -> None:
        self.presses: list[str] = []

    def press(self, key: str) -> None:
        self.presses.append(key)


class FakeLocator:
    def __init__(self, text: str, *, matches: int = 0) -> None:
        self._text = text
        self._matches = matches
        self.clicks = 0

    @property
    def first(self) -> "FakeLocator":
        return self

    def locator(self, _selector: str) -> "FakeLocator":
        return self

    def inner_text(self, *, timeout: int) -> str:
        _ = timeout
        return self._text

    def click(self, *, timeout: int) -> None:
        _ = timeout
        self.clicks += 1

    def count(self) -> int:
        return self._matches


class FakePage:
    def __init__(
        self,
        body_text: str,
        *,
        has_login_form: bool = False,
        has_saml_form: bool = False,
    ) -> None:
        self.url = "https://iam.ub.ac.id/auth/realms/ub/protocol/saml"
        self.keyboard = FakeKeyboard()
        self._body_locator = FakeLocator(body_text)
        self._form_locator = FakeLocator(body_text, matches=int(has_saml_form))
        self._login_locator = FakeLocator(body_text, matches=int(has_login_form))
        self.waited_for_brone = False

    @property
    def form_clicks(self) -> int:
        return self._form_locator.clicks

    def locator(self, selector: str) -> FakeLocator:
        if selector == "body":
            return self._body_locator
        if selector in {"#username", "#password"}:
            return self._login_locator
        if "SAMLResponse" in selector or "SAMLRequest" in selector or selector == "form":
            return self._form_locator
        return FakeLocator("")

    def wait_for_url(self, url: Callable[[str], bool], *, timeout: int) -> None:
        _ = timeout
        url("https://brone.ub.ac.id/my/")
        self.waited_for_brone = True


def test_handle_saml_redirect_when_iam_blocks_account_stops_without_submit() -> None:
    # Given
    page = FakePage(
        "Sorry, you have been blocked\n"
        "You are unable to access ub.ac.id\n"
        "This website is using a security service to protect itself from online attacks."
    )

    # When
    with pytest.raises(LoginFailedError, match="security block page"):
        handle_saml_redirect(page, wait_for_brone=True)

    # Then
    assert page.form_clicks == 0
    assert page.keyboard.presses == []
    assert page.waited_for_brone is False


def test_handle_saml_redirect_when_iam_body_is_empty_stops_without_submit() -> None:
    # Given
    page = FakePage("")

    # When
    with pytest.raises(LoginFailedError, match="Cloudflare"):
        handle_saml_redirect(page, wait_for_brone=True)

    # Then
    assert page.form_clicks == 0
    assert page.keyboard.presses == []
    assert page.waited_for_brone is False


def test_handle_saml_redirect_when_cloudflare_challenge_stops_without_submit() -> None:
    # Given
    page = FakePage(
        "iam.ub.ac.id\n"
        "Performing security verification\n"
        "This website uses a security service to protect against malicious bots.\n"
        "Ray ID: a06d536a4a3098ce\n"
        "Performance and Security by Cloudflare"
    )

    # When
    with pytest.raises(LoginFailedError, match="Cloudflare security verification"):
        handle_saml_redirect(page, wait_for_brone=True)

    # Then
    assert page.form_clicks == 0
    assert page.keyboard.presses == []
    assert page.waited_for_brone is False


def test_handle_saml_redirect_when_login_form_is_visible_defers_to_login_flow() -> None:
    # Given
    page = FakePage(
        "Sistem Autentikasi Universitas Brawijaya\nUsername or email\nPassword",
        has_login_form=True,
    )

    # When
    handled = handle_saml_redirect(page, wait_for_brone=True)

    # Then
    assert handled is False
    assert page.form_clicks == 0
    assert page.keyboard.presses == []
    assert page.waited_for_brone is False


def test_handle_saml_redirect_when_brone_page_is_rendered_does_not_press_enter() -> None:
    # Given
    page = FakePage("Dashboard\nCourse overview\nSearch courses")

    # When
    handled = handle_saml_redirect(page, wait_for_brone=True)

    # Then
    assert handled is True
    assert page.form_clicks == 0
    assert page.keyboard.presses == []
    assert page.waited_for_brone is False


def test_handle_saml_redirect_when_readable_transition_page_waits_without_submit() -> None:
    # Given
    page = FakePage("Skip to navigation\nSkip to main content")

    # When
    handled = handle_saml_redirect(page, wait_for_brone=True)

    # Then
    assert handled is True
    assert page.form_clicks == 0
    assert page.keyboard.presses == []
    assert page.waited_for_brone is True
