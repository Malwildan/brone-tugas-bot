import base64
import io
import json
import tarfile
from pathlib import Path

import pytest

from brone_tugas_bot.browser_state import (
    BrowserStateError,
    _extract_profile_archive,
    export_browser_profile_archive,
    storage_state_to_base64,
)
from brone_tugas_bot.settings import Settings


def test_storage_state_to_base64_when_state_is_valid(tmp_path: Path) -> None:
    # Given
    state_path = tmp_path / "state.json"
    state = {"cookies": [], "origins": []}
    state_path.write_text(json.dumps(state), encoding="utf-8")

    # When
    encoded = storage_state_to_base64(state_path)

    # Then
    decoded = json.loads(base64.b64decode(encoded).decode("utf-8"))
    assert decoded == state


def test_storage_state_to_base64_when_state_is_invalid(tmp_path: Path) -> None:
    # Given
    state_path = tmp_path / "state.json"
    state_path.write_text('{"cookies": []}', encoding="utf-8")

    # When
    with pytest.raises(BrowserStateError, match="does not look like Playwright"):
        storage_state_to_base64(state_path)


def test_export_browser_profile_archive_when_profile_exists(tmp_path: Path) -> None:
    # Given
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / "Preferences").write_text("{}", encoding="utf-8")
    archive_path = tmp_path / "profile.tar.gz"
    settings = Settings(browser_state_dir=profile_dir)

    # When
    export_browser_profile_archive(settings, archive_path)

    # Then
    with tarfile.open(archive_path, mode="r:gz") as archive:
        assert ".brone-browser-state/Preferences" in archive.getnames()


def test_extract_profile_archive_when_path_is_unsafe() -> None:
    # Given
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        data = b"bad"
        info = tarfile.TarInfo("../outside")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))

    # When
    with pytest.raises(BrowserStateError, match="unsafe path"):
        _extract_profile_archive(payload.getvalue())
