from collections.abc import Callable

import pytest

from brone_tugas_bot.brone_auth import LoginFailedError, handle_saml_redirect


class FakeKeyboard:
    def __init__(self) -> None:
        self.presses: list[str] = []

    def press(self, key: str) -> None:
        self.presses.append(key)


class FakeLocator:
    def __init__(self, text: str) -> None:
        self._text = text
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


class FakePage:
    def __init__(self, body_text: str) -> None:
        self.url = "https://iam.ub.ac.id/auth/realms/ub/protocol/saml"
        self.keyboard = FakeKeyboard()
        self._locator = FakeLocator(body_text)
        self.waited_for_brone = False

    @property
    def form_clicks(self) -> int:
        return self._locator.clicks

    def locator(self, _selector: str) -> FakeLocator:
        return self._locator

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
    with pytest.raises(LoginFailedError, match="no readable body"):
        handle_saml_redirect(page, wait_for_brone=True)

    # Then
    assert page.form_clicks == 0
    assert page.keyboard.presses == []
    assert page.waited_for_brone is False
